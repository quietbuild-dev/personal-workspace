# Testing notes

We use **pytest** for automated checks and **Ruff** for linting. The main coverage includes task persistence, progress tracking, time constraints, dependencies, scheduling proposals, SQLite transactions, Undo, and selected Streamlit interactions.

## How to run the checks

From the project root in Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m ruff check .

$testDir = Join-Path $env:TEMP ("pw-tests-" + [guid]::NewGuid().ToString("N"))
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp "$testDir"

.\.venv\Scripts\python.exe -m scripts.check_optimizer_ui
```

The temporary base directory keeps test artifacts separate from personal workspace data. Some UI tests use simulated Streamlit interactions; a manual browser check remains necessary.

## Verification record

- **27 November 2026:** The earlier full suite passed **385 tests and 58 subtests**.
- **After the last Home/checklist changes:** The targeted regression suite passed **20 tests**.

These runs were on different revisions. The complete suite should be rerun on the final commit before reporting a final project-wide result.

## Evaluating the scheduler

The [optimizer evaluation](OPTIMIZER_EVALUATION.md) uses fixed synthetic scenarios and records both the CP-SAT optimizer and the greedy baseline. The original measurement data is in [optimizer-benchmark.csv](optimizer-benchmark.csv). Results describe those workloads, not all possible student schedules.

For a practical click-through checklist, see [Demo walkthrough](DEMO_WALKTHROUGH.md).
