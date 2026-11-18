"""Regression coverage for calendar usability and safe one-step undo."""

import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from workspace.advanced_planner import make_revision
from workspace.advanced_repository import (
    StaleProposalError,
    accept_revision,
    add_fixed_event,
    has_undo_plan,
    load_snapshot,
    save_week_preferences,
    undo_last_plan,
)
from workspace.models import TaskDraft
from workspace.quick_tasks import create_quick_task, enable_quick_planning
from workspace.repository import initialize_database, list_tasks
from workspace.views.schedule_comparison import before_after_html

TODAY = date(2026, 11, 17)
NOW = datetime(2026, 11, 17, 8, 0)


class CalendarV4Tests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db = Path(folder.name) / "test.db"
        initialize_database(self.db)

    def _planned(self):
        create_quick_task(
            self.db,
            TaskDraft("Statistics assignment", deadline=TODAY, priority=3),
        )
        save_week_preferences(self.db, (TODAY,), 120, 9 * 60, 13 * 60)
        snapshot = load_snapshot(self.db)
        accept_revision(self.db, make_revision(snapshot, NOW), NOW)

    def test_ordinary_to_do_does_not_generate_study_sessions(self):
        task_id = create_quick_task(
            self.db,
            TaskDraft("Take out trash", estimate_minutes=5),
            schedule=False,
        )
        self.assertEqual(len(list_tasks(self.db)), 1)
        self.assertFalse(load_snapshot(self.db).steps)
        self.assertTrue(enable_quick_planning(self.db, task_id))
        self.assertFalse(enable_quick_planning(self.db, task_id))
        self.assertEqual(len(load_snapshot(self.db).steps), 1)

    def test_undo_restores_previous_plan_and_is_one_level(self):
        self._planned()
        current = load_snapshot(self.db)
        self.assertEqual(len(current.sessions), 1)
        self.assertTrue(has_undo_plan(self.db))
        self.assertEqual(undo_last_plan(self.db, NOW), 0)
        self.assertFalse(load_snapshot(self.db).sessions)
        self.assertFalse(has_undo_plan(self.db))
        with self.assertRaisesRegex(ValueError, "no recent"):
            undo_last_plan(self.db, NOW)

    def test_undo_refuses_to_overwrite_new_events(self):
        self._planned()
        add_fixed_event(self.db, "New lecture", TODAY, 11 * 60, 12 * 60, "Lecture")
        self.assertFalse(has_undo_plan(self.db))
        with self.assertRaises(StaleProposalError):
            undo_last_plan(self.db, NOW)
        self.assertEqual(len(load_snapshot(self.db).sessions), 1)

    def test_undo_rejects_old_conflicting_session(self):
        self._planned()
        add_fixed_event(self.db, "Guest lecture", TODAY, 9 * 60, 10 * 60, "Lecture")
        snapshot = load_snapshot(self.db)
        revision = make_revision(snapshot, NOW)
        accept_revision(self.db, revision, NOW)
        self.assertTrue(has_undo_plan(self.db))
        fingerprint = load_snapshot(self.db).fingerprint
        with self.assertRaisesRegex(ValueError, "conflicts"):
            undo_last_plan(self.db, NOW)
        self.assertEqual(load_snapshot(self.db).fingerprint, fingerprint)
        self.assertEqual(
            [(s.start, s.end) for s in load_snapshot(self.db).sessions],
            [(10 * 60, 11 * 60)],
        )

    def test_comparison_is_neutral_and_uses_sage_new_blocks(self):
        self._planned()
        snapshot = load_snapshot(self.db)
        session = snapshot.sessions[0]
        from workspace.advanced_planner import Slot

        old = (Slot(session.step_id, TODAY, session.start, session.end),)
        new = (Slot(session.step_id, TODAY + timedelta(days=1), 900, 960),)
        html = before_after_html(TODAY, (), old, new, {s.id: s for s in snapshot.steps})
        self.assertIn("#3f4a48", html)
        self.assertIn("#668b70", html)
        self.assertNotIn("#775d35", html)


if __name__ == "__main__":
    unittest.main()
