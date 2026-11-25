"""Exercise goal preview/compare/approve/undo and task dependencies on disposable data."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from workspace.advanced_planner import week_bounds
from workspace.advanced_repository import add_window, load_snapshot
from workspace.models import TaskDraft
from workspace.quick_tasks import create_quick_task


def main():
    now = datetime.now()
    _, sunday = week_bounds(now.date())
    # Small tasks and future windows keep this check independent of time of day.
    with tempfile.TemporaryDirectory() as directory:
        db = Path(directory) / "ui.db"
        first = create_quick_task(db, TaskDraft("Research", deadline=sunday, estimate_minutes=5))
        second = create_quick_task(
            db, TaskDraft("Write report", deadline=sunday, estimate_minutes=5)
        )
        day = now.date()
        while day <= sunday:
            start = now.hour * 60 + now.minute + 2 if day == now.date() else 540
            if start <= 1428:
                add_window(db, day, start, min(1440, start + 30))
            day += timedelta(days=1)
        if not load_snapshot(db).windows:
            raise RuntimeError("Run this UI check before the final 12 minutes of Sunday.")
        root = Path(__file__).resolve().parents[1]
        with patch("workspace.repository.DEFAULT_DB_PATH", db):
            app = AppTest.from_file(str(root / "app.py"), default_timeout=40).run()
            app.switch_page("workspace/views/week.py").run()
            assert not app.exception
            before = load_snapshot(db)
            app.button(key="generate_goal_preview").click().run()
            assert not app.exception
            assert load_snapshot(db) == before, "Preview wrote data"
            app.button(key="compare_goals").click().run()
            assert not app.exception
            assert len(app.dataframe) >= 1
            app.selectbox(key="optimizer_goal").select("routine").run()
            assert not app.exception
            assert load_snapshot(db) == before, "Goal comparison wrote data"
            app.button(key="accept_rescue_plan").click().run()
            assert not app.exception
            assert len(load_snapshot(db).sessions) > 0
            app.button(key="undo_last_plan").click().run()
            assert not app.exception
            assert load_snapshot(db).sessions == ()
            app.switch_page("workspace/views/task_board.py").run()
            app.button(key=f"details_{second}").click().run()
            assert not app.exception
            app.multiselect(key=f"prerequisites_{second}").set_value([first])
            next(b for b in app.button if b.label == "Save prerequisites").click().run()
            assert not app.exception
            assert len(load_snapshot(db).dependencies) == 1
            app.multiselect(key=f"prerequisites_{second}").set_value([])
            next(b for b in app.button if b.label == "Save prerequisites").click().run()
            assert not app.exception
            assert load_snapshot(db).dependencies == ()
    print("OK: goal previews, comparison, approval, Undo and dependency editing on temporary data")


if __name__ == "__main__":
    main()
