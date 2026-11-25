# Personal Workspace — final Smoky Lavender polish

This is an **overlay** for the existing `feat/smoky-lavender-ui` branch,
not a replacement application. The ZIP only contains presentation-layer files,
small UI regression tests, and a Windows desktop shortcut helper.

## Changes

- Browser icon: Calendar Check (`:material/event_available:`). A matching
  lavender calendar-check `.ico` is supplied for the desktop shortcut.
- Home: `A clearer view of your tasks, deadlines, and the week ahead.`
- Home focus: tasks due/overdue today or linked to an accepted study session
  scheduled today. Other work remains accessible through Tasks.
- Completed tasks are shown **below** Today's Focus, collapsed by default.
  Entries are based on the existing `completed_at` timestamp, not the due date.
- `View task` opens that exact task on the shared Tasks page in the same tab.
- Corrected awkward deadline copy (`Overdue · due DD/MM/YYYY at HH:MM`).
- Rescue My Week: one pair of clickable choice buttons instead of a selector
  plus explanatory cards. All scheduling strategies and proposal actions remain
  exactly as before.
- Removed unnecessary Home/Calendar/Tasks subtitles, renamed the two Advanced
  routes to `Detailed Task Editor` and `Advanced Planning`, and clarified the
  purpose of each Advanced page.
- Added `Create Desktop Shortcut.bat`, a lightweight Windows shortcut creator.
  It places `Personal Workspace.lnk` on your desktop with a calendar icon and
  launches the **personal** local workspace using the pre-existing batch file.

## No changes to application data or scheduling algorithms

The update does not change any file in `workspace/advanced_planner.py`,
`workspace/advanced_repository.py`, `workspace/planning_insights.py`,
`workspace/quick_tasks.py`, `workspace/repository.py`, or the database schema.
No database is included in the ZIP.

## Windows installation

1. Stop Streamlit (`Ctrl+C`).
2. In PowerShell, go to the existing local repository:

   ```powershell
   cd C:\Users\Win\OneDrive\Desktop\personal-workspace
   git status -sb
   ```

3. Confirm you're on `feat/smoky-lavender-ui`. Commit the pre-polish changes
   to preserve a checkpoint (never add personal databases):

   ```powershell
   git add -A
   git commit -m "Checkpoint Smoky Lavender before final polish"
   ```

   `nothing to commit` is harmless.

4. Download `personal-workspace-final-ui-polish.zip` into `Downloads`, then:

   ```powershell
   Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\personal-workspace-final-ui-polish.zip" -DestinationPath . -Force
   ```

5. Run the quality checks:

   ```powershell
   .\.venv\Scripts\python.exe -m ruff check --fix .
   .\.venv\Scripts\python.exe -m ruff format .
   .\.venv\Scripts\python.exe -m ruff check .
   .\.venv\Scripts\python.exe -m ruff format --check .
   .\.venv\Scripts\python.exe -m pytest -q
   .\.venv\Scripts\python.exe -m scripts.check_ui
   ```

6. Run the separate demo (safe sample database) and inspect Home, Tasks and
   Rescue My Week:

   ```powershell
   & ".\Launch Calendar V3 Demo.bat"
   ```

   It normally opens `http://localhost:8503`.

7. To create a Windows desktop shortcut for your **personal** workspace, stop
   the demo, then run once:

   ```powershell
   & ".\Create Desktop Shortcut.bat"
   ```

   Double-click `Personal Workspace` on your desktop to start the personal
   local application. The Streamlit server terminal is minimized and **must
   remain running**; to stop it, restore that terminal window and press
   `Ctrl+C`. This is not a hosted app or a stand-alone Windows installer.

## Manual verification before merge

- Home: verify the greeting and new subtitle, focus tasks and collapsed
  Completed today, deadline wording and task View action.
- Tasks: verify that View task opens the right assignment and that Back to all
  tasks works. Complete/edit a checklist only in the separate demo database.
- Calendar: switch between the two Rescue My Week strategies. Each choice is
  a button containing its own description; confirm the selected one is styled.
- Advanced: check the detailed editor and planning views remain accessible.
- Desktop shortcut: confirm the icon is correct and starts the **personal**
  app, not the demo. Closing the server process should stop the app.

The source tests here passed **163 Python tests and 58 subtests**. Ruff and
live Streamlit browser checks must still run on Windows before merging.
