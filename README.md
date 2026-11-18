# Personal Workspace

A local planner for students who need to fit study time around lectures, appointments, and everything else in a week. We built it for Bocconi's Software Engineering course (20875) using Python, Streamlit, and SQLite.

The main idea is simple: a deadline tells you *when* work has to be finished, but not *when* you'll actually do it. Personal Workspace suggests study blocks, checks them against your calendar, and lets you review changes before saving them.

## What you can do

- **Keep track of work.** Add assignments and to-dos with deadlines, priorities, categories, time estimates, and checklists. Small errands can stay as to-dos without being scheduled.
- **See your week.** Switch between day and week views. Lectures, social plans, exercise, personal events, and study sessions have different colors; task priority is shown separately.
- **Set study preferences.** Choose an earliest start, latest finish, and maximum study hours for a day. The planner works around fixed events rather than placing study sessions on top of them.
- **Update progress.** Complete checklist items, mark a session done or missed, or record partial work. You can inspect the assignment and its subtasks from a calendar session.
- **Rescue a disrupted week.** Compare a plan that changes as little as possible with one that makes more room for unfinished work. Review the Before/After calendars and decide whether to accept the changes.
- **Try a what-if scenario.** Check how losing some study time would affect the plan without changing the saved calendar.
- **Undo an accepted plan.** Restore the previous set of study sessions when nothing important has changed since acceptance. If undo would overwrite newer work or introduce a conflict, the app refuses it.

## How scheduling works

Study sessions are generated from unfinished work, deadlines, daily study limits, preferred hours, and fixed commitments. The planner uses a deterministic, constraint-aware heuristic; it does **not** claim to find a mathematically optimal schedule.

The interesting part is replanning. When something changes, the app can preserve valid existing sessions and move only what needs moving, or rebuild the remaining week to fit more work. Suggestions are previews until the user accepts them. Acceptance checks the latest saved data so an outdated proposal cannot silently replace a newer plan.

The two strategies can also be compared using the included synthetic benchmark (see `docs/RESCUE_MY_WEEK.md`).

## Run locally

The application runs on your computer. There is no account or hosted server to set up.

**Requirements:** Python 3.12 and Git. On Windows, open PowerShell and run:

```powershell
# Clone the repository (requires access to this private repo)
git clone https://github.com/quietbuild-dev/personal-workspace.git
cd personal-workspace

# Create the environment and install dependencies
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# Start the app
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the local address Streamlit prints in the terminal (usually `http://localhost:8501`). Stop the app with `Ctrl+C`.

### Try the sample workspace

On Windows, after installing dependencies, run:

```powershell
& ".\Launch Calendar V3 Demo.bat"
```

Despite the launcher name, it starts the **Calendar V4** code, normally at `http://localhost:8503`. The demo uses its own SQLite database (`data/calendar-v3-demo.db`) and does not use your personal `data/workspace.db`. If you want a fresh demo, reset only the demo database, never the personal one.

## Tests

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.check_ui
```

At the Calendar V4 checkpoint, **150 tests and 58 subtests passed**, Ruff and formatting were clean, and the Home/Calendar smoke checks passed on Windows. The smoke check is not a substitute for clicking through the app in a browser.

For a repeatable comparison of the two replanning strategies:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_rescue --repeats 30
```

## Where the code lives

| Path | Role |
| --- | --- |
| `app.py` | Streamlit entry point and page navigation |
| `workspace/views/home.py` | Tasks, deadlines, checklists, and today's focus |
| `workspace/views/week.py` | Calendar, events, study preferences, and schedule review |
| `workspace/views/weekly_calendar.py` | Day/week calendar rendering |
| `workspace/views/schedule_comparison.py` | Before/After schedule comparison |
| `workspace/advanced_planner.py` | Scheduling rules and proposal generation |
| `workspace/planning_insights.py` | Replanning strategies, comparisons, and risk summaries |
| `workspace/advanced_repository.py` | SQLite persistence, accepted plans, and safe undo |
| `workspace/quick_tasks.py` | Task creation, editing, and optional scheduling |
| `tests/` and `scripts/` | Automated tests, demos, and evaluation scripts |

More implementation notes are in `docs/RESCUE_MY_WEEK.md` and `docs/CALENDAR_V4_RELEASE.md`.

## Current scope

This is a local, single-user university project, not a calendar service. It has no cloud sync, Google Calendar integration, collaboration inside the app, or guaranteed optimal scheduling. Some UI details still need refinement, but the core task, scheduling, replanning, and persistence flows are implemented and covered by automated tests.

Personal SQLite databases, virtual environments, and local secrets are excluded from Git. If you work on the project with someone else, share code through GitHub rather than exchanging database files.
