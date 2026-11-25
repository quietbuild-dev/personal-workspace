# Final experience upgrade (November 25, 2026)

This patch builds on the goal-based optimizer and the simplified Rescue My Week interface.
It is deliberately a separate, reviewable change, not a replacement of the planner.

## What changed

- **Plan my week:** The Home and Calendar pages have a single entry button that opens a goal-based preview. It uses the same `optimize` function, proposal validator and transactional approval path as Rescue My Week. Nothing is saved until approval. Switching goals still uses the existing preview cache.
- **Subtasks:** A new task can include several checklist items, one per line. The existing task view accepts multiple new checklist items in one action. Input lengths are checked before creating items. Existing dependency editing and task categories remain available.
- **Explain differences:** The optional goal comparison can state how the chosen result differs from Keep my routine in deadline coverage, high-priority coverage and existing blocks changed. It describes the actual metrics and never claims that reserved time means completed work.
- **Study session quality:** The optimizer's *third*, tie-breaking objective now favors fewer sub-25-minute fragments and smaller shifts of existing blocks. The primary goal is unchanged: deadlines, priority, preservation, throughput or peak daily load. Tiny blocks remain valid when time is scarce. The new `session_shift_minutes` benchmark metric pairs each original block with at most one suggested block of the same task and measures how far its start time moved; it is an explanatory heuristic, not a minimum-cost matching proof.
- **Calendar export:** A read-only `.ics` download exports *accepted planned* study sessions and fixed commitments in the selected week. It does not export unapproved plans or completed historical study sessions, and does not contact a calendar service. Times use floating local calendar time (no timezone conversion).
- **Benchmark summary:** `python -m scripts.summarize_optimizer_benchmark --csv docs/optimizer-benchmark.csv` summarizes all scenarios and repeats with median values, constraint violations and per-scenario differences from greedy rebuild. Regenerate the CSV using `scripts.evaluate_optimizer` to include the newly added `session_shift_minutes` column.
- **Embedded Windows window (already on `feat/native-desktop-window`):** The optional native desktop launcher uses `pywebview`/WebView2 rather than a normal Edge browser profile. The local Streamlit server still runs invisibly while the window is open. This is *not* an independently installable EXE.

## Checks before merging

From the Windows feature branch, after creating a backup of your personal data:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m ruff check .
$testDir = Join-Path $env:USERPROFILE ("Downloads\pw-final-" + [guid]::NewGuid().ToString("N"))
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp "$testDir"
.\.venv\Scripts\python.exe -m scripts.check_optimizer_ui
```

Then test the *native desktop* on Windows: open the shortcut, add a task with subtasks, click Plan my week, switch goals, preview and approve **in a demo database** (not your personal one), test Undo, download an `.ics` file and import it into a calendar, and close the window. Check that it closes the server and does not launch a normal Edge profile.

The source snapshot used to prepare this patch does not have the installed Windows GUI/runtime or OR-Tools in the review environment. Pure Python tests were run; CP-SAT and end-to-end Windows checks must be rerun on the laptop. Do not merge if any of them fail.

## Known limits

The model's time horizon remains the current week. The scheduling heuristic and optimizer can both return a feasible partial plan; neither guarantees every deadline. The optimizer's third objective is a *soft preference*, not a ban on short study blocks. Task checklist updates are persisted through existing per-item database operations; they do not form one atomic multi-item transaction. The Windows desktop launcher still requires the project folder, `.venv`, WebView2 and a local server; Mac packaging and iOS are not part of this patch.
