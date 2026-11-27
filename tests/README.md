# Automated tests

We use **pytest** for automated tests and **Ruff** for code quality checks. The tests cover task management and progress, database changes, scheduling constraints, planning proposals, Undo, and selected UI behavior.

Tests that need SQLite create temporary databases rather than modifying personal workspace data. Some Streamlit interactions are simulated; the real interface still needs a manual check.

## Run the checks (Windows PowerShell)

From the project root with Python 3.12 and development dependencies installed:

```powershell
.\.venv\Scripts\python.exe -m ruff check .

$testDir = Join-Path $env:TEMP ("pw-tests-" + [guid]::NewGuid().ToString("N"))
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp "$testDir"

.\.venv\Scripts\python.exe -m scripts.check_optimizer_ui
```

We also ran synthetic evaluations comparing **CP-SAT** with the **greedy baseline**. See the [optimizer evaluation](../docs/OPTIMIZER_EVALUATION.md) for the scenarios, results, and limitations. The [demo checklist](../docs/DEMO_WALKTHROUGH.md) covers what to verify in the running app.
