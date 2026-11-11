# Personal Workspace

A small, local-first personal planning workspace for the Bocconi Software
Engineering project. Working title; choose the product name later.

**Stage:** planning and setup, November 11, 2026.
**Submission date:** November 27, 2026, as supplied in the project brief.
**Budget:** 45 combined student hours.

## What is ready

- A Streamlit entry point and three navigable screens.
- A restrained dark theme and dashboard empty states.
- Dependency files, pytest configuration, Ruff configuration, and Git ignore rules.
- A scoped [project plan](docs/PLAN.md), [technical contract](docs/DESIGN.md),
  [first implementation milestone](docs/FIRST_MILESTONE.md), and
  [testing checklist](tests/README.md).

This is a starter, not the finished application. Task forms, database access,
scheduling, metrics, and charts are deliberately not implemented yet. Dashboard
dashes mean that the data is not connected; they are not fabricated statistics.

## Start on your computer

Install Python **3.12** and Git, extract this folder, and open a terminal inside
`personal-workspace`. Both students should use Python 3.12.

Windows PowerShell, without changing execution policy:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

macOS or Linux:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m streamlit run app.py
```

Open the local URL printed by Streamlit, normally `http://localhost:8501`.
Confirm all three sidebar destinations open. Stop the server with Ctrl+C.
Always launch from the project folder so Streamlit loads `.streamlit/config.toml`.
Python's `sqlite3` module is built in; do not install an SQLite Python package.

For the examples below, `python` means the Python executable inside your `.venv`.
You may activate it with `.venv\Scripts\Activate.ps1` on Windows, or
`source .venv/bin/activate` on macOS/Linux. If PowerShell blocks activation,
keep using the explicit executable path above.

The current requirements specify compatible version ranges. After the first
successful install and launch, one student should freeze that fresh environment
and commit the resolved versions:

```bash
python -m pip freeze > requirements-lock.txt
```

The other student then installs with `python -m pip install -r requirements-lock.txt`.
Use this same lock file for the fresh-install check and future CI. Do not upgrade
dependencies during the final week without a concrete reason and rechecking the app.

```bash
python -m ruff check .
python -m ruff format --check .
```

After writing the first domain and persistence tests in the next milestone:

```bash
python -m pytest
```

There are intentionally no feature tests yet. Running pytest now will report
that no tests were collected; this is not evidence of application correctness.

## Create the shared GitHub repository

One student creates an **empty private** repository named `personal-workspace`
in their own GitHub account. Do not add a second README, license, or gitignore
on GitHub. Invite the other student as a collaborator. Revisit visibility and
licensing after checking the course's open-source requirements.

From this folder:

```bash
git init -b main
git add .
git commit -m "Set up workspace scaffold and project plan"
git remote add origin https://github.com/YOUR-USERNAME/personal-workspace.git
git push -u origin main
```

Replace `YOUR-USERNAME` with the repository owner's GitHub username. If Git asks
for identity, set your own name and email. No GitHub repository has been created
or published by this starter.

The second student clones the repository and repeats the environment setup:

```bash
git clone https://github.com/YOUR-USERNAME/personal-workspace.git
cd personal-workspace
```

## Daily collaboration

Start a small feature branch from an up-to-date `main`:

```bash
git switch main
git pull --ff-only
git switch -c feat/task-persistence
```

Keep each change small, include relevant tests, and open a pull request for the
other student to review. Merge daily when practical. Agree who edits a shared
file before working on it. Do not exchange database files or merge `.venv` folders.
Add a short note in each pull request explaining what changed and how it was checked.

Once the first meaningful tests exist, add one GitHub Actions job to install the
same dependencies and run Ruff and pytest. No deployment pipeline is needed.

## Where things go

| Path | Responsibility | Status |
| --- | --- | --- |
| `app.py` | Page configuration and navigation | Present |
| `.streamlit/config.toml` | Dark theme | Present |
| `workspace/views/` | Dashboard, tasks, and planner screens | Empty states only |
| `workspace/models.py` | Data structures and validation | Next milestone |
| `workspace/repository.py` | SQLite persistence and serialization | Next milestone |
| `workspace/planner.py` | Pure daily allocation algorithm | Planned |
| `workspace/metrics.py` | Pure dashboard calculations | Planned |
| `tests/` | Behavior and integration tests | Checklist present |
| `data/` | Local SQLite database | Created on first persistence use |
| `docs/` | Scope, contracts, milestones | Present |

Keep SQL out of views and Streamlit imports out of business logic.

## Next action

Read [FIRST_MILESTONE.md](docs/FIRST_MILESTONE.md) together. Implement one task
from validated input to SQLite to a visible list, then restart and verify it
survives. Build editing, deletion, and completion on that foundation.
