# Final usability polish and richer playground

This patch makes the live planner easier to understand without changing stored personal data.

## What changed

- Four Study Style questions remain dropdowns, and Settings now calls the section **My Study Style**. The previous one-line focus-time reminder on Home is gone.
- In Rescue My Week, an uncovered required deadline is explained in hours/minutes rather than solver terminology. A/B comparisons **still require** every required timed task due this week to have its full estimated remaining study time allocated before either alternative is offered as complete. Allocation is not completion.
- **Ordinary** five-goal preview comparisons no longer impose A/B's all-or-nothing deadline constraint. Previously that constraint could make an infeasible optimization fall back to the exact same greedy plan for every goal. Normal previews can still leave unscheduled work, and must explain it honestly.
- Goal comparison shows **study days** and **busiest day** as well as coverage and movements; it tells the user when the chosen schedules are actually identical.
- Task list, today's focus and upcoming deadlines show accessible **green progress bars**. Logged timed-step progress is preferred, since recording a completed session updates the timed step even if the parent task's remaining-time field hasn't changed. For a task with no logged minutes, checked checklist items can show *checklist* progress explicitly. Merely accepting a study session does not increase progress.
- Advanced calendar says **Preview a new plan**, not **Propose revision**.
- Export popover explains how to import `.ics` into Google Calendar/Apple Calendar; this is not live synchronization.
- The Streamlit auto-generated heading-link control is hidden through CSS.

## Undo

Undo was already implemented. It appears at the **top of Calendar** when the database contains a safely reversible accepted plan. The screenshot in this conversation shows it. This patch shortens its label to **Undo last plan** and makes the save message point to it, without weakening safety checks. If undo doesn't work, capture the error; do not force a rollback.

## Fuller example

The module `scripts.create_rich_demo` creates a **new** demo SQLite DB with 16 fixed events, 11 tasks, two accepted study sessions, dependency examples, and a task at 50% recorded progress. It refuses to overwrite an existing file or a file named `workspace.db`.

From PowerShell in the repository:

```powershell
$demo = Join-Path (Get-Location).Path ("data\rich-demo-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".db")
.\.venv\Scripts\python.exe -m scripts.create_rich_demo --output "$demo"
$env:WORKSPACE_DB_PATH = $demo
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8508
```

When finished, stop the running server with Ctrl+C, then `Remove-Item Env:WORKSPACE_DB_PATH`. The regular desktop shortcut uses the personal database and does not inherit this shell-only environment variable.

Best run Wednesday evening November 25 or Thursday daytime November 26, 2026: the scenario is intentionally the current four-day study week.

## Validation

Targeted pure-Python tests cover green progress semantics, flexible vs. strict goal comparison, A/B deadline safety, and demo isolation. Also run Ruff and the full pytest suite with an isolated `--basetemp` on Windows. Manually inspect the desktop interface and Undo before merging.
