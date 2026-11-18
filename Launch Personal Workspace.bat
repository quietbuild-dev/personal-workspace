@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python virtual environment missing. Open PowerShell here and run:
  echo py -3.12 -m venv .venv
  echo .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m streamlit run app.py
if errorlevel 1 pause
