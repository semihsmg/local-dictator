# Local Dictator

A local push-to-talk speech-to-text dictation app for Windows. Hold a hotkey, speak, and your words appear at the cursor.

## Features

- **Push-to-talk**: Hold `Ctrl+Insert` to record, release to transcribe
- **Local processing**: Uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper) with the tiny model - no cloud, no API keys
- **System-wide**: Works in any application via clipboard injection
- **System tray**: Minimal footprint with color-coded status icon
- **Audio feedback**: Beeps indicate recording start/stop/error

## Requirements

- Windows 10/11
- Python 3.10+
- Microphone

## Installation

```batch
git clone https://github.com/your-username/local-dictator.git
cd local-dictator
setup.bat
```

This creates a virtual environment and installs dependencies. First run will download the Whisper model (~75MB).

## Usage

```batch
start.bat
```

A cyan icon appears in the system tray. Hold `Ctrl+Insert` to dictate:

| Icon Color | State |
| ---------- | ----- |
| Cyan | Idle - ready to record |
| Red | Recording - speak now |
| Yellow | Processing - transcribing |

Right-click the tray icon to exit.

## Configuration

Copy `config.example.json` to `config.json` to customize (optional - defaults are used if missing):

```json
{
  "hotkey": "ctrl+insert",
  "min_duration_seconds": 0.5,
  "model": "tiny",
  "language": "en",
  "beep_enabled": true,
  "log_to_file": true,
  "log_to_console": true
}
```

| Option | Description |
| ------ | ----------- |
| `hotkey` | Push-to-talk hotkey combination |
| `min_duration_seconds` | Minimum recording length (prevents accidental triggers) |
| `model` | Whisper model size (tiny, base, small) |
| `language` | Language code for transcription |
| `beep_enabled` | Audio feedback on/off |
| `log_to_file` | Write logs to `local-dictator.log` |
| `log_to_console` | Print logs to console |

## Troubleshooting

**No transcription appears**: Ensure the target application has focus before releasing the hotkey.

**Empty transcriptions**: Speak clearly and ensure your microphone is working. Recordings under 0.5s are ignored.

**Hotkey doesn't work**: Another application may be using `Ctrl+Insert`. Check the log file for errors.

## License

MIT
