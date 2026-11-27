# Final refinement update — 26 November 2026

This update is limited to the features reviewed in the desktop demo.

- Hide Advanced navigation; keep its source modules and database untouched.
- Add simple checkbox-style to-dos and explicit task display choice in Tasks.
- Replace decimal hours with hour/minute formatting on the Home workload chart.
- Choose a 7/14/30-day Deadline Runway, ordered chronologically, with consistent row style.
- Add a weekly booked-versus-actual Plotly graph while preserving honest historical limitations.
- Add finite daily/weekly/monthly/yearly recurring calendar events (up to two years), with separate handling of an occurrence versus deleting its whole series. Series are materialized as ordinary events.
- Protect multiple personal-time windows, allowing Social and Exercise plans while keeping fixed work/lecture conflicts visible; preview/accept/undo is transactional.
- Show Energy Today dates with accepted study counts to avoid empty-demo confusion.
- Move .ics Import below the calendar and Agenda; remove Schedule Lab UI, retain its logic.
- Replace Schedule Lab with a compact, read-only Plan Doctor using existing diagnostic and scheduling previews.
- Keep the existing Undo button and functionality; extend its atomic handling only for multiple protected periods.

## Scope limits

- Recurrences apply to fixed calendar events, not tasks. The series creates a finite number of occurrences through the user-selected end date; it does not maintain an infinite calendar.
- Editing a repeating occurrence edits only that occurrence; changing the entire existing series is not implemented. Deleting an entire series is supported.
- Plan Doctor reports grounded risk and candidate mitigations, not a formal infeasibility proof. Its approval route uses the existing planner.
- Last-week history is based on retained records; overwritten older scheduled blocks cannot be reconstructed.
- Schedule optimizer and calendar Undo button were otherwise left unchanged.

Run full Ruff and pytest on the Windows machine with OR-Tools installed before merging.
