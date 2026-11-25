# Study DNA and deadline-safe planning (November 25, 2026)

This is an additive, local personalization update for Personal Workspace. It
reuses the existing Streamlit screens, SQLite task records, CP-SAT optimizer,
independent proposal validator, approval, and Undo. It adds no cloud accounts.

## What changes

- **Study DNA onboarding:** The Home page invites a first-time user to provide
  a display name and four preferences. The user can skip it. The new **Settings**
  page allows editing it later. Preferences live in the active local SQLite file;
  two people using separate laptop installations cannot overwrite each other's
  schedules.
- **Concentration:** The optimizer softly rewards study minutes inside the
  chosen best-focus window. It may schedule elsewhere to respect real commitments.
- **Session length:** A preference for shorter, balanced, or longer focus blocks
  changes the soft penalty for tiny sessions; it is not a minimum requirement.
- **Distribution:** Steady prefers the existing balance goal; concentrated-day
  planning uses a secondary CP-SAT objective that minimizes the number of active
  study days (after maximizing scheduled work). Both respect fixed commitments.
- **Flexibility:** Stable routines incur a stronger penalty for shifting study
  blocks; open schedules have a weaker movement penalty.
- **Must finish vs flexible:** Deadline-bearing tasks default to required.
  The Home/Tasks task form lets users mark work as optional. Legacy tasks are
  unaffected unless the user explicitly changes this flag.
- **Plan A / Plan B:** Inside the calendar's Rescue My Week preview, one action
  generates steady and concentrated-week alternatives. **Both require complete
  allocation of the remaining timed study work for required tasks due this
  week.** If either proposal has a shortfall, the UI does not offer it as a
  deadline-complete alternative. If they are identical, it says so.
- **Deadline radar:** Home reports required study minutes that the current
  quick preview could not place. This is an early warning, **not** proof that
  no feasible schedule exists.
- **Explicit approval of shortfalls:** When a preview leaves required timed work
  unscheduled, approving it requires a separate acknowledgment. The proposal
  remains read-only until approval, with the same safe validation and Undo.

## Important boundaries

"Deadline coverage" means remaining **timed study estimates** have proposed
slots before their due dates. It never means an exam or assignment has been
completed, nor does it cover a to-do that has no scheduled study estimate.
The optimizer is time-bounded, so failure to produce two complete alternatives
is **not proof of mathematical infeasibility**. When the workload cannot fit,
the planner surfaces the remaining time instead of hiding it.

Study DNA is stored locally but isn't a password-protected account. It doesn't
synchronize across devices. Daily available hours and fixed events still come
from Calendar and take priority over soft preferences.

## Implementation and testing

New modules: `workspace/study_dna.py`, `workspace/deadline_guarantees.py`,
`workspace/views/settings.py`; new focused tests cover local preference
persistence, validation, required-task flags, required coverage, UI comparisons,
and optional CP-SAT hard constraints.

Windows final verification from repository root:

```powershell
.\.venv\Scripts\python.exe -m ruff check . --fix
.\.venv\Scripts\python.exe -m ruff format .
.\.venv\Scripts\python.exe -m ruff check .
$testDir = Join-Path $env:USERPROFILE ("Downloads\study-dna-tests-" + [guid]::NewGuid().ToString("N"))
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp "$testDir"
.\.venv\Scripts\python.exe -m scripts.check_optimizer_ui
```

Manually verify: first-run onboarding, skip, save/edit Settings, two local demo
DB files, required/optional task flags, A/B comparison, a deliberately
impossible deadline, accepted-plan Undo, restart of desktop shortcut.
