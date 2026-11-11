"""Editing and completion behavior against an isolated SQLite database."""

import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from workspace.models import TaskDraft, revise_task
from workspace.repository import create_task, initialize_database, list_tasks, update_task


class TaskEditingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Path(self.directory.name) / "tasks.db"
        initialize_database(self.db)
        self.draft = TaskDraft("Prepare demo", "University", date(2026, 11, 26), 3, 90)
        self.task = create_task(self.db, self.draft)

    def test_edit_details_persists_without_changing_identity(self):
        draft = TaskDraft(" Revised demo ", "Work", date(2026, 11, 27), 1, 120)
        revised = update_task(self.db, self.task.id, draft, 100)
        self.assertEqual(list_tasks(self.db), [revised])
        self.assertEqual(revised.id, self.task.id)
        self.assertEqual(revised.created_at, self.task.created_at)
        self.assertEqual(revised.title, "Revised demo")
        self.assertEqual(revised.category, "Work")
        self.assertEqual(revised.deadline, draft.deadline)
        self.assertEqual(revised.priority, 1)
        self.assertEqual(revised.estimate_minutes, 120)

    def test_partial_work_keeps_task_pending(self):
        revised = update_task(self.db, self.task.id, self.draft, 30)
        self.assertEqual(revised.remaining_minutes, 30)
        self.assertEqual(revised.estimate_minutes, 90)
        self.assertEqual(revised.status, "pending")
        self.assertIsNone(revised.completed_at)
        self.assertEqual(list_tasks(self.db)[0], revised)

    def test_zero_remaining_completes_and_persists(self):
        revised = update_task(self.db, self.task.id, self.draft, 0)
        self.assertEqual(revised.status, "completed")
        self.assertEqual(revised.remaining_minutes, 0)
        self.assertIsNotNone(revised.completed_at.utcoffset())
        self.assertEqual(list_tasks(self.db)[0], revised)

    def test_positive_remaining_reopens_and_clears_completion_time(self):
        update_task(self.db, self.task.id, self.draft, 0)
        reopened = update_task(self.db, self.task.id, self.draft, 15)
        self.assertEqual(reopened.status, "pending")
        self.assertEqual(reopened.remaining_minutes, 15)
        self.assertIsNone(reopened.completed_at)
        self.assertEqual(list_tasks(self.db)[0], reopened)

    def test_editing_completed_task_preserves_completion_time(self):
        completed = update_task(self.db, self.task.id, self.draft, 0)
        revised = update_task(self.db, self.task.id, TaskDraft("New title"), 0)
        self.assertEqual(revised.completed_at, completed.completed_at)
        self.assertEqual(revised.status, "completed")
        self.assertEqual(revised.title, "New title")

    def test_recompletion_uses_new_time_without_mutating_input(self):
        first_time = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
        second_time = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
        completed = revise_task(self.task, self.draft, 0, now=first_time)
        reopened = revise_task(completed, self.draft, 20)
        recompleted = revise_task(reopened, self.draft, 0, now=second_time)
        self.assertEqual(completed.completed_at, first_time)
        self.assertEqual(recompleted.completed_at, second_time)
        self.assertEqual(self.task.remaining_minutes, 90)
        self.assertEqual(reopened.remaining_minutes, 20)

    def test_invalid_remaining_rolls_back_without_changes(self):
        for value in [-1, 91, 1.5, True, "30", None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                update_task(self.db, self.task.id, self.draft, value)
            self.assertEqual(list_tasks(self.db), [self.task])
        # A later valid write succeeds after all failed transactions.
        self.assertEqual(update_task(self.db, self.task.id, self.draft, 30).remaining_minutes, 30)

    def test_invalid_ids_do_not_write(self):
        for value in [0, -1, True, 1.5, "1", 2**63]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                update_task(self.db, value, self.draft, 30)
        self.assertEqual(list_tasks(self.db), [self.task])

    def test_missing_task_is_not_silently_created(self):
        with self.assertRaisesRegex(ValueError, "no longer exists"):
            update_task(self.db, self.task.id + 100, self.draft, 30)
        self.assertEqual(list_tasks(self.db), [self.task])

    def test_duplicate_titles_have_independent_edits(self):
        other = create_task(self.db, self.draft)
        changed = update_task(self.db, self.task.id, self.draft, 10)
        self.assertEqual(list_tasks(self.db), [other, changed])

    def test_estimate_must_cover_remaining_work(self):
        with self.assertRaises(ValueError):
            update_task(self.db, self.task.id, TaskDraft("Smaller", estimate_minutes=20), 30)
        self.assertEqual(list_tasks(self.db), [self.task])
        increased = update_task(
            self.db, self.task.id, TaskDraft("More work", estimate_minutes=120), 110
        )
        self.assertEqual(increased.estimate_minutes, 120)
        self.assertEqual(increased.remaining_minutes, 110)

    def test_deadline_can_be_cleared(self):
        cleared = update_task(self.db, self.task.id, TaskDraft("No deadline"), 30)
        self.assertIsNone(cleared.deadline)
        self.assertIsNone(list_tasks(self.db)[0].deadline)


if __name__ == "__main__":
    unittest.main()
