@echo off
call .venv\Scripts\activate
set NVIDIA_PATH=%CD%\.venv\Lib\site-packages\nvidia
set PATH=%NVIDIA_PATH%\cudnn\bin;%NVIDIA_PATH%\cublas\bin;%NVIDIA_PATH%\cuda_runtime\bin;%PATH%
python local_dictator.py
