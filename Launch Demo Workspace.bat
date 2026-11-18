@echo off
setlocal
cd /d "%~dp0"
if not exist "data\study-playground.db" (
    echo The sample database is missing. Please extract the full demo ZIP into the project folder.
    pause
    exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    echo Python environment not found in .venv. Open the project setup first.
    pause
    exit /b 1
)
set "WORKSPACE_DB_PATH=%~dp0data\study-playground.db"
echo Starting SAMPLE Personal Workspace. Your personal database is not used.
".venv\Scripts\python.exe" -m streamlit run app.py
endlocal
