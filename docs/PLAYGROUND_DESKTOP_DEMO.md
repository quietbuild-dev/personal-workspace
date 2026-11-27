# Safe full-workspace playground (Windows)

This ZIP contains a read-to-use sample SQLite database and a generator for a fresh demo.
**No changes to `data/workspace.db` or the normal Personal Workspace shortcut.**

## Quick start: generate an up-to-date demo and open the actual native desktop app

Run from the Personal Workspace repository in PowerShell:

```powershell
cd "C:\Users\Win\OneDrive\Desktop\personal-workspace"
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\personal-workspace-full-playground.zip" -DestinationPath . -Force
$demo = Join-Path $env:USERPROFILE ("Downloads\pw-playground-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".db")
.\.venv\Scripts\python.exe -m scripts.create_full_playground_demo --output "$demo"
if ($LASTEXITCODE -ne 0) { throw "Demo generation failed" }
.\.venv\Scripts\python.exe -m scripts.launch_playground_desktop --database "$demo"
```

The final command launches a **separate native WebView2 window** using the demo DB. The regular desktop shortcut always opens the real personal workspace. You can also open this demo in a browser:

```powershell
$env:WORKSPACE_DB_PATH = $demo
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8510
# Ctrl+C after browsing
Remove-Item Env:WORKSPACE_DB_PATH -ErrorAction SilentlyContinue
```

The demo file and matching .ics are in Downloads. Closing the demo does not delete changes you make to it; rerun the generator with a fresh filename for a reset.

## Alternatively: use the included starter data without generating it

```powershell
$demo = Join-Path $env:USERPROFILE ("Downloads\pw-playground-copy-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".db")
Copy-Item ".\samples\full-playground-20261126.db" $demo
.\.venv\Scripts\python.exe -m scripts.launch_playground_desktop --database "$demo"
```

## What is included

- 18 tasks spanning algorithms, statistics, SWE, ML, economics and personal administration.
- 53 fixed appointments and commitments: lectures, seminars, gym, yoga, birthdays, dinners, family calls, reading, social plans and monthly budget reviews.
- 36 days of date-specific study availability, with realistic study caps.
- A booked upcoming 90-minute study session (when generated on Thu Nov 26), suitable for Energy Today and Make Room for Life previews.
- Partial task progress for Deadline Runway.
- Last week's **55 completed minutes and 60 missed minutes** for Weekly Replay.
- A separate .ics file with two safe events to test Calendar Import.

## What to test

1. Home: Daily Briefing, weekly workload, Deadline Runway, Weekly Replay (select Last week).
2. Tasks: edit example tasks, mark checklist items, try Smart Task Capture with your own text.
3. Calendar: open the week shown by the generator, inspect study blocks, try Energy Today and Make Room for Life (preview before saving).
4. Schedule Lab: remove a 1-2 hour window and compare replanning.
5. Calendar Import: select the `.ics` file generated next to the demo DB in Downloads. Preview and import; retry to test duplicate handling.
6. Add your own birthday, lecture or social commitment to the demo; experiment freely.

## Daily / weekly / monthly / yearly recurring schedules

The sample includes individual occurrences that *look recurring*, but these **are not recurrence rules**. The current version's Calendar does not yet let you create an event that repeats automatically. Put this in the next product update: choose Never / Daily / Weekly / Monthly / Yearly; choose an optional end date; handle series editing vs one occurrence, exceptions, and duplicate prevention. Do not confuse the seeded examples with a finished recurrence feature.

## Safety

- Generator refuses the filename `workspace.db`, personal DB path, and any existing output file.
- Demo desktop launcher requires a specific marker in the demo database and refuses anything else.
- Nothing in this ZIP alters the regular desktop app launcher or scheduling algorithm.
- The generated `.db` and `.ics` files are local only, not uploaded or synchronized to GitHub.
- This ZIP is a test fixture, not a production upgrade. Avoid staging demo DB files in a git commit.
