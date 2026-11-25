PERSONAL WORKSPACE — FINAL SMOKY LAVENDER POLISH

This ZIP is a small overlay for an ALREADY INSTALLED Smoky Lavender app.
Do not extract it into a blank directory or replace your whole repository.
The ZIP contains no SQLite databases and no algorithm/repository modules.

Read docs/FINAL_UI_POLISH.md for all instructions.

PowerShell (inside your project, on feat/smoky-lavender-ui):
  Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\personal-workspace-final-ui-polish.zip" -DestinationPath . -Force
  .\.venv\Scripts\python.exe -m ruff check --fix .
  .\.venv\Scripts\python.exe -m ruff format .
  .\.venv\Scripts\python.exe -m pytest -q
  .\.venv\Scripts\python.exe -m scripts.check_ui

Demo (separate demo DB):
  & ".\Launch Calendar V3 Demo.bat"

Personal-workspace desktop shortcut (run once):
  & ".\Create Desktop Shortcut.bat"

Keep the minimized server terminal running while using the desktop shortcut.
