"""
Local Dictator - Push-to-talk speech-to-text dictation for Windows
"""

import json
import logging
import sys
import threading
import time
import winsound
from enum import Enum
from pathlib import Path

import keyboard
import numpy as np
import pyperclip
import pystray
import sounddevice as sd
from faster_whisper import WhisperModel
from PIL import Image
from pynput.keyboard import Controller as KeyboardController, Key


# === Constants ===

SCRIPT_DIR = Path(__file__).parent.resolve()
CONFIG_PATH = SCRIPT_DIR / "config.json"
LOG_PATH = SCRIPT_DIR / "local-dictator.log"
ICON_PATH = SCRIPT_DIR / "icons" / "message-circle-code.png"

SAMPLE_RATE = 16000
CHANNELS = 1

COLORS = {
    "idle": "#06b6d4",      # Cyan
    "recording": "#ef4444", # Red
    "processing": "#eab308" # Yellow
}

BEEP_FREQUENCIES = {
    "start": 800,
    "stop": 500,
    "error": 300
}
BEEP_DURATION = 100  # ms

DEFAULT_CONFIG = {
    "hotkey": "right ctrl",
    "min_duration_seconds": 0.5,
    "model": "base",
    "device": "auto",  # "auto", "cuda", or "cpu"
    "language": None,  # None = auto-detect
    "language_presets": [],  # Quick-switch languages in tray menu
    "beep_enabled": True,
    "log_to_file": False,
    "log_to_console": True
}

CLIPBOARD_RESTORE_DELAY = 0.1  # 100ms

DEFAULT_HOTKEY = "right ctrl"


