@echo off
python -m venv .venv
call .venv\Scripts\activate
pip install -r requirements.txt
echo Setup complete. Run start.bat to launch.
pause
