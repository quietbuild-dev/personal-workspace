PERSONAL WORKSPACE - CALENDAR V4 UPDATE

This is a SOURCE-ONLY overlay for a project with Calendar V3 already installed.
It includes no personal database or Git metadata.

1. Stop running Streamlit (Ctrl+C).
2. Save a Git checkpoint first and back up data/workspace.db.
3. Extract this ZIP into your EXISTING personal-workspace folder.
4. Run Ruff lint, Ruff format check, pytest, and scripts.check_ui.
5. Start the same demo launcher as before:
     & ".\Launch Calendar V3 Demo.bat"
   It starts the updated code with a separate demo database at localhost:8503.
6. See docs/CALENDAR_V4_RELEASE.md for detailed changes, limitations, and tests.

NOTE: The launcher still says V3, because the demo database name and safe
isolation mechanism are unchanged. The application source itself is V4.
