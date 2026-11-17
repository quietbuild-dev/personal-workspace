# Personal Workspace

A local-first **student planning system** for Bocconi Software Engineering
(20875). Built with Python 3.12, Streamlit, SQLite and Plotly. Its technical
contribution is constraint-aware weekly scheduling and reviewable replanning,
not merely a calendar interface.

## Home + Calendar — simpler everyday interface

The app has two main pages: **Home** (today's agenda, tasks, deadlines and
optional scheduling suggestions) and **Calendar** (Day/Week views, events,
saved assignment-specific study blocks, and schedule review).

**Tasks** have a title, optional due date and time (DD/MM/YYYY and HH:MM),
category, priority, and estimated hours/minutes. Only the title requires manual
input. Categories include useful defaults and reusable custom entries. Tasks
may contain ordinary checklist items. Done and Partly are available directly
from the list; detailed remaining-work controls appear only when needed.

**Events** are lectures, appointments, exercise, social and personal plans.
They have selectable start/end times and colored calendar blocks. Clicking an
event opens editing; clicking a study block opens its associated assignment,
checklist, and appropriate Done/Partially done/Missed/Reschedule options.

**Suggestions** appear after creating a task when eligible study preferences
are configured. Choose daily study hours/minutes and a preferred part of the
day for one date or the remaining week. The app finds gaps around events. You
can adjust a suggested block, accept the week, or dismiss the proposal. **No
accepted calendar changes without approval.** The greedy algorithm is
constraint-aware but not globally optimal.

Existing task data, detailed study steps, schedules, and the older planner are
preserved but the legacy controls are no longer displayed in everyday pages.
See [Product UX release](docs/PRODUCT_UX_RELEASE.md) for the exact behavior,
new SQLite tables, limitations, and the browser acceptance checklist, plus
[advanced architecture](docs/ADVANCED_MILESTONE.md) for scheduling details.

## Run on Windows

From the **existing** project directory:

```powershell
cd C:\Users\Win\OneDrive\Desktop\personal-workspace
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the URL printed by Streamlit, normally `http://localhost:8501` (8502 is
also fine). Stop with Ctrl+C. You can also use `Launch Personal Workspace.bat`
from the advanced milestone for double-click launching.

Fresh setup with Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## Safe update / existing database

An update ZIP is an **overlay**, not a replacement repository. Download it,
extract its **contents** into your existing `personal-workspace` folder, and
allow matching source files to be replaced. Downloading alone doesn't install
anything. The ZIP includes **no** SQLite database, virtual environment, or
Git history. Back up your own `data/workspace.db` before installing as an extra
safeguard.

The additive tables `quick_task_links`, `day_study_budgets`,
`task_deadline_times`, `task_categories`, `fixed_event_kinds`, and
`day_focus_preferences` are created on first use without rewriting existing
task records. Existing task, availability, event and accepted-session tables
are retained. Deleted tasks cascade to their own study steps and session
records as before; deletion requires confirmation in the UI.

To run a separate demonstration database, without touching personal tasks:

```powershell
.\.venv\Scripts\python.exe -m scripts.create_advanced_demo --output data/study-demo.db
$env:WORKSPACE_DB_PATH = (Resolve-Path '.\data\study-demo.db').Path
.\.venv\Scripts\python.exe -m streamlit run app.py
# After stopping the demo, restore the normal database in that PowerShell window:
Remove-Item Env:\WORKSPACE_DB_PATH
```

The demo command refuses to overwrite an existing file; use a new name if
`data/study-demo.db` already exists.

## Checks before pushing to GitHub

```powershell
.\.venv\Scripts\python.exe -m ruff check --fix .
.\.venv\Scripts\python.exe -m ruff format .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m scripts.check_ui
```

The assistant's Python 3.13 environment passed **126 automated Python tests
and 49 subtests**, including the previous 113. A standalone Chromium calendar
alignment check passed. Ruff and actual Streamlit smoke/browser checks could
not be run here because their packages were unavailable; run them locally on
Python 3.12 and use the checklist in
[docs/PRODUCT_UX_RELEASE.md](docs/PRODUCT_UX_RELEASE.md). Do not merge until
all local checks pass.

## Key modules

| Module | Purpose |
| --- | --- |
| `app.py` | Two-page Home and Calendar navigation |
| `workspace/views/home.py` | Today's agenda, task entry, actions, custom categories and suggestions |
| `workspace/views/week.py` | Browsable Day/Week calendar, events, study preferences and progress |
| `workspace/views/weekly_calendar.py` | Aligned, colored, clickable day/week HTML calendar |
| `workspace/models.py` | Immutable tasks and validation |
| `workspace/repository.py` | Legacy SQLite task persistence and daily availability |
| `workspace/advanced_repository.py` | Study steps, daily budgets, fixed events, accepted schedule, atomic approval |
| `workspace/advanced_planner.py` | Pure deterministic scheduling and validation |
| `workspace/quick_tasks.py` | Additive quick-task linkage and atomic lifecycle |
| `workspace/simple_planning.py` | Read-only proposal summary for Home and Calendar |
| `workspace/manual_planning.py` | Validate a user's proposed time changes without saving |
| `workspace/overview.py`, `workspace/metrics.py` | Shared saved-data calculations |
| `tests/`, `scripts/` | Regression tests and safe demo/UI smoke utilities |

## Course submission status

Functional automated tests are not equivalent to course approval. Confirm the
2026 course rubric, lecturer approval, teamwork/AI policies, project deadline,
and presentation instructions. The supplied deadline is **November 27, 2026**.
No authentication, cloud sync, calendar integrations, chatbot, drag-and-drop or
complex optimal scheduling is planned for this version.
