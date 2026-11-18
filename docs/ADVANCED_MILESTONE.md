# First advanced milestone: constraint-aware weekly calendar

Status: **implemented and core-tested in the assistant's isolated checkout**. Student Windows/browser testing and code review are required before merging. This is an additive upgrade to the 57-test daily-planner MVP, not a replacement repository.

## Implemented vertical slice

1. Create an ordinary parent task such as **Prepare for economics exam** (course/project label in Category, priority, and deadline).
2. In **Tasks & Projects**, add an arbitrary mixture of **checklist** steps (zero scheduled minutes) and **timed** steps (their own estimates and remaining time). Rename steps, edit timed remaining minutes, check off checklist items, or explicitly delete steps.
3. In **Smart Planner > Time windows & commitments**, enter one or more dated, start/end availability windows and fixed lectures, appointments, or personal commitments.
4. Choose **Generate proposed revision**. See a weekly hourly calendar; unchanged/new sessions; explicit per-step shortfalls, reasons, and deadlines; and a full-rescheduling baseline.
5. Choose **Accept** to save, or **Reject** to discard. Preview and rejection make no database changes.
6. Once a saved session has started, **Log work** (real minutes worked); once ended, **Missed** is available. Logged work reduces **only** the corresponding timed step's remaining minutes. A missed session doesn't reduce work.
7. Preview the revision. Already-valid sessions are preferentially preserved, and unfinished work is suggested in free gaps. Unchanged session **database IDs** are preserved when accepting.
8. Restart the app: accepted sessions and work progress persist in the same SQLite database.

## Data model and migration

Existing `tasks` and `daily_availability` tables remain intact. New `study_steps`, `time_windows`, `fixed_events`, and `scheduled_sessions` tables are created with `CREATE TABLE IF NOT EXISTS`; IDs on existing task records are never rewritten. Foreign keys link child steps to parent tasks, and sessions to steps. Deleting a parent (or a step) explicitly cascades to its children/sessions. Back up `data/workspace.db` before the first new release run.

- `study_steps`: `id, task_id, title, kind, estimate_minutes, remaining_minutes, checked`.
- `time_windows`: `id, day (ISO date), start_minute, end_minute`.
- `fixed_events`: `id, title, day, start_minute, end_minute`.
- `scheduled_sessions`: `id, step_id, day, start_minute, end_minute, status, actual_minutes` (`planned`, `missed`, or `done`).

**No second schedule is written during proposal generation.** Only the accepted `planned` rows are saved. `missed`/`done` session history is retained. The old day-level planner remains accessible in a collapsed section, explicitly labeled a *legacy suggestion*, separate from the accepted hourly calendar. Parent task completion stays explicit; it is blocked while any child checklist or timed step is unfinished. To avoid double counting, a parent with timed steps is excluded from old daily scheduling, and dashboard remaining minutes use the sum of those timed steps rather than the parent estimate. For parents without timed steps, original behavior is preserved.

## Algorithm (pure `workspace/advanced_planner.py`)

Input: immutable snapshot of dated windows, fixed events, accepted sessions, parent deadlines/priorities, and timed steps, plus **explicit local `now`**. The planning horizon is **today through Sunday**, not next week or a recurring calendar. The deadline day is included. Only future intervals on the current day are eligible.

- Build a set of occupied intervals from fixed events. Merge overlapping/adjacent availability windows so the same free minute cannot be counted twice.
- In the **minimal-change** mode, keep previously accepted sessions which are still inside an available window, do not overlap commitments or one another, have not passed, respect deadlines, belong to open steps, and fit the step's current remaining work.
- Order unfinished timed steps by earliest deadline, higher priority, parent task ID, then step ID. Undated steps follow dated ones.
- For each step, allocate remaining minutes into earliest eligible free gaps. Sessions can be split across days or interrupted by a fixed event.
- Report unallocated minutes as **overdue**, **could not fit before this week's deadline**, or **outside this week's planning horizon**. “Could not fit” means *under this greedy strategy*, **not** a proof that no feasible alternative exists.
- Report unchanged, removed/changed, and added/changed accepted sessions. Full-rescheduling baseline runs the identical algorithm **without preserving old sessions**.

### Safety invariants

Before saving, the database is locked using `BEGIN IMMEDIATE`, all planning inputs are reread, and a SHA-256 fingerprint of task data, steps, windows, commitments, and saved sessions must match the proposal. An independent validator checks the entire proposed schedule: no overlaps, no fixed-event conflicts, inside availability windows, not in the past, inside today–Sunday, not after a deadline, and no step over-allocation. It also checks `allocated + shortfall == remaining` for every open timed step. On any error, the transaction is rolled back and the accepted timetable is unchanged. Diff-based saving preserves row IDs for unchanged sessions.

Adding a new lecture or removing availability can make an accepted session conflict with the current facts. The dashboard and planner display the conflict immediately; they **do not silently change** the accepted timetable. The user must generate and approve a new revision.

## Limitations / follow-on work

- **No global optimality claim.** Earliest-deadline greedy + preservation can allocate less than a more sophisticated search; its shortfalls are heuristic.
- The hourly scheduler uses the **current week only** and local computer time, with no time zones or multiweek forecasting. No recurring availability, drag-and-drop, phone sync, or notification system.
- Legacy task estimate/remaining fields are retained for compatibility. Child timed steps become the planning units for structured parents. Users should enter work in timed steps, not also separately schedule the parent as legacy daily work.
- The proposal is stored only in the current Streamlit session; switching browsers or restarting the app discards the *unaccepted* preview. Accepted sessions remain persisted.
- Session changes should be logged as the work happens. Completed/missed events retain history; the UI cannot retroactively edit work logs in this milestone.
- An active week beginning near Sunday evening may contain little or no available future time. This is expected and visible as unscheduled work.
- A polished complete UI, real Windows Streamlit testing, fresh-install check, GitHub PR, and lecturer approval remain student verification steps.

## Reproducible algorithm evaluation

```
python -m scripts.evaluate_advanced --repeats 100
```

Uses a disposable SQLite database, 12 timed steps, a fixed lecture, a saved schedule and a simulated missed session on fixed 2026 dates. It prints **allocated minutes**, **unallocated minutes**, **unchanged/changed sessions**, and **median runtime** for minimal-change vs full-reschedule greedy approaches. This is a deterministic case study, not a comprehensive optimization benchmark; runtime is machine-dependent. See `tests/test_advanced_planner.py`, `tests/test_advanced_integration.py`, and `tests/test_advanced_demo.py`.
