# MVP verification record — draft as of 12 November 2026

## Advanced milestone isolated-environment checks (12 November 2026)

- Previous 57 MVP tests: still passing.
- Additional advanced scheduling, persistence, migration, parent/child integration,
  replay prevention, stale-proposal validation, demo generation and algorithm
  comparison tests: **82 total passed** plus 44 `unittest.subTest` cases in pytest,
  Python 3.13.5 / pytest 9.0.2. Standard-library `unittest` also passed 82 tests.
- Controlled baseline: 12 timed steps and a simulated missed session; both methods
  scheduled 1080 minutes with 360-minute heuristic shortfalls. Preserving existing
  sessions retained 9 unchanged versus 0 with full rescheduling. Runtime varies
  by machine; see `python -m scripts.evaluate_advanced --repeats 100`.
- **Not verified in this environment:** actual Streamlit browser rendering,
  Windows Python 3.12, Ruff lint/format, real user database migration,
  GitHub PR status or course rubric. Students should fill in these checks on
  their own computer; an isolated test pass does not imply deployment completion.

---

This is a reproducible record, **not** a claim that the full product has been
browser tested or installed on a new Windows environment.

## Checks that actually ran in the assistant's temporary build environment

| Check | Result | Environment / limitation |
| --- | --- | --- |
| Original 21 task tests | Passed | Python 3.13.5, temporary SQLite DBs |
| Expanded pytest suite | **57 passed** (44 subtests) | Python 3.13.5, pytest 9.0.2 |
| Python module compile check | Passed | `python -m compileall -q app.py workspace` |
| Demo DB creation and refuse-overwrite behavior | Passed | Temporary database; never used personal task DB |
| Plotly import | Available, 6.5.2 | Does not establish Streamlit chart rendering |
| Page form paths using a lightweight Streamlit stand-in | 6 passed | Basic view control flow against real temp SQLite; **not actual Streamlit or a browser** |
| Streamlit app / local browser interaction | **Not tested here** | Streamlit not installed; pip download failed because DNS/network unavailable |
| Ruff lint / format checks | **Not tested here** | Ruff unavailable; pip download failed |
| Python 3.12 runtime and fresh Windows install | **Not tested here** | Assistant runtime is Python 3.13.5 |
| Current Git branch merge or PR state | **Not verified remotely** | Uploaded ZIP intentionally lacks `.git` metadata |

New tests: planner 13, metrics 7, availability / migration / integration 8,
demo generator 2, simulated Streamlit view paths 6, plus the original 21 = 57 total. Planner scenarios include
200 fixed-seed runs of the main invariants. All tests use temporary database
files; no user DB was available to, or modified by, the test runner.

## Student Windows verification — fill in after running

| Check | Result / date / notes |
| --- | --- |
| `py -3.12 --version` | Pending |
| `.\.venv\Scripts\python.exe -m pytest` | Pending |
| `.\.venv\Scripts\python.exe -m ruff check .` | Pending |
| `.\.venv\Scripts\python.exe -m ruff format --check .` | Pending |
| `.\.venv\Scripts\python.exe -m scripts.check_ui` | Pending |
| Manual browser checklist (see DEMO_WALKTHROUGH.md) | Pending |
| Old database copy migrated without task data loss | Pending |
| Fresh venv install and pip freeze lock review | Pending |
| Peer review, PR, merge to `main` | Pending |
| 2026 assignment brief and lecturer approval | Pending |

If a check fails, keep the failure visible here and fix the actual issue
before labeling the deliverable release-ready.
