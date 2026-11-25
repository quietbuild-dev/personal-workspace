# Focused Home & Calendar UI refresh — 25 November 2026

This is a small presentation update on top of the **exact source ZIP supplied in the conversation**. No planner algorithm, schema, database, or saved user data was edited. The dark smoky-lavender theme, task management, plan preview, deadline checks, A/B schedule comparison, and calendar export remain in place.

## What changed

- **Home:** Planning insight appears immediately below the three metric cards. When required work is unscheduled, it states the affected task names and missing time directly. Removed the duplicate yellow warning and the expander hiding the deadline names.
- **Home:** Upcoming deadlines show three entries instead of four, plus a count for additional tasks. The weekly overview is now one full-width card below the focus/deadline row instead of extending the right column.
- **Home:** Removed redundant *Plan my week*, *Open calendar*, *Today's schedule*, *Add a task* and *Manage tasks* controls from the bottom. Task creation/editing still works on the **Tasks** page; the calendar and planning tools still work on **Calendar**.
- **Weekly overview:** Calendar blocks of the same type already aggregated in the data and are now displayed as one adjacent color section per category, in a stable category order. Labels show **total booked hours** rather than cryptic "1h + 5h" notation; bars have a more readable width/height. Overlapping bookings still count twice, as disclosed.
- **Calendar:** *Undo last plan* moved beside the title and is visible **only** when a previously accepted plan is safely reversible. It does not appear before a plan is saved, or after another action invalidated that undo. The underlying undo logic and safeguards remain unchanged.
- **Calendar:** *Add event*, *Study preferences*, *Export calendar*, and *Plan my week* are individual adjacent controls. The export behavior is unchanged.
- **Navigation:** A minimal CSS rule attempts to separate **Settings** (and the adjacent Advanced menu) toward the right side of Streamlit's native top navigation. Streamlit DOM/viewport differences may affect exact alignment; this is deliberately CSS-only, not a custom router or a redesign.

## Verification

- Python compile check passed.
- 228 tests passed, 1 test skipped, and 58 `unittest.subTest` cases passed with the optimizer-only test file excluded. The skip is OR-Tools-dependent; OR-Tools is not installed in the review environment.
- The optimizer-only suite is **not** validated here: the review environment lacks `ortools`, so baseline optimizer tests fail before and after this change. The user should run the full test suite with their Windows `.venv` where the project dependencies are installed.
- Streamlit/browser pixel rendering and interactive navigation alignment were **not** tested here; Streamlit is not available in the review environment.
- No saved personal data was read into or copied into either deliverable ZIP.

## Safest installation into the EXISTING Windows repository

Open PowerShell, and keep the app closed during file replacement. This procedure uses the **patch ZIP**, not the full-source ZIP, and does not replace `.git`, `.venv`, or `data/workspace.db`.

```powershell
cd "C:\Users\Win\OneDrive\Desktop\personal-workspace"
git status --short
# Optional, but strongly recommended:
Copy-Item .\data\workspace.db ".\data\workspace-before-ui-$(Get-Date -Format yyyyMMdd-HHmmss).db"

Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\personal-workspace-ui-patch.zip" -DestinationPath "$env:TEMP\pw-ui-patch" -Force
Copy-Item "$env:TEMP\pw-ui-patch\workspace\theme.py" ".\workspace\theme.py" -Force
Copy-Item "$env:TEMP\pw-ui-patch\workspace\views\home.py" ".\workspace\views\home.py" -Force
Copy-Item "$env:TEMP\pw-ui-patch\workspace\views\week.py" ".\workspace\views\week.py" -Force
Copy-Item "$env:TEMP\pw-ui-patch\tests\test_simple_views.py" ".\tests\test_simple_views.py" -Force
Copy-Item "$env:TEMP\pw-ui-patch\docs\UI_REFRESH_2026-11-25.md" ".\docs\UI_REFRESH_2026-11-25.md" -Force

.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8510
```

Close the running Streamlit app using Ctrl+C once visually checked. To commit the UI files, from another or the same PowerShell window:

```powershell
git status --short
git add workspace/theme.py workspace/views/home.py workspace/views/week.py tests/test_simple_views.py docs/UI_REFRESH_2026-11-25.md
git diff --cached --stat
git commit -m "Refine Home and Calendar interface"
git push -u origin HEAD
```

**Important branch note:** The uploaded repository was on `feat/final-usability-polish` and its Git working tree contained *many pre-existing uncommitted and untracked implementation files* relative to the local Git HEAD. The `git add` line above stages **only this UI update**. If those other changes are needed for the app to work on GitHub, you must also commit them in a separately reviewed commit before the branch can be safely merged. Do **not** run `git reset --hard` or blindly pull over these uncommitted files. After pushing, open a pull request from `feat/final-usability-polish` into `main` and have your teammate review it.
