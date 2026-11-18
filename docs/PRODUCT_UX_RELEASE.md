# Personal Workspace — final everyday-UX implementation

## Goal

A simple student task list and calendar that offers **optional, reviewable study-time suggestions**. The user operates with three concepts: **tasks**, **events**, and **suggestions**. The underlying timed-study-step, availability, and revision data structures remain for correctness and backwards compatibility; they are not everyday UI concepts.

## What changed

- **Home:** one compact visible task form (title required; date, optional time, category, priority, estimated hours/minutes visible). DD/MM/YYYY display, no separate deadline checkbox. Categories include University, Personal, Home, Work, Social, Exercise, plus persistent custom choices. Home now emphasizes today's real agenda and the task list; the misleading top-line completion percentage and workload chart are removed.
- **After adding a task:** the task is committed immediately. If this week has configured study time, a small nonblocking **suggested schedule** appears with **Accept**, **Not now**, and **Change a suggested time**. Until Accept, the accepted calendar is untouched. The proposal is for the full remaining week; the UI warns when other sessions will move. If no study preference exists, the UI explicitly asks for the one-time week preference rather than pretending all blank time is study time.
- **Task progress:** Done, Partly (edit unfinished hours/minutes only when needed), task details, and a simple checklist. No required timed-step creation or "Focus time" terminology.
- **Calendar:** Day/Week switch and a browsable date, aligned time gutter, compact event blocks, task-specific study labels, distinct categories/colors, clickable saved session and event links, optional complete-name agenda.
- **Events:** name, kind (Lecture, Appointment, Personal, Social, Exercise, Other), DD/MM/YYYY, selectable From/To in 30-minute increments, inline edit and deletion.
- **Study preferences:** select a particular date or remaining days of the week; choose total study hours/minutes and preferred Morning/Afternoon/Evening/Flexible period. Lectures, events and existing sessions block occupied time; the planner fills *only* eligible gaps and respects daily budgets. These preferences are date-specific, not silently repeated in later weeks.
- **Sessions:** click a saved study block to see its assignment and checklist. Before it starts, offer Reschedule; after it starts, allow Done or Partially done; after its end, also allow Missed. A changed schedule is always a preview, not a background write.
- **Manual time adjustment:** move a proposed block to another start time/date; validation rejects overlap, missing availability, expired start, deadline violations, excessive minutes or budget overflow.
- **Timed deadlines:** the optional due time is stored separately, and proposals cannot extend past that time on the deadline date. Without a due time, the whole due date remains eligible.

## Schema and compatibility

All changes are additive. The existing `tasks`, `study_steps`, `scheduled_sessions`, `fixed_events`, and `time_windows` data are preserved. New tables:

- `task_categories` — persistent reusable category names.
- `task_deadline_times` — optional due time as minute-of-day; task remains date-based when absent.
- `fixed_event_kinds` — event label associated with an existing fixed event.
- `day_focus_preferences` — preferred start/end time for a given calendar date; existing daily budgets still cap planned minutes.

Migration happens automatically on first app access and is idempotent. Existing untimed deadlines still mean end-of-day. Existing events default to Appointment for presentation. Previously saved automatic steps still have their internal `Focus time` title in the DB but render as the **actual parent assignment**. Nothing migrates, deletes, or rewrites the user's personal task data on installation.

Planning-input fingerprints include new deadline times, preferences, and event categories. Accepting a proposal takes a SQLite write transaction, checks the fingerprint, revalidates nonoverlap/deadline/time budgets, then saves the difference. An unchanged accepted session keeps its ID. Manual previews do not write accepted sessions.

## Technical limits (do not overclaim)

- Scheduling is a **deadline-/priority-aware greedy heuristic**, not optimal and not an AI model. "Couldn't fit under this planning strategy" is not a mathematical proof of infeasibility.
- Productivity preferences are **stated by the user**, not learned from historical behavior.
- Automatic accepted scheduling is restricted to **today through the current Sunday**. The calendar can browse other weeks and save future events/preferences, but proposals for future weeks are generated when they become current.
- Accepted-session progress is recorded when a session starts; *Missed* becomes available after its end. Reschedule is available beforehand. These are deliberate safety rules.
- Calendar blocks are HTML links with query parameters; check on the actual local Streamlit version that clicking them opens the detail panel and that the view stays on the intended date. The standalone HTML test alone cannot verify Streamlit routing.
- Old detailed timed steps and legacy daily-minute features are still stored in the code/database for compatibility but no longer occupy the everyday interface. No account/cloud sync, recurring commitments, ML, drag-and-drop, or Google Calendar integration.

## Manual acceptance walkthrough (Windows)

Use a **separate** demo database or make a database backup before these checks. Start Streamlit from the project directory.

1. **Home:** create a task titled *Economics assignment*, choose University, deadline Friday in DD/MM/YYYY with a time such as 17:00, estimate 2h. Save. Verify it appears in the task list with the correct deadline and a short suggestion or preference prompt.
2. **Custom category:** choose `+ New category`, enter `Student association`, save a task; add another task and verify that Student association can be reselected.
3. **Calendar:** set a study preference for today or tomorrow: 2h, Morning, this date or remaining week. Add a 10:00–11:00 Lecture. Verify the proposal avoids this lecture and respects the chosen period and budget.
4. **Home suggestion:** save another assignment, inspect its proposed study times; use *Change a suggested time* to try an overlapping slot (should show an error), then a valid slot (preview), and *Not now* (should not save sessions). Repeat and explicitly *Accept proposed week*.
5. **Day and Week:** switch views, browse to the chosen date, and verify hour/grid alignment. Click the assignment block. Its real task title and checklist should be displayed. Click a lecture block; edit its title or time and verify the revised plan notice.
6. **Progress:** for a future session, check that Reschedule is available with an explanation of why other results are not yet allowed. After a session has started choose Partially done and enter the remaining estimate; after it has ended choose Missed for a different session. Verify the app offers a revision without silently rewriting the current saved schedule.
7. **Persistence:** accept a revision, stop/restart Streamlit, verify tasks, event types, due times, custom categories, and unchanged session IDs survive.
8. **Edge cases:** zero study budget, no deadline, due time earlier than any eligible study gap, changing a commitment after preview (stale proposal should be rejected), and deleting a task with a confirmation.

## Test evidence and release gate

- In the assistant's Python 3.13 environment: **126 pytest tests and 49 subtests passed**. Source compilation passed.
- A standalone Chromium check of the HTML calendar passed: events/links present and hour gutter height aligned. This is **not** an actual Streamlit UI test.
- Streamlit and Ruff packages were unavailable in the assistant's environment due to package-network restrictions. **Before committing:** run `python -m ruff check --fix .`, `python -m ruff format .`, then Ruff check/format-check, pytest, `python -m scripts.check_ui`, and the manual browser workflow on the user's installed Python 3.12 environment.
- **Unresolved academic issue:** confirm the 2026 course rubric, lecturer approval, collaboration/AI-use rules, and submission instructions. Do not claim these are verified.
