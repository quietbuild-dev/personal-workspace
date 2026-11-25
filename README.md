# Personal Workspace

**A local study planner that turns deadlines into a realistic weekly schedule.**

We built Personal Workspace for Bocconi's Software Engineering course (20875). A list of assignments tells you *what* needs to get done, but not necessarily *when* you'll find time for it. Our app combines tasks, calendar commitments, and study preferences to suggest a plan—and helps you revise that plan when your week changes.

The application is written in **Python 3.12**, with **Streamlit** for the interface, **SQLite** for local storage, **OR-Tools CP-SAT** for constraint-based scheduling, and **pywebview/WebView2** for its Windows desktop window. The interface uses a dark *Smoky Lavender* theme.

## Features

- **Home:** See today's priorities, upcoming deadlines, progress, and recently completed work.
- **Tasks:** Create assignments and quick to-dos, choose priorities and deadlines, set estimated work, and manage categories, checklists, and subtasks. Multiple subtasks can be added at once. Not every to-do has to become a study session.
- **Calendar:** View lectures, appointments, personal events, and study sessions in day or week view. Open study sessions to check their linked tasks and record progress.
- **Plan My Week:** Generate a proposed weekly study schedule from Home or Calendar. Review it before anything is saved.
- **Rescue My Week:** When plans change, compare five scheduling goals: **Meet my deadlines**, **Focus on important tasks**, **Keep my routine**, **Get as much done as possible**, and **Balance my workload**.
- **Constraints and prerequisites:** Set preferred study hours and a maximum daily workload. Fixed commitments block unavailable time, and task dependencies determine which work must come first.
- **Review, what-if, and Undo:** Inspect a Before/After timetable, test reduced availability without changing saved data, approve a feasible proposal, and safely undo the latest accepted plan when possible.
- **Calendar export:** Download accepted study sessions and fixed events for the selected week as an `.ics` file for import into calendar applications. This is a one-time export, **not** live synchronization.

Everyday controls are kept simple; more detailed scheduling and task settings are available under **Advanced**.

## How scheduling works

The planner uses remaining task effort, deadlines, priorities, dependencies, fixed calendar events, preferred hours, and daily study limits to build feasible study sessions.

The central engineering feature is **constraint-aware replanning**, rather than the calendar interface itself. We use a bounded **OR-Tools CP-SAT** model with five objective profiles. Each profile makes a different trade-off between urgency, importance, preserving an existing plan, total scheduled work, and workload distribution. A deterministic greedy planner provides a baseline and fallback.

The optimizer also uses tie-breaking preferences to discourage very short study fragments (under 25 minutes) and excessive movement of existing sessions. These are **soft preferences**: a shorter session can still be proposed when necessary. The stability metric estimates how far preserved sessions move, not just how many are affected.

**Proposals are not applied automatically.** Before approval, the app validates hard constraints and rechecks the current SQLite state so that an outdated preview cannot silently replace newer work. Undo has its own safety checks. A feasible partial plan is possible; meeting every deadline or proving a globally optimal plan is **not guaranteed**.

For more detail, see [the optimizer model](docs/GOAL_BASED_OPTIMIZER.md), [the evaluation](docs/OPTIMIZER_EVALUATION.md), and [the final experience update](docs/FINAL_EXPERIENCE_UPGRADE.md).

## Run on Windows

Install **Python 3.12** and **Git**, then open PowerShell:

```powershell
git clone https://github.com/quietbuild-dev/personal-workspace.git
cd personal-workspace
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

### Desktop window

Create a desktop shortcut once:

```powershell
& ".\Create Desktop Shortcut.bat"
```

Then double-click **Personal Workspace** on your desktop. The Windows launcher uses **pywebview with the Edge WebView2 runtime** to display the app in its own window, without a normal Edge browser profile or extensions. A **local Streamlit server runs in the background** and is stopped when the window closes.

This is **not** a packaged standalone `.exe`: the project folder, Python virtual environment, and WebView2 runtime are still required. See [desktop setup and troubleshooting](docs/DESKTOP_LAUNCHER.md). The desktop window should be checked on each target Windows installation.

### Browser option

You can also run the same app in a regular browser:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the local URL shown in PowerShell (usually `http://localhost:8501`). Keep the terminal open; press **Ctrl+C** to stop the server.

### Sample workspace

To explore the app without changing your own tasks:

```powershell
& ".\Launch Calendar V3 Demo.bat"
```

Despite the older launcher filename, this opens the current application using a separate demo database, normally at `http://localhost:8503`. **Do not delete or overwrite `data/workspace.db`** when resetting demo data.

On macOS, the Streamlit application can run in a browser with an appropriate Python environment; the Windows desktop shortcut is not supported.

## Testing and evaluation

The latest Windows development run on **November 25, 2026** completed **222 tests and 58 subtests**, with Ruff linting and formatting checks passing.

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .

$testDir = Join-Path $env:USERPROFILE ("Downloads\pw-tests-" + [guid]::NewGuid().ToString("N"))
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp "$testDir"

.\.venv\Scripts\python.exe -m scripts.check_optimizer_ui
```

To repeat the synthetic comparison of greedy baselines and the five optimizer goals:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_optimizer --repeats 3 --time-limit 1 --csv docs/optimizer-benchmark.csv
.\.venv\Scripts\python.exe -m scripts.summarize_optimizer_benchmark --csv docs/optimizer-benchmark.csv
```

The benchmark measures feasible scheduled work, constraint violations, goal-specific outcomes, and disruption; it does not prove that every optimizer run is optimal. The full results and methodology are described in [`docs/OPTIMIZER_EVALUATION.md`](docs/OPTIMIZER_EVALUATION.md).

## Project structure

| Path | Purpose |
| --- | --- |
| `app.py` | Application entry point and navigation |
| `workspace/views/` | Home, task management, calendar, and schedule previews |
| `workspace/advanced_planner.py` | Greedy scheduling baseline and constraint checks |
| `workspace/optimizer.py` | CP-SAT model and goal-based scheduling |
| `workspace/dependencies.py` | Task prerequisites and cycle validation |
| `workspace/conflict_analysis.py` | Scheduling conflicts and available-capacity analysis |
| `workspace/schedule_quality.py` | Study-session fragmentation and schedule stability metrics |
| `workspace/calendar_export.py` | Read-only `.ics` calendar export |
| `workspace/advanced_repository.py` | SQLite operations, proposal approval, and safe Undo |
| `scripts/launch_desktop.py` | Windows desktop launcher with embedded WebView2 |
| `scripts/` and `tests/` | Demos, benchmarks, smoke checks, and automated tests |
| `docs/` | Technical explanations, evaluation, and launcher instructions |

## Scope and limitations

Personal Workspace is a **local, single-user course project**. It has no accounts, cloud synchronization, collaborative editing, or live external-calendar integration. The scheduling horizon is a week, and the solver may return a feasible partial plan rather than a fully completed or proven-optimal one.

Personal SQLite databases, virtual environments, and local secrets should stay out of Git. Share source code through this repository, not personal database files.
