"""Smoke-test Calendar planning and task dependencies using a disposable database.

This follows the current UI: Plan my week -> Preview schedule -> Compare goals;
Tasks -> Details -> More details. No personal database is opened.
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from workspace.advanced_planner import week_bounds
from workspace.advanced_repository import add_window, load_snapshot
from workspace.models import TaskDraft
from workspace.quick_tasks import create_quick_task


def _no_exceptions(app: AppTest, stage: str) -> None:
    if app.exception:
        raise AssertionError(f"{stage}: Streamlit reported {app.exception}")


def _click(app: AppTest, key: str, stage: str) -> AppTest:
    try:
        button = app.button(key=key)
    except KeyError as exc:
        raise AssertionError(f"{stage}: expected button '{key}' was not shown") from exc
    if button.disabled:
        raise AssertionError(f"{stage}: button '{key}' was disabled")
    result = button.click().run()
    _no_exceptions(result, stage)
    return result


def _setup(now: datetime, db: Path) -> tuple[int, int]:
    _, sunday = week_bounds(now.date())
    # New study sessions must meet the planner's 20-minute minimum.
    first = create_quick_task(db, TaskDraft("Research", deadline=sunday, estimate_minutes=25))
    second = create_quick_task(
        db, TaskDraft("Write report", deadline=sunday, estimate_minutes=25)
    )
    day = now.date()
    while day <= sunday:
        # Use plausible daytime availability even when this checker runs at night.
        start = 9 * 60
        if day == now.date():
            current = now.hour * 60 + now.minute + 10
            start = max(start, ((current + 4) // 5) * 5)
        end = min(22 * 60, start + 3 * 60)
        if end - start >= 60:
            add_window(db, day, start, end)
        day += timedelta(days=1)
    if not load_snapshot(db).windows:
        raise RuntimeError("No usable study window remains before the end of Sunday.")
    return first, second


def main() -> None:
    now = datetime.now()
    with tempfile.TemporaryDirectory(prefix="pw-optimizer-ui-") as directory:
        db = Path(directory) / "ui.db"
        first, second = _setup(now, db)
        root = Path(__file__).resolve().parents[1]
        with patch("workspace.repository.DEFAULT_DB_PATH", db):
            app = AppTest.from_file(str(root / "app.py"), default_timeout=70).run()
            _no_exceptions(app, "App startup")
            app.switch_page("workspace/views/week.py").run()
            _no_exceptions(app, "Calendar startup")
            before = load_snapshot(db)

            # The preview is now intentionally hidden until Plan my week is clicked.
            app = _click(app, "calendar_plan_week", "Open weekly planner")
            app = _click(app, "generate_goal_preview", "Preview weekly plan")
            assert load_snapshot(db) == before, "Preview changed the saved calendar"
            print("OK: weekly plan preview is read-only")

            app = _click(app, "compare_goals", "Compare planning goals")
            assert any(
                "pw-goal-table" in str(markdown.value) for markdown in app.markdown
            ), "The comparison table did not appear"
            app.selectbox(key="optimizer_goal").select("routine").run()
            _no_exceptions(app, "Select another goal")
            assert load_snapshot(db) == before, "Selecting a goal changed saved data"
            app.selectbox(key="optimizer_goal").select("deadlines").run()
            _no_exceptions(app, "Return to deadline-focused goal")
            print("OK: comparison and goal switching are read-only")

            app = _click(app, "accept_rescue_plan", "Save proposed weekly plan")
            assert len(load_snapshot(db).sessions) > 0, "Saving created no sessions"
            app = _click(app, "undo_last_plan", "Undo saved weekly plan")
            assert load_snapshot(db).sessions == (), "Undo did not restore empty calendar"
            print("OK: plan approval and Undo")

            app.switch_page("workspace/views/task_board.py").run()
            _no_exceptions(app, "Tasks startup")
            app = _click(app, f"details_{second}", "Open task summary")
            app = _click(app, f"task_more_button_{second}", "Open full task details")
            app.multiselect(key=f"prerequisites_{second}").set_value([first])
            submit = next(
                (button for button in app.button if button.label == "Save prerequisites"),
                None,
            )
            assert submit is not None, "Prerequisites form not shown"
            app = submit.click().run()
            _no_exceptions(app, "Save task prerequisite")
            assert len(load_snapshot(db).dependencies) == 1, "Prerequisite not saved"

            # The task details may remain open or close after saving; support either.
            try:
                app.multiselect(key=f"prerequisites_{second}")
            except KeyError:
                app = _click(app, f"details_{second}", "Reopen task summary")
                app = _click(app, f"task_more_button_{second}", "Reopen full details")
            app.multiselect(key=f"prerequisites_{second}").set_value([])
            submit = next(
                (button for button in app.button if button.label == "Save prerequisites"),
                None,
            )
            assert submit is not None, "Prerequisites form not shown for removal"
            app = submit.click().run()
            _no_exceptions(app, "Remove task prerequisite")
            assert load_snapshot(db).dependencies == (), "Prerequisite not removed"
            print("OK: task dependencies save and remove")
    print("PASS: Calendar planning, comparison, approval, Undo, and task dependencies")


if __name__ == "__main__":
    main()
