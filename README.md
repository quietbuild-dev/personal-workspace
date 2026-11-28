# Personal Workspace

*A task list tells you what needs to be done. We wanted to figure out when to do it, too, based on your preferences.*

**Personal Workspace** is a local planning app we built for **Software Engineering (20875)**. It brings tasks, deadlines, calendar events, and progress tracking into one place, but the main idea goes beyond organization: **turning a to-do list into a realistic schedule that fits your life.**

Instead of manually fitting assignments around lectures, appointments, and other commitments, the planner considers your available time, deadlines, priorities, and preferences to suggest when to study. You can explore different scheduling goals, compare the results, and choose which plan to save to your calendar.

**Built with:** Python 3.12, Streamlit, SQLite, Google OR-Tools CP-SAT, and Plotly.

## What you can do

- **Home â€” The bigger picture.** See what matters today: upcoming deadlines, priorities, remaining workload, and recent progress. No digging through endless task lists.

- **Tasks â€” Not everything is just done or not done.** Organize tasks by deadline, priority, and estimated effort. Tick off quick to-dos, track longer assignments with a progress bar, or break them into subtasks. Finishing the last subtask can automatically complete the parent task, provided no required work remains.

- **Calendar â€” See where your time actually goes.** Keep lectures, appointments, and study sessions together. Switch between day and week views, create recurring events, and import or export `.ics` files.

- **Settings & Personalization â€” Plan around your study style.** Set when you study best, how long you like to focus, whether you prefer an evenly spread workload, and how flexible your study times are. You can also choose your preferred breaks and daily study hours. These preferences guide scheduling suggestions, while deadlines and fixed commitments come first.

- **Smart Planner â€” Five goals, different ways to plan your week.** Our optimizer finds study slots around existing commitments, taking deadlines, priorities, available hours, and task dependencies into account. Choose what matters most, compare proposed schedules, and decide which one to save. If everything doesn't fit, the planner shows what's left out instead of pretending there are more hours in the day.

- **Weekly review â€” Planned vs. actual.** Look back at your week and compare completed work with what was originally scheduled.

## The interesting part: making a plan that doesn't cheat

Putting tasks on a calendar is easy. Making sure they actually fit is where things get interesting.

Our planner uses **Google OR-Tools CP-SAT**, a constraint-based optimization solver that accounts for study hours, deadlines, existing commitments, task dependencies, and personal preferences. When there isn't enough time, it shows what couldn't be scheduled rather than ignoring the constraints.

Since there's no single *best* schedule for everyone, we implemented **five optimization goals**: meeting deadlines, prioritizing important tasks, preserving existing plans, maximizing scheduled work, and balancing the workload. We also built a **greedy scheduling algorithm** as a simpler baseline and fallback.

Another challenge was **safe replanning**. You can compare proposed schedules before accepting one, and the app checks the constraints again before saving in case the underlying data has changed. Accepted plans also come with a guarded **Undo**.

We keep **progress tracking separate from scheduled work**, too. Updating a progress bar shouldn't silently change the amount of work left for the planner.

The goal isn't a perfect week. It's a realistic plan, clear trade-offs, and the freedom to choose what works for you.

## Run it locally

Personal Workspace runs on your computer, with no account or cloud service required to use it.

You'll need **Python 3.12** and **Git**.

### Windows

Open PowerShell:

```powershell
git clone https://github.com/quietbuild-dev/personal-workspace.git
cd personal-workspace
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

**Option 1: Run in your browser**

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the local address shown in the terminal (usually `http://localhost:8501`). Press **Ctrl+C** to stop the app.

**Option 2: Run as a desktop app**

Prefer a dedicated window instead of another browser tab?

Run `Create Desktop Shortcut.bat` once, then launch **Personal Workspace** from your desktop.

This uses **pywebview and Microsoft Edge WebView2** to display the same application in its own window. It's not a standalone `.exe`, so the Python environment is still required.

See the [desktop launcher guide](https://github.com/quietbuild-dev/personal-workspace/blob/main/docs/DESKTOP_LAUNCHER.md) for details.

### macOS

The browser version should also work on macOS. Open Terminal:

```bash
git clone https://github.com/quietbuild-dev/personal-workspace.git
cd personal-workspace
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m streamlit run app.py
```

Open the local address shown in Terminal.

**Note:** Personal Workspace was originally developed and tested on Windows, but the Streamlit application has also been successfully run on macOS through a web browser at http://localhost:8501. The dedicated desktop launcher is currently available only for Windows. macOS does not have a dedicated desktop launcher, but users can access the application through their browser after starting the Streamlit server.

### Just want to try it out?

On Windows, run `Launch Sample Workspace.bat` to explore the app with sample tasks and events.

The demo uses a **separate database**, so your personal workspace stays untouched.

## Tests

We use **pytest** for automated tests and **Ruff** for code quality checks. Our tests cover task management, database operations, scheduling constraints, plan generation, and UI behavior. There's also a separate check for the optimizer's integration with the interface.

To run the checks on Windows, open PowerShell in the project folder:

```powershell
.\.venv\Scripts\python.exe -m ruff check .

$testDir = Join-Path $env:TEMP ("pw-tests-" + [guid]::NewGuid().ToString("N"))
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp "$testDir"

.\.venv\Scripts\python.exe -m scripts.check_optimizer_ui
```

We also **evaluated the CP-SAT optimizer against the greedy baseline**, looking at how different scheduling goals affect the resulting plans.

The methodology and results are in our [Optimizer Evaluation](https://github.com/quietbuild-dev/personal-workspace/blob/main/docs/OPTIMIZER_EVALUATION.md).

## Where to look in the code

We kept the interface, scheduling logic, and database code separate, so they're easier to work on and test.

| Location | What's inside |
| --- | --- |
| `app.py` | Starts the app and sets up navigation |
| `workspace/views/` | Code for Home, Tasks, Calendar, and Settings |
| `workspace/optimizer.py` | The **CP-SAT scheduler** and its five planning goals |
| `workspace/advanced_planner.py` | Our **greedy planner** and scheduling checks |
| `workspace/advanced_repository.py` | Saving data in SQLite, approving plans, and Undo |
| `tests/` | Tests for tasks, scheduling, and other app behavior |
| `docs/` | More on the algorithms, design, and evaluation |

### A closer look at the algorithms

- [**Goal-Based Optimizer**](https://github.com/quietbuild-dev/personal-workspace/blob/main/docs/GOAL_BASED_OPTIMIZER.md) â€” How we model scheduling constraints and implement the five optimization goals.

- [**Optimizer Evaluation**](https://github.com/quietbuild-dev/personal-workspace/blob/main/docs/OPTIMIZER_EVALUATION.md) â€” How we compare the algorithms and evaluate their results.

## Scope & limitations

We built Personal Workspace as a **local, single-user application**, focusing on useful scheduling rather than building another large productivity platform.

There are no user accounts, cloud sync, or collaboration features. Calendar import and export use `.ics` files, not a live Google Calendar or Outlook connection.

The planner works within a **weekly planning horizon**. It may produce a partial schedule when time is limited, and CP-SAT does not guarantee a globally optimal result on every run.

Personal databases and virtual environments are excluded from the source-code submission.
