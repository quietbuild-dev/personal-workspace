# Home & Week usability refactor — 12 November 2026

## Purpose

Keep the advanced planner's algorithm, saved sessions, and explicit acceptance
while reducing visible controls to two primary destinations: **Home** and **Week**.
The application is still a local, single-user Streamlit + SQLite desktop app.

## Everyday workflow

1. **Home** shows open tasks, time remaining, due-this-week completion, today's
   accepted sessions and fixed commitments, upcoming deadlines, and a compact
   availability-versus-planned chart.
2. **Add task** needs only a title. Defaults: Personal, 60 minutes, Medium, no
   deadline. Expanding *Add details* reveals duration, category, priority and date.
3. One transaction creates the parent task, one automatic **Focus time** timed
   step, and its link; this lets the hourly planner consider quick-added tasks
   without requiring users to create a study step manually.
4. After availability has been set, a read-only proposal is computed on page
   refresh. Home links to **Week** for review. **No plan is accepted silently.**
5. **Week** always shows the saved calendar first. Study windows and fixed events
   are under *Availability & fixed commitments*. The proposal panel is displayed
   only when there is a change or unscheduled work. The user previews, accepts, or
   keeps the accepted plan. Session logging is optional and collapsed.
6. **Done** and **Edit** are directly available in the Home task list. Detailed
   editing, simple checklists, additional timed study steps, and confirmed
   deletion remain accessible from task details.

## Data model and compatibility

- The existing `tasks`, `study_steps`, `time_windows`, `fixed_events`, and
  `scheduled_sessions` tables are not rewritten.
- New `quick_task_links(task_id, step_id)` has both foreign keys and cascade
  deletion. It distinguishes an automatic Focus time step from separate steps.
- Quick-task creation, editing, completion and reopening happen transactionally.
  Closing an automatic step does **not** silently complete other checklist or
  custom timed steps. Unchecked work blocks parent completion.
- Adding a detailed timed step through Home **splits** the existing automatic
  Focus time budget so scheduled work is not counted twice.
- Legacy tasks are left untouched. They still appear on Home. The optional
  **Include this existing task in the hourly planner** action creates a linked
  Focus time step if the task does not already have custom timed work.
- The old three page modules remain present as compatibility code, but
  `app.py` registers only Home and Week as primary destinations.
- Original day-level planning is still accessible by enabling the Advanced
  checkbox near the bottom of Week. It does not alter accepted hourly sessions.

## Proposal safety

- `workspace.simple_planning.proposal_notice()` computes a deterministic,
  read-only preview from the latest SQLite snapshot.
- An accepted schedule is changed only by `accept_revision()`, which uses an
  immediate SQLite transaction, rechecks the fingerprint and validation rules,
  and retains unchanged session IDs. Stale proposals are rejected.
- A missed/done session or edited task can cause a new proposed revision, but
  no accepted session is silently moved.
- The heuristic may leave work unscheduled; that is **not** a proof that no
  feasible schedule exists.

## Manual Windows browser checklist

1. Back up `data/workspace.db` and optionally run the demo in its **separate**
   DB using `WORKSPACE_DB_PATH`. Verify only Home and Week appear in navigation.
2. On Home, add `Economics revision` with just the title. Verify it appears as
   an open task and in task details without requiring a manual timed step.
3. On Week, expand Available time, add an hour tomorrow (e.g. 14:00–15:00)
   and a lecture overlapping part of another available window. Confirm the
   accepted calendar does **not** change merely from adding these.
4. Review the suggested week. Verify the proposed block does not overlap the
   lecture; accept and confirm it remains saved after restart.
5. On Home, mark the task Done. Week must propose removal of any future accepted
   session; reject once and verify the saved session is unchanged, then accept.
6. Reopen the task and verify it has a positive remaining-time estimate and a
   new plan may be proposed; nothing is accepted without approval.
7. Add a checklist item beneath a task. Verify parent completion refuses to
   silently check it off. Finish the checklist and complete the parent.
8. Edit a task's deadline and estimated minutes; verify any resulting proposal
   is preview-only, and stale proposals cannot be committed.
9. Confirm the UI is readable at your actual Windows browser width and that
   no nested expander errors, form-key collisions, or scroll traps occur.

## Testing status

The 103 Python tests and 44 subtests pass in the assistant's available Python
runtime. The original 85 tests remain green. Ruff and the real Streamlit UI
smoke/browser checks are **not** verified in this environment: run them in your
local Windows Python 3.12 `.venv` before committing or merging. A passing
Python test suite alone is not a guarantee of browser behavior.
