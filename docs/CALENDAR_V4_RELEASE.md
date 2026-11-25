# Calendar V4 — clarity, visual hierarchy, and safe undo

## Product decisions implemented

- **Home**: Today's Focus and Due This Week, prominent task titles, smaller color-coded priority badges (high: muted red; medium: warm ochre; low: neutral); the large rescue comparison lives only in Calendar. Home displays a short notice only for meaningful planning issues.
- **Task editing**: saving closes details; finishing every checklist item offers to mark its task complete. Selecting Partly on Home also shows its checklist, and the same checklist appears when selecting a calendar session.
- **Task creation**: plain **Deadline** and **Due time** labels, lowercase `hh:mm` placeholder, consistent field font sizing. You can uncheck **Add study time to my calendar** to create a to-do only. You may opt that task into study planning later through its details; task creation and checklist persistence are unaffected.
- **Study preferences**: earliest start, latest finish, and one decimal **Study hours** input; e.g., `2.5` for 2h30. Busy events are excluded by the existing planner constraints.
- **Calendar**: Day/Week, previous/next arrows, Today, date picker without “Browse date”, study/session badges for priority, deadline information and next incomplete checklist item (when there is room), stronger calendar contrast, event-type colors, in-place details, grouped and collapsed agenda.
- **Rescue my week**: single collapsed entry in Calendar; once opened, side-by-side Before/After timelines appear directly. Neutral previous-time outline instead of yellow, sage proposed time, unchanged blocks faded. Technical change lists are accessible but hidden by default; tiny shortfalls are in an additional section, serious deadline risks use red.
- **One-step Undo**: after accepting a plan, Restore the previous accepted sessions transactionally. The operation refuses if a task, event, preference, or session has changed since acceptance, or if restoring the old sessions would conflict with current events or limits. It never blindly erases subsequent work. Full version history and global undo are intentionally out of scope.

## Colors and meaning

| UI element | Color | Meaning |
|---|---|---|
| Study blocks | Sage | Scheduled work |
| Lectures | Blue-gray | Fixed university classes |
| Social | Violet | Social plans |
| Exercise | Muted green | Exercise |
| Personal | Warm gray-brown | Personal events |
| High priority | Muted red small badge | Task importance |
| Medium priority | Warm neutral small badge | Task importance |
| Low priority | Gray-green small badge | Task importance |
| Previous schedule | Neutral dashed | Position before a change |
| Proposed schedule | Sage | Suggested time after a change |
| Serious deadline risk | Red callout | Material unscheduled work/overdue |

Priority badges and the background type color are separate dimensions; the entire calendar block is not painted red for priority.

## Test status

- **150 Python tests and 58 subtests** passed in the release build using Python 3.13, including undo, opt-in scheduling, conflict rejection, and old-engine regression tests.
- Python `compileall` passed and edited Python lines were checked for length <=100 characters.
- **Not yet verified here**: Ruff (not installed) and running the real Streamlit UI in a browser (Streamlit not installed). These are required release checks on the student's Windows environment.

## Windows verification

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.check_ui
```

Open a separate demo with `& ".\Launch Sample Workspace.bat"` (the name of the old launcher is unchanged; source files are V4). Verify: task creation with and without study scheduling; priority badges; changing tasks and checking subtasks; calendar date arrows and current-day reset; editing one block in the same tab; viewing Before/After; accepting and undoing a conflict-free plan; intentionally adding a lecture and checking undo is safely refused.

The demo runs on an isolated database at `data/calendar-v3-demo.db`, not `data/workspace.db`. Do **not** copy its DB over personal data. The ZIP contains no database, `.venv`, or `.git` folders.
