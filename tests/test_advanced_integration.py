"""Legacy task compatibility and the hourly planner's cross-component behavior."""

import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from workspace.advanced_planner import accepted_conflicts, make_revision
from workspace.advanced_repository import (
    accept_revision,
    add_step,
    add_window,
    delete_window,
    initialize_advanced,
    load_snapshot,
    set_checklist_done,
    set_timed_remaining,
)
from workspace.models import TaskDraft
from workspace.overview import load_overview
from workspace.repository import (
    create_task,
    initialize_database,
    list_tasks,
    save_availability,
    set_task_completion,
    update_task,
)

TUESDAY = date(2026, 11, 17)
NOW = datetime(2026, 11, 17, 8, 0)


class CrossComponentIntegrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "original.db"
        initialize_database(self.db)
        self.task = create_task(self.db, TaskDraft("Study for exam", "University", TUESDAY, 3, 180))
        initialize_advanced(self.db)
        self.step = add_step(self.db, self.task.id, "Review notes", "timed", 60)
        self.check = add_step(self.db, self.task.id, "Download notes", "checklist")

    def test_parent_is_not_double_scheduled_in_legacy_daily_planner(self):
        save_availability(self.db, {TUESDAY: 180})
        overview = load_overview(self.db, TUESDAY)
        self.assertEqual(overview.metrics.remaining_minutes, 60)
        self.assertEqual(overview.plan.allocations, ())
        self.assertEqual(overview.metrics.open_tasks, 1)

    def test_parent_cannot_complete_before_detailed_steps(self):
        with self.assertRaisesRegex(ValueError, "Complete all"):
            set_task_completion(self.db, self.task.id, completed=True)
        with self.assertRaisesRegex(ValueError, "Complete all"):
            update_task(
                self.db, self.task.id, TaskDraft("Study for exam", "University", TUESDAY, 3, 180), 0
            )
        set_checklist_done(self.db, self.check, True)
        set_timed_remaining(self.db, self.step, 0)
        set_task_completion(self.db, self.task.id, completed=True)
        self.assertEqual(list_tasks(self.db)[0].status, "completed")

    def test_removing_a_window_flags_existing_accepted_sessions(self):
        window_id = add_window(self.db, TUESDAY, 9 * 60, 11 * 60)
        snap = load_snapshot(self.db)
        accept_revision(self.db, make_revision(snap, NOW), NOW)
        self.assertEqual(len(load_snapshot(self.db).sessions), 1)
        delete_window(self.db, window_id)
        self.assertTrue(accepted_conflicts(load_snapshot(self.db), NOW))
        # No automatic acceptance/reordering occurred.
        self.assertEqual(len(load_snapshot(self.db).sessions), 1)

    def test_contiguous_windows_are_treated_as_one_long_availability(self):
        add_window(self.db, TUESDAY, 9 * 60, 10 * 60)
        add_window(self.db, TUESDAY, 10 * 60, 11 * 60)
        proposal = make_revision(load_snapshot(self.db), NOW)
        self.assertEqual(len(proposal.slots), 1)
        self.assertEqual(proposal.slots[0].minutes, 60)

    def test_deadline_day_is_eligible(self):
        add_window(self.db, TUESDAY, 15 * 60, 16 * 60)
        proposal = make_revision(load_snapshot(self.db), NOW)
        self.assertEqual(proposal.planned_minutes, 60)
        self.assertFalse(proposal.shortfalls)


if __name__ == "__main__":
    unittest.main()
