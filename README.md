# Local Dictator

A local push-to-talk speech-to-text dictation app for Windows. Hold a hotkey, speak, and your words appear at the cursor.

## Features

- **Push-to-talk**: Hold `Ctrl+Insert` to record, release to transcribe
- **Local processing**: Uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper) with the base model - no cloud, no API keys
- **Multi-language**: Auto-detects language or set a specific one in config
- **System-wide**: Works in any application via clipboard injection
- **System tray**: Minimal footprint with color-coded status icon
- **Audio feedback**: Beeps indicate recording start/stop/error
- **GPU acceleration**: Auto-detects NVIDIA CUDA for faster transcription

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

This creates a virtual environment and installs dependencies. First run will download the Whisper model (~145MB) to the Hugging Face cache (`~/.cache/huggingface/hub/`).

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
  "model": "base",
  "language": null,
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
| `language` | Language code (e.g., "en", "de", "fr") or null for auto-detect |
| `beep_enabled` | Audio feedback on/off |
| `log_to_file` | Write logs to `local-dictator.log` |
| `log_to_console` | Print logs to console |

## Troubleshooting

**No transcription appears**: Ensure the target application has focus before releasing the hotkey.

**Empty transcriptions**: Speak clearly and ensure your microphone is working. Recordings under 0.5s are ignored.

**Hotkey doesn't work**: Another application may be using `Ctrl+Insert`. Check the log file for errors.

## GPU Acceleration (Optional)

The app auto-detects NVIDIA CUDA and uses GPU if available. For CPU-only systems, it falls back automatically.

### To Enable CUDA

1. **Install NVIDIA drivers** (if not already installed)

2. **Install CUDA Toolkit 12.x**
   - Download from [NVIDIA CUDA Downloads](https://developer.nvidia.com/cuda-downloads)
   - Or via winget: `winget install Nvidia.CUDA`

3. **Reinstall ctranslate2 with CUDA support**

   ```batch
   .venv\Scripts\activate
   pip uninstall ctranslate2 -y
   pip install ctranslate2
   ```

4. **Verify** - Check the log on startup:

   ```log
   Loading Whisper model: base on cuda (float16)
   Model loaded successfully on CUDA
   ```

If CUDA is not detected, you'll see:

```log
Loading Whisper model: base on cpu (int8)
Model loaded successfully on CPU
```

## License

MIT
