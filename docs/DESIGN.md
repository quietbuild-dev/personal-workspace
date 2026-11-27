# How Personal Workspace is put together

Personal Workspace runs locally. **Streamlit** provides the interface, **SQLite** stores tasks and calendar data, and the scheduling logic lives in Python modules that can be tested without opening the UI. There is no hosted service or account system.

## Main pieces

| Area | Code | Responsibility |
| --- | --- | --- |
| Entry point | `app.py` | App setup and navigation. |
| Interface | `workspace/views/` | Home, Tasks, Calendar, Settings, and the planning controls. |
| Task storage | `workspace/repository.py`, `workspace/quick_tasks.py` | Create, update, complete, and reopen tasks. |
| Advanced storage | `workspace/advanced_repository.py` | Study steps, events, study windows, accepted sessions, dependencies, and transactional plan approval. |
| Greedy baseline | `workspace/advanced_planner.py` | Builds a feasible week and checks the scheduling rules independently of the optimizer. |
| Optimization | `workspace/optimizer.py` | CP-SAT search and the five planning goals. |
| Preferences and insights | `workspace/study_dna.py`, `workspace/planning_insights.py` | Personal study preferences and information about proposed schedules. |
| Tests | `tests/` | Task, data, scheduling, and Streamlit interaction tests. |

## Tasks, steps, and calendar time

A task has a title, category, priority, estimated and remaining minutes, optional deadline, and completion status. Task steps are either **checklist items** (no duration) or **timed work** (minutes that the scheduler can allocate). A task's estimate is not scheduled again on top of its timed steps.

Fixed calendar events — lectures, appointments, and personal commitments — reserve real time. Accepted study sessions reserve time as well, but **booking a session does not mean that the work is done**. Recorded completed minutes and checklist state are handled separately from future bookings.

Tasks can have prerequisites. A dependent task must not be scheduled before its prerequisites satisfy the relevant rules. The optimizer and the independent validator both enforce these restrictions.

## What happens when you plan a week

1. The app loads a consistent snapshot of tasks, steps, fixed events, existing sessions, daily study hours, preferences, and dependencies.
2. The greedy planner or **OR-Tools CP-SAT** proposes study blocks for the remaining Monday–Sunday horizon. The five goals change which *feasible* schedule the optimizer prefers.
3. The preview shows proposed blocks, unscheduled work, and possible changes to previously accepted sessions. It **doesn't write anything** to the calendar.
4. On approval, the database transaction checks that the snapshot is still current and validates the constraints again before writing the new plan.
5. Undo can restore the previous accepted schedule only while the saved state still matches the expected fingerprint.

This avoids a common failure mode: accepting a proposal based on tasks or events that have since changed. See the [optimizer model](GOAL_BASED_OPTIMIZER.md) for the exact constraints and scoring rules.

## Storage and consistency

SQLite is the source of truth. Database changes use explicit transactions, input validation, and foreign keys where appropriate. Additional features were implemented with additive tables rather than requiring a fresh personal database. Tests use temporary SQLite files.

The app is **single-user and local**: there is no cloud synchronization, multi-user locking, or Google Calendar connection. `.ics` import/export exchanges files, not live calendar updates.

## Where the design stops

The planner has a **weekly horizon** and a bounded solver search. It may produce a partial plan when work cannot fit and doesn't guarantee a globally optimal real-life timetable. Study preferences are inputs to planning, not promises that every session will land at an ideal time. A schedule is still a proposal until the user approves it.
