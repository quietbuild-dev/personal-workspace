# Core usability update — November 2026

This is a small upgrade to the existing Personal Workspace project, intended to
be applied **on top of** the preceding `feat/final-usability-polish` rich-demo
update. It does not change the CP-SAT objective functions, the launcher, or the
users' personal databases.

## Everyday task progress

Tasks now offer a per-task progress method: automatic (checklist first),
completed subtasks, recorded work time, or a manual percentage. Automatic
progress selects checklist coverage whenever a task has a checklist, otherwise
it uses genuinely logged work time. Manually set percentages update the **bar
only**; they do not reduce estimated remaining time, mark a task complete, or
mark study sessions as done. A task has to be explicitly marked Done.

The mode and manual percentage are persisted in a small additive SQLite table
with cascading deletion. Each local database keeps its own preferences. A
recent completion can be reversed from the task list and restores the task's
prior remaining work, rather than blindly resetting its full estimate.

## Calendar and Home

- Home shows a stacked seven-day display of **accepted study blocks and fixed
  commitments**, with the Calendar's lavender, blue, purple, sage and peach
  colors. It is booked time, **not** remaining free capacity; overlapping fixed
  events can add up.
- Calendar keeps Plan My Week visible and groups secondary tools into one
  expandable row.
- Preview states the plan being reviewed (including Plan A / Plan B). The
  search-limit message is in optional solver details rather than interrupting
  everyday planning.
- Undo remains restricted to the last safely reversible accepted schedule.
  If new task/event/calendar changes invalidate Undo, the interface explains
  why instead of silently hiding the history.
- Deadline help uses simpler language.

## How to verify on Windows

1. Back up `data/workspace.db` with the app **closed** (do not commit this file).
2. Extract the patch over the existing **uncommitted**
   `feat/final-usability-polish` branch (not `main`).
3. Run Ruff formatting and linting, the full pytest suite with a unique
   `--basetemp`, and `scripts.check_optimizer_ui`.
4. Try a **separate demo DB**. On Tasks: check 1/2 subtasks, select manual 65%,
   test a partial-time entry, mark Done, then use Undo completion.
5. On Home: inspect combined workload. On Calendar: compare plans, accept one,
   test Undo, then make an event edit to see the safety explanation.

The new pure-Python tests cover persisted progress, task completion reversal,
weekly workload categories, and the three Undo visibility states. A Windows
manual test is still required before merging; no claim is made that a screenshot
or browser-only smoke test proves the desktop launcher works.

Future roadmap (not implemented here): Make Room for Life; Daily Briefing;
Today Energy; Deadline Runway; Smart Capture; Weekly Replay; safe `.ics`
import; and later a secure phone/Shortcuts companion.
