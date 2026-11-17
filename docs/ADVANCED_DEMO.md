# Advanced weekly calendar: demonstration and local checklist

## Install update over your **existing** repository

1. On your Windows machine, first ensure that **the earlier MVP integration PR is merged to `main`**; if `git diff --stat main feat/mvp-integration` still lists files, finish that merge first.
2. Open PowerShell in the existing project directory. Make a feature branch: `git switch -c feat/weekly-calendar` (only if it does not exist).
3. Back up your task database: `Copy-Item .\data\workspace.db .\data\workspace-backup-before-advanced.db`.
4. Extract the update ZIP; **downloading alone does not apply it**. Run `Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\personal-workspace-advanced-milestone.zip" -DestinationPath . -Force` from the project directory. The archive contains no database, `.venv`, or `.git` folder. It updates source files and adds documentation/tests.
5. Run ` .\.venv\Scripts\python.exe -m pytest`, ` .\.venv\Scripts\python.exe -m ruff check .`, ` .\.venv\Scripts\python.exe -m ruff format --check .`, ` .\.venv\Scripts\python.exe -m scripts.check_ui`, then launch ` .\.venv\Scripts\python.exe -m streamlit run app.py`.
6. Run manual checks below against a **demo database**, not your personal tasks. Only push and open a PR when local checks pass.

## Optional separate demo database

```
.\.venv\Scripts\python.exe -m scripts.create_advanced_demo --output data/study-demo.db
$env:WORKSPACE_DB_PATH = (Resolve-Path '.\data\study-demo.db').Path
.\.venv\Scripts\python.exe -m streamlit run app.py
```

The generator refuses to overwrite existing files. If the file already exists, choose another filename. A demo created on Sunday late at night may be mostly unallocated because there is no time left this week. **Close this PowerShell window or run `Remove-Item Env:\WORKSPACE_DB_PATH` to return to your normal database.** Do not delete the demo database while the app is running.

## Five-minute live walkthrough

1. **Tasks:** Quick-create “Prepare for economics exam” (category Economics, deadline this Friday or Sunday, 180 estimated minutes). Add a checklist item “Download past papers” and timed steps “Revise Chapter 3” (60 minutes) and “Practice questions” (90 minutes). Verify task completion cannot be forced while steps are open.
2. **Calendar setup:** Add Tuesday 13:00–17:00 and Wednesday 10:00–12:00 as windows (use dates **today or later** in the current week for a live demo). Add a fixed “Economics lecture” Tue 14:00–15:00.
3. **Preview:** Generate revision. Explain why no study block overlaps the lecture, which task gets priority, which steps split, and where shortfalls appear with minute counts and deadlines. Compare minimal-change vs full-rescheduling change counts.
4. **Accept or reject:** Reject once, demonstrating no timetable changed. Generate again and accept; restart Streamlit and verify saved study sessions remain.
5. **Change the week:** Add an overlapping fixed appointment. See the immediate conflict warning; accepted rows remain unchanged. Generate revision, inspect moved and unchanged blocks, then accept.
6. **Missed/partial session:** After a planned session's end, click **Missed**; or after it starts, **Log work** with fewer minutes than originally planned. Preview how the remaining work is redistributed, then accept or reject. Sessions cannot be marked missed before they end. For a *date-controlled* demonstration without waiting for real time, run `python -m scripts.evaluate_advanced` instead of changing the PC clock.

## What to verify manually

- Parent task editing, deletion confirmation, quick Complete/Reopen and form resets still work.
- Mix of checklist and timed steps persists through a restart.
- Calendar hours and dates are correct in your local timezone; no two proposed study sessions overlap each other or a lecture.
- Adding/removing fixed events or windows flags conflicts with previously accepted sessions immediately.
- Preview and Reject leave the accepted calendar untouched; Accept applies it and persists after restart.
- If a new lecture is saved after a preview, the old preview cannot be accepted without regenerating.
- After a session is missed, the existing valid sessions remain in place whenever the greedy strategy permits.
- Dashboard remaining-work counts structured timed steps once, and its hourly planned-vs-free chart is readable.
- Empty week, no time windows, overdue steps and zero remaining work have useful messages.
- Fresh install, Ruff, UI smoke check and full pytest suite pass **on Windows Python 3.12**.
- Both students can explain the heuristic, invariants, transaction/fingerprint safety, and why greedy shortfalls do not prove impossibility.

## Submission gate

Verify current 2026–2027 course 20875 instructions, the November 27 date, any requirement for open-source work and lecturer approval using the actual 2026 brief; older public-page wording is not authoritative for this year's rubric.
