# First implementation milestone: a task that survives restart

Start after both computers can launch the scaffold and the current course brief
has been checked. Work through this small vertical slice before implementing
the planner or filling the dashboard with charts.

## First working session

**Student A: data and persistence**

1. Add TaskDraft and Task dataclasses plus validation to `workspace/models.py`.
2. Add database initialization and create/list functions to
   `workspace/repository.py`. Follow the field rules in DESIGN.md.
3. Write tests that reject empty titles and invalid minutes, and a test that
   creates a task, closes the connection, opens a new connection, and reads it.

**Student B: the first task form**

1. Replace the tasks-page placeholder with a Streamlit form for title, category,
   optional deadline, priority, and estimate in minutes.
2. On submit, pass a TaskDraft to the repository and render stored tasks below.
3. Display validation feedback without claiming a failed save succeeded.

Agree the exact fields and function names together first. Student B can build
the visual form before persistence lands, but merge the real connection in the
same milestone. Do not add temporary hardcoded dashboard totals.

## Acceptance walkthrough

1. Add "Prepare SWE demo", category University, deadline November 26, priority
   High, estimate 90 minutes. It begins pending with 90 minutes remaining.
2. Submit an empty title and an invalid duration; neither should create a row.
3. Stop Streamlit, start it again, and confirm the first task is still visible.
4. Confirm the database lives under `data/` and is excluded by Git.
5. Run pytest and Ruff; review the diff together and merge the feature branch.

After this succeeds, add editing, confirmed deletion, completion, reopening,
and manual remaining-time updates. Complete those persistence tests before
starting automatic planning. The milestone's end state is real task management,
not a fully built dashboard.

## Questions both students should be able to answer

- What survives a browser refresh, a rerun, and a server restart, and why?
- Why are durations integer minutes instead of floating-point hours?
- Why are SQL queries parameterized?
- Where is invalid input rejected, and what happens when saving fails?
- How does marking a task completed change remaining work and completed_at?