class AppState(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"


class DictatorApp:
    def __init__(self):
        self.config = self._load_config()
        self._setup_logging()

        self.state = AppState.IDLE
        self.recording = False
        self.audio_data = []
        self.record_start_time = None

        self.icon = None
        self.icon_images = {}
        self.keyboard_controller = KeyboardController()
        self.model = None

        self._load_icon_images()
        self._load_model()

    def _load_config(self) -> dict:
        """Load config from file, create default if missing, use defaults if corrupted."""
        if not CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "w") as f:
                    json.dump(DEFAULT_CONFIG, f, indent=2)
            except Exception:
                pass
            return DEFAULT_CONFIG.copy()

        try:
            with open(CONFIG_PATH) as f:
                config = json.load(f)
            # Merge with defaults for any missing keys
            merged = DEFAULT_CONFIG.copy()
            merged.update(config)
            return merged
        except (json.JSONDecodeError, Exception) as e:
            print(f"Config error, using defaults: {e}")
            return DEFAULT_CONFIG.copy()

    def _save_config(self):
        """Save current config to file."""
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(self.config, f, indent=2)
            self.logger.info("Config saved")
        except Exception as e:
            self.logger.error(f"Failed to save config: {e}")

    def _setup_logging(self):
        """Configure logging based on config."""
        handlers = []

        if self.config.get("log_to_console", True):
            handlers.append(logging.StreamHandler(sys.stdout))

        if self.config.get("log_to_file", True):
            handlers.append(logging.FileHandler(LOG_PATH, encoding="utf-8"))

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=handlers if handlers else [logging.NullHandler()]
        )

        self.logger = logging.getLogger("local-dictator")
        self.logger.info("Local Dictator starting...")
        self.logger.info(f"Config: {self.config}")

    def _hex_to_rgb(self, hex_color: str) -> tuple:
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def _colorize_icon(self, image: Image.Image, color: str) -> Image.Image:
        """Colorize a white icon with the specified color."""
        img = image.copy().convert("RGBA")
        r, g, b = self._hex_to_rgb(color)

        pixels = img.load()
        width, height = img.size

        for y in range(height):
            for x in range(width):
                _, _, _, a = pixels[x, y]
                if a > 0:
                    pixels[x, y] = (r, g, b, a)

        return img.resize((64, 64), Image.Resampling.LANCZOS)

    def _load_icon_images(self):
        """Load and colorize icons for all states."""
        try:
            if not ICON_PATH.exists():
                self.logger.error(f"Icon not found: {ICON_PATH}")
                self._create_fallback_icons()
                return

            base_icon = Image.open(ICON_PATH)

            for state, color in COLORS.items():
                self.icon_images[state] = self._colorize_icon(base_icon, color)

            self.logger.info("Icons loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to load icon: {e}")
            self._create_fallback_icons()

    def _create_fallback_icons(self):
        """Create simple circle icons as fallback."""
        for state, color in COLORS.items():
            img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            pixels = img.load()
            r, g, b = self._hex_to_rgb(color)

            cx, cy = 32, 32
            radius = 28

            for y in range(64):
                for x in range(64):
                    dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                    if dist <= radius:
                        pixels[x, y] = (r, g, b, 255)

            self.icon_images[state] = img

        self.logger.info("Using fallback icons")

    def _detect_device(self):
        """Detect best available device based on config (auto, cuda, or cpu)."""
        device_config = self.config.get("device", "auto").lower()

        if device_config == "cpu":
            return "cpu", "int8"

        # Check CUDA availability
        cuda_available = False
        try:
            import ctranslate2
            if ctranslate2.get_supported_compute_types("cuda"):
                cuda_available = True
        except Exception:
            pass

        if device_config == "cuda":
            if cuda_available:
                return "cuda", "float16"
            else:
                self.logger.warning("CUDA requested but not available, falling back to CPU")
                return "cpu", "int8"

        # auto mode
        if cuda_available:
            return "cuda", "float16"
        return "cpu", "int8"

    def _load_model(self):
        """Load the Whisper model."""
        model_name = self.config.get("model", "base")
        device, compute_type = self._detect_device()
        self.logger.info(f"Loading Whisper model: {model_name} on {device} ({compute_type})")

        try:
            self.model = WhisperModel(model_name, device=device, compute_type=compute_type)
            self.logger.info(f"Model loaded successfully on {device.upper()}")
        except Exception as e:
            self.logger.error(f"Failed to load model: {e}")
            raise

    def _update_icon(self):
        """Update tray icon to reflect current state."""
        if self.icon:
            self.icon.icon = self.icon_images[self.state.value]

    def _set_state(self, state: AppState):
        """Update application state and icon."""
        self.state = state
        self._update_icon()

    def _beep(self, beep_type: str):
        """Play audio feedback beep."""
        if not self.config.get("beep_enabled", True):
            return

        freq = BEEP_FREQUENCIES.get(beep_type, 500)
        try:
            winsound.Beep(freq, BEEP_DURATION)
        except Exception as e:
            self.logger.warning(f"Beep failed: {e}")

    def _start_recording(self):
        """Start audio recording."""
        self.recording = True
        self.audio_data = []
        self.record_start_time = time.time()
        self._set_state(AppState.RECORDING)
        self._beep("start")
        self.logger.info("Recording started")

        def audio_callback(indata, frames, time_info, status):
            if status:
                self.logger.warning(f"Audio status: {status}")
            if self.recording:
                self.audio_data.append(indata.copy())

        try:
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=np.float32,
                callback=audio_callback
            )
            self.stream.start()
        except Exception as e:
            self.logger.error(f"Failed to start recording: {e}")
            self._beep("error")
            self._set_state(AppState.IDLE)
            self.recording = False

    def _stop_recording(self):
        """Stop recording and process audio."""
        if not self.recording:
            return

        self.recording = False
        duration = time.time() - self.record_start_time

        try:
            self.stream.stop()
            self.stream.close()
        except Exception as e:
            self.logger.warning(f"Error closing stream: {e}")

        self._beep("stop")
        self.logger.info(f"Recording stopped (duration: {duration:.2f}s)")

        min_duration = self.config.get("min_duration_seconds", 0.5)
        if duration < min_duration:
            self.logger.info(f"Recording too short ({duration:.2f}s < {min_duration}s), ignoring")
            self._set_state(AppState.IDLE)
            return

        if not self.audio_data:
            self.logger.warning("No audio data captured")
            self._beep("error")
            self._set_state(AppState.IDLE)
            return

        self._set_state(AppState.PROCESSING)
        self._process_audio()

    def _process_audio(self):
        """Transcribe audio and insert text."""
        try:
            audio = np.concatenate(self.audio_data, axis=0).flatten()
            self.logger.info(f"Processing {len(audio)} samples")

            language = self.config.get("language")  # None = auto-detect
            segments, info = self.model.transcribe(
                audio,
                language=language,
                beam_size=5
            )

            text = " ".join(segment.text for segment in segments).strip()

            if not text:
                self.logger.info("Empty transcription")
                self._beep("error")
                self._set_state(AppState.IDLE)
                return

            self.logger.info(f"Transcribed: {text}")
            self._insert_text(text)

        except Exception as e:
            self.logger.error(f"Transcription failed: {e}")
            self._beep("error")

        self._set_state(AppState.IDLE)

    def _insert_text(self, text: str):
        """Insert text via clipboard and Ctrl+V."""
        original_clipboard = None

        try:
            original_clipboard = pyperclip.paste()
        except Exception:
            pass

        try:
            pyperclip.copy(text)

            time.sleep(0.05)

            self.keyboard_controller.press(Key.ctrl)
            self.keyboard_controller.press("v")
            self.keyboard_controller.release("v")
            self.keyboard_controller.release(Key.ctrl)

            time.sleep(CLIPBOARD_RESTORE_DELAY)

            if original_clipboard is not None:
                pyperclip.copy(original_clipboard)

            self.logger.info("Text inserted successfully")

        except Exception as e:
            self.logger.error(f"Failed to insert text: {e}")
            self._beep("error")

    def _parse_hotkey(self, hotkey_str: str) -> dict:
        """Parse a hotkey string into configuration.

        Formats:
        - Single key: "menu", "f9", "pause"
        - Modifier+key: "ctrl+insert", "right ctrl+menu", "alt+`"
        """
        hotkey_str = hotkey_str.lower().strip()

        if "+" in hotkey_str:
            # Modifier+key format: split on last "+" to handle "right ctrl+menu"
            last_plus = hotkey_str.rfind("+")
            modifier = hotkey_str[:last_plus].strip()
            trigger = hotkey_str[last_plus + 1:].strip()
            return {
                "type": "modifier_trigger",
                "modifier": modifier,
                "trigger": trigger,
            }
        else:
            # Single key format
            return {
                "type": "single_key",
                "key": hotkey_str,
            }

    def _get_hotkey_config(self):
        """Get hotkey configuration, falling back to default if invalid."""
        hotkey = self.config.get("hotkey", DEFAULT_HOTKEY).lower().strip()
        return hotkey, self._parse_hotkey(hotkey)

    def _on_trigger_down(self, event):
        """Handle trigger key press - start recording if modifier is held (modifier_trigger type)."""
        if keyboard.is_pressed(self._hotkey_modifier) and not self.recording:
            threading.Thread(target=self._start_recording, daemon=True).start()
        return False  # Always suppress

    def _on_trigger_up(self, event):
        """Handle trigger key release - always suppress (modifier_trigger type)."""
        return False  # Always suppress

    def _on_modifier_up(self, event):
        """Handle modifier release - stop recording (modifier_trigger type)."""
        if self.recording:
            self._stop_recording()

    def _on_single_key_down(self, event):
        """Handle single key press - start recording (single_key type)."""
        if not self.recording:
            threading.Thread(target=self._start_recording, daemon=True).start()
        return False  # Always suppress

    def _on_single_key_up(self, event):
        """Handle single key release - stop recording (single_key type)."""
        # Schedule stop in a thread so we can return False immediately for suppression
        if self.recording:
            threading.Thread(target=self._stop_recording, daemon=True).start()
        return False  # Always suppress

    def _register_hotkey(self, hotkey_name: str, hotkey_config: dict):
        """Register hotkey handlers. Raises exception if key is invalid."""
        if hotkey_config["type"] == "modifier_trigger":
            self._hotkey_modifier = hotkey_config["modifier"]
            self._hotkey_trigger = hotkey_config["trigger"]

            keyboard.on_press_key(self._hotkey_trigger, self._on_trigger_down, suppress=True)
            keyboard.on_release_key(self._hotkey_trigger, self._on_trigger_up, suppress=True)
            keyboard.on_release_key(self._hotkey_modifier, self._on_modifier_up, suppress=False)

        elif hotkey_config["type"] == "single_key":
            single_key = hotkey_config["key"]
            keyboard.on_press_key(single_key, self._on_single_key_down, suppress=True)
            keyboard.on_release_key(single_key, self._on_single_key_up, suppress=True)

        self.logger.info(f"Hotkey registered: {hotkey_name}")

    def _setup_hotkey(self):
        """Register global hotkey listeners based on config."""
        hotkey_name, hotkey_config = self._get_hotkey_config()

        try:
            self._register_hotkey(hotkey_name, hotkey_config)
        except Exception as e:
            if hotkey_name != DEFAULT_HOTKEY:
                self.logger.warning(f"Invalid hotkey '{hotkey_name}': {e}")
                self.logger.warning(f"Falling back to default: {DEFAULT_HOTKEY}")
                try:
                    default_config = self._parse_hotkey(DEFAULT_HOTKEY)
                    self._register_hotkey(DEFAULT_HOTKEY, default_config)
                except Exception as e2:
                    self.logger.error(f"Failed to register default hotkey: {e2}")
            else:
                self.logger.error(f"Failed to register hotkey: {e}")

    def _set_language(self, lang_code):
        """Set the transcription language and save to config."""
        def action(icon, item):
            self.config["language"] = lang_code
            self._save_config()
            self.logger.info(f"Language set to: {lang_code or 'Auto'}")
            self.icon.update_menu()
        return action

    def _is_language_selected(self, lang_code):
        """Check if a language is currently selected."""
        def check(item):
            return self.config.get("language") == lang_code
        return check

    def _create_menu(self):
        """Create system tray menu."""
        def get_status_text(item):
            return f"Status: {self.state.value.capitalize()}"

        menu_items = [
            pystray.MenuItem(get_status_text, lambda: None, enabled=False),
            pystray.Menu.SEPARATOR,
        ]

        # Add language selection if language_presets are configured
        languages = self.config.get("language_presets", [])
        if languages:
            # Auto-detect option (always first)
            menu_items.append(pystray.MenuItem(
                "Auto",
                self._set_language(None),
                checked=self._is_language_selected(None),
                radio=True
            ))

            # Configured languages
            for lang in languages:
                menu_items.append(pystray.MenuItem(
                    lang.upper(),
                    self._set_language(lang),
                    checked=self._is_language_selected(lang),
                    radio=True
                ))

            menu_items.append(pystray.Menu.SEPARATOR)

        menu_items.append(pystray.MenuItem("Exit", self._exit))

        return pystray.Menu(*menu_items)

    def _exit(self, icon=None, item=None):
        """Clean up and exit application."""
        self.logger.info("Exiting...")

        try:
            keyboard.unhook_all()
        except Exception:
            pass

        if self.recording:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass

        if self.icon:
            self.icon.stop()

    def run(self):
        """Start the application."""
        self._setup_hotkey()

        self.icon = pystray.Icon(
            "local-dictator",
            self.icon_images["idle"],
            "Local Dictator",
            menu=self._create_menu()
        )

        hotkey_name, _ = self._get_hotkey_config()
        self.logger.info(f"Application ready. Hotkey: {hotkey_name}")

        try:
            self.icon.run()
        except KeyboardInterrupt:
            self._exit()


def main():
    try:
        app = DictatorApp()
        app.run()
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    main()
