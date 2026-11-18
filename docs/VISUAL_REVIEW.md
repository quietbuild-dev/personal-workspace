# Visual polish review (November 2026)

This update is **presentation-only**. The task model, scheduling heuristic,
SQLite schema, acceptance/rejection transaction, and saved data remain unchanged.

## Changes

- **Smart Planner:** Seven-column Monday-Sunday weekly calendar. The time axis
  runs down the page, with hour grid lines and legible horizontal labels.
  Availability windows are faint sage; accepted study sessions are sage blocks;
  fixed events are slate. Each block's full text and precise time are available
  on hover. The expandable full-week agenda gives a readable alternative when
  blocks are short or titles are long. Proposed revisions use the same grid.
- **Tasks:** Compact quick-add with title, category/course label, and estimated
  minutes visible immediately. Deadline and priority are available in one
  collapsed optional section; the complete/edit/delete and study-step controls
  remain unchanged below the list. After saving, fresh widget keys reset inputs.
- **Dashboard:** Matched metric-card footers, relative labels on upcoming and
  overdue deadlines, a useful next-session preview when today is empty, and a
  workload chart in hours with complete minute values on hover.

## Run validation on Windows

```powershell
.\.venv\Scripts\python.exe -m ruff check --fix .
.\.venv\Scripts\python.exe -m ruff format .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m scripts.check_ui
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Use your existing **separate demo database** and check all three screens.
Specifically verify the chart shows all seven day columns, hover gives full
study names, quick-add is visible without scrolling, and both accepted and
proposed plans remain consistent. Nothing about the calendar update should
change accepted sessions when it is merely viewed.

The baseline before this update had 82 automated tests; the visual test module
adds three more. Passing automated tests does **not** establish pixel-perfect
browser behavior; manually review the display at your normal window width.
