# Personal Workspace

A local, single-user productivity workspace for the Bocconi Software Engineering (20875)
student project. Built with Python 3.12, Streamlit, SQLite and Plotly.

**MVP implementation stage:** task management, date-specific availability, a weekly
heuristic planner and a connected dashboard are implemented. Core tests pass in
the provided development environment. Browser appearance and user interactions
still require local checks before declaring the final submission complete.

## What it does

- **Dashboard:** open task count, remaining minutes, completion percentage among
  tasks **due Monday–Sunday of the current week** (N/A when none), today's focus,
  overdue and upcoming deadlines, planned-versus-available chart, and an insight
  based on actual deadline shortfalls.
- **Tasks & Projects:** create, filter, edit, complete, reopen and explicitly
  confirm permanent deletion. "Projects" are simple category labels.
- **Smart Planner:** save daily minutes for this exact calendar week, then allocate
  incomplete tasks between today and Sunday. The deadline-first, priority-aware
  algorithm may split work across days. It reports overdue work, deadline-capacity
  shortfalls, and backlog outside this week's plan separately.

**Important:** A plan is a suggestion. It does not automatically reduce a task's
remaining work. After doing work, change "Remaining minutes" or mark the task
completed yourself. The planner is a deterministic greedy heuristic, **not** a
promise of optimality or feasibility after Sunday.

## Run on Windows (from the existing checkout)

Open PowerShell in `C:\Users\Win\OneDrive\Desktop\personal-workspace`:

```powershell
cd C:\Users\Win\OneDrive\Desktop\personal-workspace
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the URL shown by Streamlit (often `http://localhost:8501`; 8502 is fine too).
Stop the app with **Ctrl+C** in PowerShell.

For a new machine, install Python 3.12, create `.venv`, then:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m streamlit run app.py
```

`sqlite3` is part of Python. No SQLite package, database server, account, cloud
service, or calendar integration is needed.

## Applying the MVP update ZIP without losing work

This is an **overlay update**, not a new repository. Downloading the ZIP does
**not** install it. Extract it and copy its contents into your **existing**
`personal-workspace` folder, preserving the directory structure. Allow replacing
matching **source files** (`workspace/`, `tests/`, `README.md`, etc.). The ZIP
contains **no** `.git`, `.venv`, or `data/workspace.db` files.

Recommended Git steps **before** extracting, assuming a clean `main`:

```powershell
git status -sb
git switch -c feat/mvp-integration
```

With the downloaded `personal-workspace-mvp-update.zip` in Windows Downloads,
while PowerShell is in your **existing project directory**:

```powershell
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\personal-workspace-mvp-update.zip" -DestinationPath . -Force
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m streamlit run app.py
```

If the browser saved the ZIP somewhere else, change just the path before
`-DestinationPath`. Alternatively, right-click ZIP > Extract All into a temporary
folder, **open that extracted folder**, then copy the files **inside** it into
your original project, choosing to replace matching source files. Do **not**
copy into a second `personal-workspace` subfolder.

The original database stays at `data/workspace.db`; schema initialization adds
only the `daily_availability` table. Back up your personal DB before the first
run as an additional precaution, particularly before a deadline.

## Safe demo database

Generate an **independent** sample database, without modifying your tasks:

```powershell
.\.venv\Scripts\python.exe -m scripts.create_demo_db
$env:WORKSPACE_DB_PATH = (Resolve-Path ".\data\demo-workspace.db").Path
.\.venv\Scripts\python.exe -m streamlit run app.py
```

The generator refuses to overwrite an existing database file or the active
personal DB path. It creates `data/demo-workspace.db` instead; the `data/`
folder is Git-ignored. When finished, stop Streamlit with Ctrl+C, and **in the
same PowerShell window** clear the demo override:

```powershell
Remove-Item Env:WORKSPACE_DB_PATH
```

Then launch normally to see your personal tasks again. **Do not delete your
personal `data/workspace.db`.** For a fixed-date core logic demo use:
`python -m scripts.create_demo_db --today 2026-11-11 --output <different-path>`.
The live Streamlit UI uses the computer's *real* current date, so use the normal
(today-based) demo for its visual walkthrough.

## Tests and quality

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m scripts.check_ui
```

The last command uses Streamlit's page test harness on a disposable DB and is an
**additional smoke check**, not a substitute for testing browser forms and page
switching. Follow [the manual checklist](docs/DEMO_WALKTHROUGH.md) as well.
Record actual results on your machine in `docs/TEST_REPORT.md`.

On the team's successful Windows Python 3.12 environment, capture installed
dependency versions for reproducibility:

```powershell
.\.venv\Scripts\python.exe -m pip freeze > requirements-lock.txt
```

Review the generated lock file before committing it (avoid unrelated packages
from an old environment); repeat an install in a clean virtual environment
using the same lock file. A verified Windows lock and clean-install result
are **not** included in this update.

## Architecture and planner policy

| File | Role |
| --- | --- |
| `app.py`, `.streamlit/config.toml` | Navigation and dark visual theme |
| `workspace/views/` | Three Streamlit pages (presentation and forms) |
| `workspace/models.py` | Immutable task objects, validation, edit semantics |
| `workspace/repository.py` | SQLite CRUD, additive availability schema |
| `workspace/planner.py` | Pure, deterministic allocations and residuals |
| `workspace/metrics.py` | Pure dashboard statistics and insight |
| `workspace/overview.py` | One shared DB-read and recompute path for planner/dashboard |
| `scripts/` | Isolated demo generator and optional UI smoke check |
| `tests/` | Task, planning, metrics, persistence, migration and integration tests |

See [algorithm and implementation notes](docs/MVP_IMPLEMENTATION.md),
[original detailed design contract](docs/DESIGN.md),
[demo and UI checklist](docs/DEMO_WALKTHROUGH.md), and
[test record](docs/TEST_REPORT.md).

## Academic scope check

The public course listing for 20875 (2026–2027) warns that its detailed profile
refers to the prior year. The public profile mentions lecturer approval and
practical open-source projects, but it is **not** confirmation that a standalone
Streamlit app is approved for the current assignment. Verify the current
Blackboard/project instructions and the lecturer's approval, the presentation
requirements, the exact deadline, group rules and any AI-use rules. The
November 27, 2026 project date is supplied by the students, not verified online.

This app intentionally excludes authentication, cloud sync, integrations,
recurring tasks, chatbots, drag-and-drop, and complex scheduling optimization.
