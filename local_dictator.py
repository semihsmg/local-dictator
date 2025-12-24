"""
Local Dictator - Push-to-talk speech-to-text dictation for Windows
"""

import json
import logging
import os
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
    "hotkey": "ctrl+insert",
    "min_duration_seconds": 0.5,
    "model": "tiny",
    "language": "en",
    "beep_enabled": True,
    "log_to_file": True,
    "log_to_console": True
}

CLIPBOARD_RESTORE_DELAY = 0.1  # 100ms


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
        self.ctrl_pressed = False

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

    def _load_model(self):
        """Load the Whisper model."""
        model_name = self.config.get("model", "tiny")
        self.logger.info(f"Loading Whisper model: {model_name}")

        try:
            self.model = WhisperModel(model_name, device="cpu", compute_type="int8")
            self.logger.info("Model loaded successfully")
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

            segments, info = self.model.transcribe(
                audio,
                language=self.config.get("language", "en"),
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

    def _on_key_down(self, event):
        """Handle key down events."""
        if event.name == "insert" and keyboard.is_pressed("ctrl"):
            if not self.recording:
                self._start_recording()

    def _on_key_up(self, event):
        """Handle key up events."""
        if event.name == "insert":
            if self.recording:
                self._stop_recording()

    def _setup_hotkey(self):
        """Register global hotkey listeners."""
        try:
            keyboard.on_press_key("insert", self._on_key_down, suppress=False)
            keyboard.on_release_key("insert", self._on_key_up, suppress=False)
            self.logger.info("Hotkey registered: Ctrl+Insert")
        except Exception as e:
            self.logger.error(f"Failed to register hotkey: {e}")

    def _create_menu(self):
        """Create system tray menu."""
        def get_status_text(item):
            return f"Status: {self.state.value.capitalize()}"

        return pystray.Menu(
            pystray.MenuItem(get_status_text, lambda: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._exit)
        )

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

        self.logger.info("Application ready. Press Ctrl+Insert to dictate.")

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
