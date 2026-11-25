# Make Room for Life — Calendar feature

This small, opt-in feature lets the user reserve a time interval (for example Friday 17:00–22:00) without moving fixed events. It uses the existing bounded CP-SAT optimizer or safe greedy fallback to propose alternative study slots around a temporary, in-memory personal event.

**User flow:** Calendar → "Make room for life · Protect personal time" → choose day and hours → Preview free time → inspect preserved/changed study blocks and before/after → Protect this time (or Cancel). Only the final action writes to SQLite. The protected time becomes a Personal event, shown in the existing Calendar.

**Correctness:** No preview writes. The app rejects windows overlapping fixed events, the past, or outside the current planning week. A preview is not approved if it would reduce already-booked due-study work or fail required-deadline coverage. Before approval, database fingerprints, window validity, requirements, and schedule constraints are checked again. Event, scheduled sessions, and Undo metadata commit in one SQLite transaction; failures roll back everything. Calendar's usual Undo removes the protected event and restores the previous schedule together, but only while the state is unchanged.

**Scope:** Only the current week; no recurring protected periods, no automatic movement of fixed lectures or other events. Completing study time still requires explicit user action. This adds `workspace/life_planning.py`, `workspace/views/life_time.py`, `tests/test_life_planning.py`, and a three-point integration into `workspace/views/week.py`. No changes to the existing optimizer or database schema migration path are required; the Undo marker table is initialized lazily upon approval.

**Run focused tests:** `python -m pytest -q tests/test_life_planning.py`

## Safe application and demo

1. Update local `main` from `origin/main`, check for uncommitted tracked changes, then make a new feature branch.
2. Extract `make-room-for-life-patch.zip` in the repository root, and run `python scripts/install_make_room.py`.
3. Verify lint and tests before running the app.
4. To demo, create a fresh DB using `python -m scripts.create_life_demo --output data/<unique-name>.db`. Set `WORKSPACE_DB_PATH` to that absolute file path in the same terminal before running Streamlit. Remove the environment variable afterwards.
5. Merge only after reviewing `git diff`, and update local `main` again; the desktop shortcut should point to this same project folder.

The ZIP intentionally omits private data, virtual environments, and entire replacements for existing application files.
