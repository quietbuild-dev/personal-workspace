# MVP automated tests

Run `python -m pytest` from the project root with your project's Python 3.12
virtual environment. Existing core task tests are in `test_tasks.py` and
`test_task_editing.py`. The added `test_planner.py`, `test_metrics.py`,
`test_availability_and_integration.py`, `test_demo_script.py` and
`test_view_logic_smoke.py` cover the new feature boundaries and simulated UI
forms. The six view-logic tests use a Streamlit stand-in, not the actual library.

The planner tests use fixed dates and a reproducible randomized suite of 200
scenarios. Database tests use temporary SQLite files; they never open the
personal database. The migration test creates an old-schema SQLite DB and
verifies the new availability table can be added without losing tasks.

**Do not confuse** successful unit/integration tests with browser verification:
run `python -m scripts.check_ui` (with Streamlit installed) and the checklist
in `docs/DEMO_WALKTHROUGH.md` before release.
