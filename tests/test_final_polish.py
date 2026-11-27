"""Regression checks for the final visual and navigation polish.

No live browser is required; Streamlit smoke checks run separately on Windows.
"""

import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from workspace.home_view_logic import completed_today, due_display, focus_tasks

ROOT = Path(__file__).resolve().parents[1]


def task(task_id, *, due=None, status="pending", priority=2, finished=None):
    return SimpleNamespace(
        id=task_id,
        title=f"Task {task_id}",
        deadline=due,
        status=status,
        priority=priority,
        completed_at=finished,
    )


class HomePolishTests(unittest.TestCase):
    def setUp(self):
        self.today = date.today()

    def test_focus_is_for_today_and_overdue_not_just_any_upcoming_task(self):
        earlier = task(1, due=self.today - timedelta(days=1))
        tomorrow = task(2, due=self.today + timedelta(days=1), priority=3)
        planned = task(3)
        complete = task(4, due=self.today, status="completed")
        overview = SimpleNamespace(
            tasks=(earlier, tomorrow, planned, complete),
            advanced=SimpleNamespace(
                steps=(SimpleNamespace(id=91, task_id=3),),
                sessions=(
                    SimpleNamespace(
                        step_id=91,
                        day=self.today,
                        status="planned",
                    ),
                ),
            ),
        )
        self.assertEqual([t.id for t in focus_tasks(overview, self.today)], [3])

    def test_completed_today_uses_actual_timestamp(self):
        completed = datetime.now(timezone.utc)
        yesterday = completed - timedelta(days=1)
        overview = SimpleNamespace(
            tasks=(
                task(1, status="completed", finished=completed),
                task(2, status="completed", finished=yesterday),
                task(3, status="pending"),
            )
        )
        self.assertEqual(
            [t.id for t in completed_today(overview, completed.astimezone().date())], [1]
        )

    def test_overdue_text_is_not_due_overdue(self):
        value = due_display(task(9, due=self.today - timedelta(days=1)), {9: 1200}, self.today)
        self.assertTrue(value.startswith("Overdue · due"))
        self.assertIn("20:00", value)
        self.assertNotIn("Due Overdue", value)

    def test_copy_and_icon_match_decisions(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        home = (ROOT / "workspace/views/home.py").read_text(encoding="utf-8")
        board = (ROOT / "workspace/views/task_board.py").read_text(encoding="utf-8")
        week = (ROOT / "workspace/views/week.py").read_text(encoding="utf-8")
        self.assertIn(":material/event_available:", app)
        self.assertNotIn("Your tasks, deadlines and one sensible next step.", home)
        self.assertNotIn("One place to capture work, check off steps", board)
        self.assertNotIn("Your week, at a glance", week)
        self.assertIn("Completed today", home)
        self.assertIn('st.switch_page("workspace/views/task_board.py")', home)
        self.assertIn("choose_goal_preview(", week)
        self.assertNotIn('st.caption(f"Selected: {selected}")', week)

    def test_desktop_shortcut_is_nonprivileged_and_uses_project_launcher(self):
        ps = (ROOT / "scripts/create_desktop_shortcut.ps1").read_text(encoding="utf-8")
        self.assertIn("WScript.Shell", ps)
        self.assertIn("Launch Personal Workspace Desktop.vbs", ps)
        self.assertTrue((ROOT / "assets/personal-workspace.ico").is_file())
        self.assertNotIn("Register-ScheduledTask", ps)


if __name__ == "__main__":
    unittest.main()
