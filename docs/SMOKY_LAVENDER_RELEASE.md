# Smoky Lavender UI update

This update is an overlay for **Calendar V4 on `main`**. It is intentionally
presentation-focused: the planner, SQLite repository, migrations, task models,
and proposal validation/undo algorithms are not included and are not changed.

## What changed

- Centralized Smoky Lavender presentation module (`workspace/theme.py`) and
  Streamlit theme configuration: `#14141A` background, `#22222B` cards,
  `#2C2A36` raised surfaces, `#BAA9D0` accents, `#F1EEF5` main text,
  `#A8A4B3` secondary text, and `#393640` borders.
- Top navigation: **Home**, **Calendar**, **Tasks**. Previously hidden legacy
  task-step and planner pages remain available under **Advanced**.
- Home: a date-aware greeting, three dynamic metrics (active tasks, accepted
  study hours this week, upcoming deadlines), focus list with badges and
  checklist completion, deadlines, a weekly workload chart, and a concise
  planning insight. Existing Home task entry and actions remain available in
  expandable sections; the new Tasks page provides dedicated access.
- Calendar: restrained Lavender treatment for study, blue-gray for lectures,
  mauve for social events, green for exercise, and warm gray for personal events.
  Priority remains a separate High/Medium/Low indicator, not an event color.
- Rescue My Week: both strategy explanations, an informative summary, clearer
  lavender Before/After comparison, and Approve/Cancel/Undo language.
- The old technical/advanced page implementations are intentionally kept intact
  so existing controls aren't silently deleted by the redesign.

## What did not change

- Constraint-aware scheduling or the two Rescue My Week algorithms.
- Task creation/editing semantics, checklists, progress, or validations.
- SQLite schema, saved data, database paths, and write/undo transactions.
- Work estimates, preference inputs, or existing API method signatures.

## Installation on Windows

From a clean `main` checkout, create a feature branch before installing:

```powershell
cd C:\Users\Win\OneDrive\Desktop\personal-workspace
git status -sb
git switch main
git pull --ff-only origin main
git switch -c feat/smoky-lavender-ui
```

Back up the personal database if you use it:

```powershell
if (Test-Path .\data\workspace.db) {
    Copy-Item .\data\workspace.db .\data\workspace-before-lavender.db
}
```

Download `personal-workspace-smoky-lavender-update.zip` to Downloads and unzip
it into the project directory:

```powershell
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\personal-workspace-smoky-lavender-update.zip" -DestinationPath . -Force
```

These are application/source files only. **There is no database in the ZIP**.

Run Ruff normalization, the test suite, and the UI smoke test:

```powershell
.\.venv\Scripts\python.exe -m ruff check --fix .
.\.venv\Scripts\python.exe -m ruff format .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.check_ui
```

The theme uses Streamlit's top navigation introduced in version 1.46, which is
already the minimum Streamlit version in `requirements.txt`.

Run the app normally:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Or test with a separate sample database:

```powershell
& ".\Launch Sample Workspace.bat"
```

The old demo launcher name remains unchanged. The browser address is normally
`http://localhost:8503`. The demo still uses `data/calendar-v3-demo.db`, not
`data/workspace.db`.

## Manual acceptance checks

1. Check Home, Calendar, Tasks and the Advanced navigation dropdown.
2. Compare the dashboard counts with actual tasks and accepted sessions.
3. Create a quick errand with optional scheduling turned off. Confirm it is not
   added to the study calendar. Edit a task and its checklist.
4. In Calendar, change Day/Week and dates; click events and study blocks and
   confirm the details stay in the app. Try session progress actions.
5. Save study preferences, run both Rescue strategies and the what-if preview,
   accept a safe revision and undo it. Verify that stale undo is rejected.
6. Restart the app and confirm data is unchanged except for actions you
   explicitly saved. Check on a laptop-sized browser window.
7. Open both Advanced legacy pages and confirm their controls remain available.

## Verification status

This reconstructed V4 source passed **157 tests plus 58 subtests** in the
packaging environment; all changed Python modules compiled. The environment
could not install Streamlit or Ruff, so the Streamlit browser, smoke check,
and Ruff checks above must be completed on Windows before merge. The preview
`previews/smoky-lavender-preview.html` is an illustrative visual mockup only,
not a running app and not connected to any database.
