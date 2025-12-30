@echo off
cd /d "%~dp0"
python -m venv .venv
call .venv\Scripts\activate
pip install -r requirements.txt
echo Setup complete. Run start-cpu.bat or start-cuda.bat to launch.
pause
