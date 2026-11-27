# Understanding plans and bringing in calendar events

Three features help make the planner easier to inspect without giving it permission to quietly change your calendar.

## Schedule Lab and plan checks

Calendar includes tools for checking the current plan: occupied time, deadline pressure, and possible conflicts. A **what-if** preview can show the effect of losing a study window. That simulation is read-only. To protect a real interval, use **Make Room for Life** and approve the change separately.

Explanations show the relevant inputs — deadline, priority, prerequisites, available hours, and commitments. They aren't claims to reproduce every internal decision made by the optimizer.

## Weekly Replay

Home's weekly review compares currently stored planned sessions with recorded completed or missed work. It can show how much time was actually logged against retained bookings; it is **not a direct measurement of productivity**.

Older accepted schedules weren't necessarily stored as permanent history, so the app cannot reconstruct every past version of the timetable. The optional local plan-change log tracks changes **from the point it is enabled**, not retroactively.

## Importing `.ics` commitments

Calendar can preview selected events from an `.ics` export before importing them into the local database. The import checks for conflicts and duplicates and commits the selected events only after confirmation. Imported events become ordinary editable calendar commitments.

Supported imports include single-occurrence timed events and supported one-day all-day events. The import is intentionally **not a live sync**. Recurrence rules, exceptions, overnight or multi-day events, and some large or unsupported files are not imported as complete recurring series. Export recurring calendar occurrences individually if needed.

**Separate feature:** You *can* create recurring events within Personal Workspace itself. That doesn't mean the `.ics` importer understands every external recurrence rule.

Relevant modules include `workspace/views/plan_doctor.py`, `workspace/views/weekly_replay.py`, and `workspace/views/calendar_import.py`.
