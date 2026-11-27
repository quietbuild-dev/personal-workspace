# Final usability pass

This patch simplifies the Home/Calendar experience while preserving the existing
solver, accepted-plan safety, explicit approval, saved user data and Undo behavior.

- Removes the empty-calendar Home nudge.
- Weekly Replay records actual minutes only when a Calendar study session is
  marked Done or Partially done through Update progress or reschedule.
- Event repeat label now reads Does not repeat; internal stored value stays Never.
- Schedule check replaces verbose Plan Doctor diagnostics and shows a brief
  actionable warning without pretending to prove infeasibility.
- Calendar event times, protected free time and preferred focus times use 5-minute
  choices; exact off-grid times imported from ICS are preserved in event editing.
- The first Make room for life period can be previewed immediately without
  clicking Add period; multiple periods remain optional.
- Study Style supports persistent custom focus hours in HH:MM (24-hour) format,
  without a database schema migration. Existing focus selections still work.
- Energy and Smart Task Capture section titles are simplified.
- Old advanced calendar availability forms use a 5-minute step.

The normal desktop app reads its usual database; use the separate playground
launcher for demo data. The installer only changes files listed in its manifest.
Run Ruff and full pytest on the Windows setup, then visually verify one-click
Free Time preview and custom Study Style hours before merging into main.
