# Demo walkthrough

A short route through Personal Workspace, using a **sample database**, not your personal one. You don't have to explain every button: focus on what the scheduler adds beyond a task list.

## Suggested 8–10 minute walkthrough

1. **Home (1 min).** Show today's focus, deadlines, and workload. Explain where the numbers come from.
2. **Tasks (1–2 min).** Add a task with a deadline and priority. Show a simple to-do, a manual progress bar, and a checklist. Complete the last subtask on a suitable example and show where the finished task appears.
3. **Settings and Calendar (1–2 min).** Show study preferences and actual available study hours. Add or point out a fixed lecture or appointment.
4. **Smart Planner (2–3 min).** Generate a schedule, switch goals, and compare results. Explain why a goal that protects routine can differ from one that schedules more work. Show a shortfall if the week is overloaded.
5. **Safe replanning (1 min).** Review proposed changes before approval. Explain that the app checks the latest state again when saving and supports guarded Undo.
6. **Engineering (1 min).** Point to the [CP-SAT model](GOAL_BASED_OPTIMIZER.md), [evaluation](OPTIMIZER_EVALUATION.md), and [tests](../tests/README.md).

## Manual checks before presenting

- [ ] The app opens in a browser and, on Windows, from the desktop shortcut.
- [ ] A task persists after a refresh; a completed to-do appears under Completed today.
- [ ] Checking the last subtask in Home/Tasks completes an eligible parent task. Tasks with required unfinished timed steps stay open.
- [ ] Day/week Calendar views show events and accepted study sessions without overlaps.
- [ ] A planning preview doesn't modify the calendar until it is approved.
- [ ] Different optimization goals can be generated and compared.
- [ ] Undo behaves correctly when the saved state has not changed.
- [ ] Unsupported `.ics` entries are reported rather than silently imported.

Use [the sample-workspace guide](PLAYGROUND_DESKTOP_DEMO.md) to avoid changing your personal data. Automated tests are useful, but they don't replace checking the running interface yourself.
