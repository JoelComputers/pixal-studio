@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run the installation commands in README.md first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" doctor.py
if errorlevel 1 (
  pause
  exit /b 1
)
start "" http://127.0.0.1:8790
".venv\Scripts\python.exe" server.py
if errorlevel 1 pause
