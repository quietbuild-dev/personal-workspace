# Calendar V3: Human-readable schedule repair (17 November 2026)

This release is an additive source overlay to the current **Rescue My Week** branch.
There is no database migration, and the ZIP does not contain `data/workspace.db`.

## What changed

- Home: today's priorities and due-this-week tasks appear before the full task list.
- Saving a task edit immediately closes its details panel after a successful DB write.
- Finishing all checklist items offers an explicit **Mark task done** prompt.
- Deadline time is an optional five-character `HH:MM` text field with validation.
- Calendar is called **My Calendar**, with stronger calendar-block link contrast and
  explicit same-tab navigation (`target="_self"`). Real browser behavior needs testing.
- Selecting a fixed event shows its details, with the full editing form tucked in
  **Edit event**. Session progress and rescheduling are similarly tucked in one control.
- Study preferences: one date, earliest start, latest finish and maximum hours/minutes.
  Applying the same settings through Sunday is optional. Events still block their own times.
- Rescue My Week: two plain-language strategies, short readable risk messages,
  an expandable **Before → After** comparison on a shared time scale, and changes
  grouped by assignment (old time → proposed time). The old raw + / - log is gone.
- What-if: a one-sentence explanation of additional unplanned deadline work, with
  affected assignments in an optional section. The preview never alters saved data.
- New algorithm-suggested sessions begin on five-minute boundaries. Existing accepted
  sessions are never silently rounded. This rule can produce up to four minutes of
  extra unscheduled work in a tight gap, reported as a shortfall rather than lost.

The two scheduling methods remain deterministic greedy heuristics; a shortfall does
not prove there is no other feasible schedule. Stale-proposal validation, conflict
checks, user approval, and atomic persistence stay in place.

## How to try the example

The source ZIP includes an independent local HTML preview at
`previews/my-calendar-playable-preview.html`. Double-click it to explore the UI
without Streamlit. It's **read-only** and uses precomputed sample schedules.

For the actual working Streamlit example:
1. Run the included `Launch Calendar V3 Demo.bat` from the project folder.
2. On first launch it creates `data/calendar-v3-demo.db` using the current date.
3. Visit http://localhost:8503 and inspect Home, My Calendar, and Rescue My Week.
4. Accept a real plan or edit an event, then restart and verify it persists.
5. To start over, stop the demo, delete ONLY `data/calendar-v3-demo.db` and relaunch.

The personal database `data/workspace.db` is never opened by this demo launch.
To return to your personal workspace, stop the demo and launch your usual app
without `WORKSPACE_DB_PATH` set.

## Manual release gates

On Windows, after installing this overlay into the existing project:

    .\.venv\Scripts\python.exe -m ruff check .
    .\.venv\Scripts\python.exe -m ruff format --check .
    .\.venv\Scripts\python.exe -m pytest -q
    .\.venv\Scripts\python.exe -m scripts.check_ui

The current isolated environment runs Python tests but lacks Streamlit and Ruff.
Test the same-tab event behavior, keyboard accessibility, form submissions, and
calendar contrast manually in the real Windows Streamlit browser.
