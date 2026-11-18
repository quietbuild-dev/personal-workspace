PERSONAL WORKSPACE - CALENDAR V3 UPDATE

1. This ZIP is a source-only overlay plus a demo generator and local HTML preview.
   It contains NO personal database or Git metadata.
2. Extract into the SAME personal-workspace folder, preserving its directory structure.
   You should already have the Rescue My Week update installed.
3. Stop Streamlit before installing. Do not remove .venv or data/workspace.db.
4. Verify:
      .\.venv\Scripts\python.exe -m ruff check .
      .\.venv\Scripts\python.exe -m ruff format --check .
      .\.venv\Scripts\python.exe -m pytest -q
      .\.venv\Scripts\python.exe -m scripts.check_ui
5. Open previews/my-calendar-playable-preview.html to play with the
   no-install, read-only before/after example.
6. Or double-click "Launch Calendar V3 Demo.bat" to use the REAL app with a
   separate, automatically generated example database at localhost:8503.
7. See docs/CALENDAR_V3.md for features, limitations and reset instructions.

Your personal database is not included or replaced by this ZIP.
