@echo off
cd /d "%~dp0"
call .venv\Scripts\activate
start "" pythonw local_dictator.py
