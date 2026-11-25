@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Missing Python virtual environment. Run setup in this project folder first.
    pause
    exit /b 1
)
if not exist "data\calendar-v3-demo.db" (
    echo Creating a NEW demo workspace for the current week...
    ".venv\Scripts\python.exe" -m scripts.create_playground_demo --output data/calendar-v3-demo.db
    if errorlevel 1 (
        echo Demo data generation failed. Your personal workspace is untouched.
        pause
        exit /b 1
    )
)
set "WORKSPACE_DB_PATH=%CD%\data\calendar-v3-demo.db"
echo DEMO MODE. Using data\calendar-v3-demo.db, NOT your personal workspace.db.
echo Open http://localhost:8503 if the browser does not open by itself.
".venv\Scripts\python.exe" -m streamlit run app.py --server.port 8503
endlocal
