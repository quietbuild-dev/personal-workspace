# Calendar usability increment — 12 November 2026

This is an **overlay on the tested Home + Week version**, not a new repository.
It keeps the task schema, study-step data, fixed commitments, accepted sessions,
and explicit acceptance of revisions. It does **not** modify existing users'
saved tasks or time windows.

## Everyday changes

- **Home → Add task:** title, category, estimated minutes, priority, and due-date
  controls are all shown immediately. Only the title requires user entry;
  defaults are Personal, 60 minutes, Medium, no deadline. The date control is
  visible but is used only when “Has a deadline” is checked. Quick task
  creation still creates its schedulable work atomically.
- **Calendar:** start in a **Day** timeline. Switch to **Week** for seven days.
  The timetable uses a shared time scale and fixed grid columns. Full names
  are shown in tooltips and the agenda; the main timetable has readable blocks.
- **Progress:** one-click **Done** and **Missed**, or **Partially done** with a
  minutes-left field only when that action is chosen. A future session is not
  eligible to be marked complete before it starts, or missed before it ends.
  The interface now says why the buttons are unavailable. To finish a whole
  task early, use **Done** on Home. Partial progress updates the corresponding
  timed step but does not automatically accept a new plan.

## Day-specific study budgets

Use **Calendar → Plan study time & add commitments**. Enter the amount of study
work you are willing to schedule on each date (blank = unchanged; 0 = day off). A date with no
budget and no old detailed window has **no automatic study capacity**.
Only entered budgets are saved on actual dates; blank inputs do not overwrite older
availability windows or other dates. Budgets do not repeat next week.

For a budgeted date, the planner looks for time gaps **between 08:00 and 22:00**,
subtracts fixed lectures/appointments, and schedules no more than that day's
budget. The 08–22 range is a *search boundary*, not a presumption that you are
free or willing to study all those hours. If 08:00 is too early for you,
**do not accept** an unsuitable proposal; this version does not yet provide a
per-day preferred earliest start or manual dragging of study sessions.

The daily budget is a maximum, not a request to fill every available gap.
Minutes already recorded as completed that day count toward its maximum;
missed sessions don't. Existing accepted sessions stay saved on changes;
conflicts are shown and a new revision requires deliberate acceptance.

Older `time_windows` records remain stored, and continue working for dates
without a new budget. A saved budget **takes precedence** on its date, without
removing the older windows. This allows a gradual migration instead of a
one-time destructive conversion.

## Correctness and limits

- A budget is validated as an integer between 0 and 840 minutes, then saved in
  an additive SQLite table `day_study_budgets` with a database CHECK constraint.
- The scheduler and independent acceptance validator both enforce the daily cap,
  deadline, no-overlap, time window, and remaining-work invariants.
- The complete planner snapshot fingerprint includes the budgets. Editing one
  invalidates any previously previewed proposal. Approval still uses an atomic
  SQLite transaction and keeps unchanged session IDs.
- The algorithm is greedy. Unscheduled minutes mean the strategy did not place
  that work; they do not prove no feasible schedule exists.
- The calendar is a readable static view plus forms, not yet an interactive
  drag-and-drop editor. Manual study-session placement is a separate potential
  usability improvement and is *not* claimed as implemented.

## Windows browser walkthrough

Use a separate demo database or back up your normal `data/workspace.db` first.

1. Open **Home**; confirm Category, Priority, Estimated minutes, and Due date
   appear without opening an expander. Save a task with title alone.
2. Open **Calendar**; check Day first, then Week. All event blocks should line up
   with their clock rows and date headers. Verify no narrow-screen overflow
   outside the scrollable calendar container.
3. In the collapsed study-time panel, set today to 60–120 minutes and another
   date to zero. Add a fixed lecture on today's date. Confirm proposed work is
   outside the lecture and within the target minutes.
4. Accept the suggestion, restart, and confirm the saved timetable and budgets
   survive. Change today's target and verify the old acceptance is not silently
   overwritten. A previously created proposal must be rejected as stale.
5. For future sessions, check the explanatory text next to disabled progress
   actions. After the session begins, Done and Partial become available; after
   it ends, Missed becomes available. Partial asks for remaining minutes only
   after selection, never for normal Done/Missed.
6. Reject one revision and confirm it hasn't changed accepted sessions. Accept
   another and verify its persistence. Confirm Home's workload preview uses the
   new daily budgets.
7. Run `python -m pytest`, `python -m ruff check .`,
   `python -m ruff format --check .`, and `python -m scripts.check_ui` in the
   project virtual environment before committing.

**Release status:** Pure-Python/SQLite automated tests and standalone browser
rendering of the HTML timetable passed in the assistant environment. Native
Streamlit browser interaction and Ruff must be verified on Windows.
