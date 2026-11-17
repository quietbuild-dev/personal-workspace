PERSONAL WORKSPACE -- SAMPLE CALENDAR PLAYGROUND
17 November 2026

This kit provides example assignments, schedules, daily study preferences and fixed events.
It DOES NOT replace data/workspace.db, your personal task data, Git files, or source files.

INSTALL
1. Stop Streamlit if running.
2. Extract all files from this ZIP into the existing personal-workspace project folder.
3. Double-click "Launch Demo Workspace.bat" in the project folder.
4. Open Home and Calendar and try the example week.

NOTE: The new "Rescue my week" comparison appears only if you've installed the
personal-workspace-rescue-my-week-update.zip update in the project first.

WHAT TO TRY
A. Home: inspect assignment deadlines, study work, and checklists.
B. Calendar: switch between Day and Week; inspect category colors and event details.
C. Open Rescue my week. You will see a deliberately added guest lecture conflict.
D. Compare Keep my plans and Rebuild my week; inspect work fitted, disruptions, risk.
E. Simulate losing an afternoon. This preview is read-only.
F. Try accepting a plan; restart the demo and check it stayed saved.
G. Try recording progress on a past/current study block, or rescheduling a future one.

IMPORTANT
- The demo is meant to be changed: edits persist only inside data/study-playground.db.
- The included demo database is anchored to the week of 17 November 2026.
- To reset/create a new demo for your current week: STOP the app, delete ONLY
  data/study-playground.db, and run:
  .\.venv\Scripts\python.exe -m scripts.create_playground_demo
- Future weeks: the planner currently only suggests through the current Sunday.
- To return to your real workspace, close the demo process, then launch your
  normal project command or normal desktop shortcut (not Launch Demo Workspace.bat).
