# Personal Workspace

*A task list tells you what needs doing. We wanted to figure out when to do it, too.*

Personal Workspace is a local planning app we built for **Software Engineering (20875) at Bocconi University**. It brings tasks, deadlines, calendar events and study time into one place. Instead of manually fitting every assignment around lectures and other plans, you can ask it to suggest a week that actually fits your available time.

It's a single-user app written in **Python 3.12**, with **Streamlit** for the interface, **SQLite** for storage, **OR-Tools CP-SAT** for scheduling and **Plotly** for charts. On Windows, it can also open in its own desktop window using pywebview/WebView2.

## What you can do

- **Home:** See today's focus, upcoming deadlines, remaining workload and recent progress without digging through the whole task list.
- **Tasks:** Add assignments or quick to-dos, set deadlines and priorities, and choose how to track each task: a simple Done checkbox, a manual progress bar or completed subtasks.
- **Calendar:** Keep fixed commitments and study sessions together, with day/week views, recurring events and one-time `.ics` import/export.
- **Plan or rescue your week:** Generate a study plan, then compare alternatives if deadlines, priorities or available hours change. Nothing is saved until you approve it.
- **Adjust to your day:** Use Today's Energy to try shorter or longer focus blocks. There are also workload summaries and a weekly review to compare planned work with actual progress.

## The interesting part: making a plan that doesn't cheat

The planner has to work around lectures and appointments, stay within available study hours, respect task deadlines and prerequisites, and avoid overlapping sessions. It also has to admit when there simply isn't enough time.

We use a **constraint-based optimizer** with five planning goals: meeting deadlines, prioritizing important tasks, keeping the existing routine, scheduling as much work as possible, or balancing workload across the week. A simpler greedy planner provides a fallback. The goals can produce different schedules from the same tasks because they value different trade-offs.

One problem we spent time on was **safe replanning**. A proposed timetable is only a preview: the app checks the constraints again when you approve it, because the saved tasks or calendar may have changed in the meantime. There is also a guarded Undo for accepted plans. We kept reported task progress separate from remaining scheduled work, so moving a progress bar doesn't quietly remove study time from the planner.

The aim isn't to promise a perfect schedule. It's to produce a useful one, show the compromises, and leave the final decision to the user.

## Run it locally

You'll need **Python 3.12** and **Git**. On Windows, open PowerShell:

```powershell
git clone https://github.com/quietbuild-dev/personal-workspace.git
cd personal-workspace
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Start the browser version:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the local address shown in the terminal (usually `http://localhost:8501`). Press **Ctrl+C** to stop it.

**Windows desktop option:** Run `Create Desktop Shortcut.bat` once, then open **Personal Workspace** from the desktop. This uses the installed Edge WebView2 runtime; it is not a standalone `.exe`. Setup details are in [the desktop launcher guide](docs/DESKTOP_LAUNCHER.md).

**Want to explore without entering tasks?** Run `Launch Sample Workspace.bat`. It creates/opens a separate demo database rather than your personal workspace.

## Tests

From the project folder, with the virtual environment installed:

```powershell
.\.venv\Scripts\python.exe -m ruff check .

$testDir = Join-Path $env:TEMP ("pw-tests-" + [guid]::NewGuid().ToString("N"))
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp "$testDir"

.\.venv\Scripts\python.exe -m scripts.check_optimizer_ui
```

The tests cover task management, schedule constraints, planning proposals, database operations and interface behavior. The optimizer's evaluation and benchmarks are documented separately.

## Where to look in the code

| Location | What's there |
| --- | --- |
| `app.py` | Streamlit entry point and navigation |
| `workspace/views/` | Home, Tasks, Calendar and Settings screens |
| `workspace/optimizer.py` | CP-SAT scheduling model and planning goals |
| `workspace/advanced_planner.py` | Greedy baseline and scheduling checks |
| `workspace/advanced_repository.py` | Saving plans, validation and Undo |
| `tests/` | Automated tests |
| `docs/` | Design notes, technical details and evaluations |

For a closer look at the scheduling logic, see the [optimizer model](docs/GOAL_BASED_OPTIMIZER.md) and [evaluation](docs/OPTIMIZER_EVALUATION.md).

## Limits

This is a **local, single-user university project**, not a hosted productivity service. There are no user accounts, cloud sync or collaborative features. Calendar export is a one-time file, not a live connection to Google Calendar or Outlook. The planner works within a weekly horizon and may propose a partial schedule when there isn't enough capacity; a globally optimal result is not guaranteed for every run.

Personal databases and virtual environments are not part of the source-code submission.
