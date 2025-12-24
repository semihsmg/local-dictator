# local-dictator

A local push-to-talk speech-to-text dictation app for coding sessions in VS Code.

## Project Overview

**Purpose:** System-wide dictation tool that records speech while holding a hotkey and inserts transcribed text at the cursor position via clipboard injection.

**Target Platform:** Windows 10/11

**Runtime:** Python 3.10+ with virtual environment + batch file launcher

## Architecture

```md
┌─────────────────────────────────────────────────┐
│         System Tray App (pystray)               │
├─────────────────────────────────────────────────┤
│  Global Hotkey: keyboard lib (Ctrl+Insert)      │
│  Audio Recording: sounddevice + numpy           │
│  Audio Feedback: winsound (beeps)               │
│  STT: faster-whisper (base, int8, CPU)          │
│  Text Injection: pyperclip + pynput (Ctrl+V)    │
│  Icons: Lucide message-circle-code (PIL render) │
└─────────────────────────────────────────────────┘
```

## Core Behavior

### Hotkey: Push-to-Talk

- **Hotkey:** `Ctrl+Insert`
- **Behavior:** Hold to record, release to transcribe and insert
- **Minimum duration:** 0.5 seconds (recordings shorter than this are ignored to prevent accidental triggers)

### Recording

- **Audio backend:** `sounddevice` with `numpy`
- **Sample rate:** 16000 Hz (Whisper requirement)
- **Channels:** Mono
- **Device:** System default input device

### Transcription

- **Engine:** `faster-whisper`
- **Model:** `base` (multilingual)
- **Compute:** CPU with int8 quantization
- **Mode:** Batch (full recording transcribed after release)
- **Language:** Auto-detect (configurable), pure transcription (no voice commands)

### Text Output

- **Method:** Clipboard injection
  1. Save current clipboard content
  2. Copy transcribed text to clipboard
  3. Simulate `Ctrl+V` keystroke
  4. Restore original clipboard content
- **Post-processing:** None (raw Whisper output, no capitalization, no punctuation stripping)
- **Trailing space:** None
- **Focus handling:** Insert regardless of focused window (user is responsible for focus)

### Audio Feedback (Beeps via winsound)

| Event | Frequency | Duration |
| ----- | --------- | -------- |
| Recording start | 800 Hz | 100 ms |
| Recording stop | 500 Hz | 100 ms |
| Error | 300 Hz | 100 ms |

### System Tray

- **Library:** `pystray`
- **Icon:** Lucide `message-circle-code` rendered via PIL
- **Icon states:**

  | State | Color | Hex |
  | ----- | ----- | --- |
  | Idle | Cyan | #06b6d4 |
  | Recording | Red | #ef4444 |
  | Processing | Yellow | #eab308 |

- **Menu items:**
  - Status display (current state: Idle/Recording/Processing)
  - Exit

### Model Loading

- **Strategy:** Eager (load at app startup)
- **Expected startup time:** 2-3 seconds

## Configuration

**File:** `config.json` in script directory

**Schema:**

```json
{
  "hotkey": "ctrl+insert",
  "min_duration_seconds": 0.5,
  "model": "base",
  "language": null,
  "beep_enabled": true,
  "log_to_file": true,
  "log_to_console": true
}
```

All fields should have sensible defaults if config file is missing.

## Logging

- **Console:** Enabled (for development visibility)
- **File:** `local-dictator.log` in script directory
- **Format:** Timestamp, level, message
- **Content:** Startup info, hotkey events, transcription results, errors

## Project Structure

```md
local-dictator/
├── CLAUDE.md              # This specification
├── config.json            # User configuration
├── requirements.txt       # Python dependencies
├── start.bat              # Windows launcher script
├── setup.bat              # Venv setup script
├── local_dictator.py      # Main application entry point
├── local-dictator.log     # Log file (generated at runtime)
└── icons/                 # Generated icon files (optional cache)
```

## Dependencies

```md
faster-whisper
sounddevice
numpy
pystray
Pillow
keyboard
pynput
pyperclip
requests
```

Note: `winsound` is Windows built-in, no pip install needed.

## Lucide Icon Handling

The `message-circle-code` icon should be:

1. Downloaded from Lucide (SVG) or fetched via URL
2. Rendered to PIL Image at appropriate size (64x64 recommended for tray)
3. Colorized according to current state
4. Converted to format suitable for pystray

**Lucide SVG URL pattern:** `https://unpkg.com/lucide-static@latest/icons/message-circle-code.svg`

## Launcher Scripts

### setup.bat

```batch
@echo off
python -m venv .venv
call .venv\Scripts\activate
pip install -r requirements.txt
echo Setup complete. Run start.bat to launch.
pause
```

### start.bat

```batch
@echo off
call .venv\Scripts\activate
pythonw local_dictator.py
```

Note: `pythonw` runs without console window. For debugging, use `python` instead.

## Implementation Notes

### Threading Model

- Main thread: pystray event loop
- Hotkey listener: Runs in separate thread (keyboard library handles this)
- Recording: Happens on hotkey thread
- Transcription: Can block briefly (base model is fast), but consider running in thread pool if UI feels sluggish

### Clipboard Restoration

```python
import pyperclip

original = pyperclip.paste()
pyperclip.copy(transcribed_text)
# simulate Ctrl+V
pyperclip.copy(original)  # restore
```

Handle exceptions if clipboard contains non-text data (images, etc.) — in that case, just skip restoration.

### Hotkey Implementation

```python
import keyboard

keyboard.on_press_key("insert", on_key_down, suppress=True)
keyboard.on_release_key("insert", on_key_up, suppress=True)

# Check for ctrl modifier in handlers
```

Alternatively, use `keyboard.add_hotkey("ctrl+insert", ...)` but this doesn't easily support push-to-talk. Manual key tracking recommended.

### Error Conditions to Handle

1. **No microphone available** — Show error in tray, log, don't crash
2. **Model download fails** — faster-whisper auto-downloads; handle network errors gracefully
3. **Empty transcription** — Play error beep, don't paste empty string
4. **Clipboard access fails** — Log warning, continue without paste
5. **Hotkey conflict** — Log error if hotkey registration fails

### Graceful Shutdown

- Tray "Exit" should:
  1. Stop hotkey listener
  2. Release audio resources
  3. Stop pystray
- Handle `SIGINT`/`SIGTERM` similarly

## Testing Checklist

- [ ] App starts without errors
- [ ] Tray icon appears (cyan)
- [ ] Ctrl+Insert starts recording (icon turns red, start beep plays)
- [ ] Releasing Ctrl+Insert stops recording (stop beep plays, icon turns yellow)
- [ ] Transcribed text appears at cursor in VS Code
- [ ] Original clipboard content is restored
- [ ] Recordings under 0.5s are ignored
- [ ] Empty transcriptions play error beep
- [ ] Exit menu item closes app cleanly
- [ ] Logs appear in console and file

## Future Enhancements (Out of Scope for v1)

- Microphone selection in tray menu
- Configurable hotkey via tray menu
- Auto-start with Windows
- Model size selection (tiny, small, large)
- Voice commands ("new line", "tab", etc.)
- Real-time/streaming transcription
- PyInstaller packaging to standalone .exe
