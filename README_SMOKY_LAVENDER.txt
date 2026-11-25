PERSONAL WORKSPACE - SMOKY LAVENDER UI OVERLAY

This ZIP updates the existing Calendar V4 application in-place. It contains
source, CSS, tests, a release note, and a read-only HTML visual preview. It
does not contain a .db file, personal data, or a Python environment.

Please read docs/SMOKY_LAVENDER_RELEASE.md for exact installation steps.

QUICK WINDOWS STEPS (inside the project folder, after saving a Git checkpoint):

  Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\personal-workspace-smoky-lavender-update.zip" -DestinationPath . -Force
  .\.venv\Scripts\python.exe -m ruff check --fix .
  .\.venv\Scripts\python.exe -m ruff format .
  .\.venv\Scripts\python.exe -m ruff check .
  .\.venv\Scripts\python.exe -m ruff format --check .
  .\.venv\Scripts\python.exe -m pytest -q
  .\.venv\Scripts\python.exe -m scripts.check_ui

Run the app:

  .\.venv\Scripts\python.exe -m streamlit run app.py

For safe sample data:

  & ".\Launch Calendar V3 Demo.bat"

Preview (no database; cannot save):

  previews\smoky-lavender-preview.html

Important: The source was reconstructed from the existing V4 update packages.
The functional Python regression suite passed here (157 tests, 58 subtests),
but Streamlit/Ruff and actual browser checks still require your Windows setup.
