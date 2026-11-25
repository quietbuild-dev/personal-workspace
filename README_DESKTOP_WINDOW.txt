Personal Workspace - Desktop Window Update

This patch adds a hidden Windows Streamlit launcher and changes the desktop
shortcut to open Edge/Chrome in a standalone app window. It does NOT modify
app.py, scheduling logic, tests, or personal SQLite data.

1. Extract this ZIP into the existing personal-workspace project folder.
2. Run: & ".\Create Desktop Shortcut.bat"
3. Double-click "Personal Workspace" on your desktop.
4. Close the standalone app window to stop the associated local server.

Requires Python venv and Microsoft Edge or Google Chrome. Error log:
%LOCALAPPDATA%\PersonalWorkspace\desktop-server.log

Full notes: docs/DESKTOP_LAUNCHER.md
