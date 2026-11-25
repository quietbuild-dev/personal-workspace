# Personal Workspace

Personal Workspace is a local study planner built for Bocconi's Software Engineering course (20875). We wanted a way to turn a list of deadlines into an actual plan for the week, without having to rearrange every study session by hand when something changes.

The app is written in Python 3.12, with Streamlit for the interface and SQLite for local data. It uses a dark **Smoky Lavender** design and has a Windows desktop launcher, so it can open in its own window instead of a normal browser tab.

## What it does

- **Home:** see what needs attention today, upcoming deadlines, priorities, progress, and recently completed work.
- **Tasks:** create assignments and quick to-dos, set deadlines and priorities, and track checklists and remaining work. Not every to-do has to become a study session.
- **Calendar:** view lectures, appointments, personal plans and scheduled study blocks by day or week. Open a session to see its linked assignment and record progress.
- **Study preferences:** set an earliest start, latest finish and maximum study hours for a day. Fixed commitments are taken into account when suggesting study times.
- **Rescue My Week:** choose deadlines, important tasks, routine, total work or workload balance. Compare goal previews and review the Before/After timetable before approval.
- **Prerequisites:** define which tasks must come first; the planner checks task dependencies without marking reserved work complete.
- **What-if and undo:** preview the effect of losing study time without changing saved data; undo the most recent accepted plan when restoration is still safe.

The interface is intended to stay simple for everyday tasks, while detailed task and planning controls remain available under **Advanced**.

## The scheduling part

The scheduling engine works with deadlines, remaining work, daily study limits, preferred hours and fixed calendar events. Rescue My Week uses a bounded OR-Tools CP-SAT optimizer, with the original deterministic greedy heuristic as its baseline and fallback. Optimality is reported only when all objective levels are proved for the modeled week.

Replanning is the main engineering focus. Five objective profiles make different trade-offs between deadlines, priority, routine, throughput and peak daily workload. Proposed changes are not saved automatically. Before accepting a plan, the application checks it against the latest database state; undo also checks whether restoring the previous sessions is safe.

See the [mathematical model and safe review guide](docs/GOAL_BASED_OPTIMIZER.md) and [experimental evaluation](docs/OPTIMIZER_EVALUATION.md). The benchmark in `scripts/evaluate_optimizer.py` compares both greedy strategies with all five goals. Install the updated requirements to enable OR-Tools.

## Run it on Windows

You'll need **Python 3.12** and **Git**. From PowerShell:

```powershell
git clone https://github.com/quietbuild-dev/personal-workspace.git
cd personal-workspace
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

### Desktop window (recommended on Windows)

Run this once to create a **Personal Workspace** shortcut on your desktop:

```powershell
& ".\Create Desktop Shortcut.bat"
```

Then double-click the shortcut. It opens a separate Edge/Chrome application window without a visible terminal. A local Streamlit server still runs in the background and closes with the app window. This is a Windows launcher, **not** a standalone installer or an online service. The project folder and Python environment must remain available.

See `docs/DESKTOP_LAUNCHER.md` for details and troubleshooting.

### Run in a browser instead

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the local URL shown in PowerShell (usually `http://localhost:8501`). Keep the terminal running while using the app, and press `Ctrl+C` to stop it.

### Sample workspace

```powershell
& ".\Launch Calendar V3 Demo.bat"
```

Despite the older launcher name, this runs the current interface with sample data, usually at `http://localhost:8503`. It uses a separate demo database (`data/calendar-v3-demo.db`), not your personal `data/workspace.db`. Do not delete or overwrite your personal database when resetting a demo.

On macOS, the Python/Streamlit application can be run from a virtual environment, but the Windows desktop shortcut is not supported. macOS desktop packaging has not been tested.

## Testing

On the Windows development setup:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.check_ui
```

The optimizer checkpoint passes **209 tests and 58 subtests**, lint, formatting,
and Home/Calendar smoke checks. `scripts.check_optimizer_ui` also exercises goal
preview/comparison, approval, Undo and prerequisite editing on temporary data.
The Windows desktop launcher has not been manually retested for this upgrade.

To reproduce the seven-method comparison on 15 synthetic scenarios:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_optimizer --repeats 3 --time-limit 1 --csv docs/optimizer-benchmark.csv
```

## Project structure

| Path | Purpose |
| --- | --- |
| `app.py` | App entry point and navigation |
| `workspace/theme.py` | Smoky Lavender styling |
| `workspace/views/home.py` | Home, focus tasks and deadlines |
| `workspace/views/task_board.py` | Everyday Tasks page |
| `workspace/views/week.py` | Calendar, preferences, session actions and replanning |
| `workspace/views/weekly_calendar.py` | Calendar rendering |
| `workspace/views/schedule_comparison.py` | Before/After schedule comparison |
| `workspace/advanced_planner.py` | Greedy baseline and independent constraints |
| `workspace/optimizer.py` | CP-SAT model and five objective profiles |
| `workspace/dependencies.py` | Dependency graph and precedence validation |
| `workspace/conflict_analysis.py` | Calculated capacity bounds and suggestions |
| `workspace/planning_insights.py` | Replanning comparisons and risk summaries |
| `workspace/advanced_repository.py` | SQLite operations, plan acceptance and undo |
| `workspace/quick_tasks.py` | Task creation, editing and optional scheduling |
| `scripts/launch_desktop.py` | Windows desktop-window launcher |
| `tests/`, `scripts/` | Tests, demos and evaluation |

Additional notes are in `docs/`, especially `RESCUE_MY_WEEK.md`, `FINAL_UI_POLISH.md` and `DESKTOP_LAUNCHER.md`.

## Scope and limitations

This is a **local, single-user course project**. It has no accounts, cloud synchronization, external calendar integration, or guaranteed optimal scheduling. SQLite data stays on the user's computer; personal databases, virtual environments and local secrets should not be committed to Git. The project is shared through GitHub, not through the app itself.
