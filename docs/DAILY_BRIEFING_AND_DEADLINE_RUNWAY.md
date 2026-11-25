# Daily Briefing and Deadline Runway — additive Home update

This patch adds two small, data-driven Home sections without replacing the existing Home, optimizer, calendar, or desktop launcher.

## Daily Briefing

- Shows today's number of lectures, accepted study-session minutes, and count of nearby unfinished deadlines.
- “Start my day” reveals the real saved agenda and nearest deadlines; it does not mark tasks done or approve a schedule.
- The summary is deterministic and based on saved local data. It does not use an LLM or send data anywhere.

## Deadline Runway

- Displays the nearest upcoming or overdue assignments within 14 days.
- For hourly-plannable tasks, “remaining” comes from actual *timed-step* remaining minutes. A booked study session does **not** subtract from this amount.
- Shows already accepted future study time allocated to each task and the remaining work without a slot.
- Estimates unbooked capacity until the due date by combining explicit availability/budgets, then subtracting fixed commitments and booked study. Study budgets are respected, including already completed study time.
- Capacity is a **shared pool** and does not guarantee that all deadlines can be satisfied. The planner may reallocate booked sessions; a simple capacity comparison is not a proof of feasibility.
- Tasks excluded from hourly planning are labeled rather than described as unscheduled study.
- First three deadline rows are visible; more are available inside “See more deadlines”.

## Install on your current main checkout

Extract the ZIP **into the repository root**, then run:

```powershell
.\.venv\Scripts\python.exe .\scripts\install_home_intelligence.py
```

The installer looks for three known anchors and only adds an import and two render calls in `workspace/views/home.py`. It refuses unknown Home versions with no changes. It is safe to rerun and saves the original Home file under `data/source-backups/`.

Run `ruff check .` and the full pytest suite. The new read-only features add no database migrations and no dependencies. All source is compatible with Python 3.12.

## Demo

Use the existing local data, or create a separate demo database with `scripts.create_rich_demo` where applicable. Start Streamlit and visit Home. The same working directory is used by the optional WebView2 desktop shortcut; no separate frontend build is required.
