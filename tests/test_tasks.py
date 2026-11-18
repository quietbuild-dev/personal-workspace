"""Behavior tests runnable with pytest or standard-library unittest."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

from workspace.models import TaskDraft
from workspace.repository import create_task, initialize_database, list_tasks


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Path(self.directory.name) / "data" / "test.db"
        initialize_database(self.db)

    def test_empty_database(self):
        self.assertEqual(list_tasks(self.db), [])

    def test_reopen_preserves_all_fields(self):
        draft = TaskDraft("  SWE demo  ", " University ", date(2026, 11, 26), 3, 90)
        saved = create_task(self.db, draft)
        # list_tasks opens a separate connection after the writing connection closes.
        self.assertEqual(list_tasks(self.db), [saved])
        self.assertEqual(saved.title, "SWE demo")
        self.assertEqual(saved.category, "University")
        self.assertEqual(saved.deadline, draft.deadline)
        self.assertEqual(saved.priority, 3)
        self.assertEqual(saved.estimate_minutes, 90)
        self.assertEqual(saved.remaining_minutes, 90)
        self.assertEqual(saved.status, "pending")
        self.assertIsNone(saved.completed_at)
        self.assertIsNotNone(saved.created_at.utcoffset())

    def test_reinitialization_preserves_records(self):
        saved = create_task(self.db, TaskDraft("Read notes"))
        initialize_database(self.db)
        self.assertEqual(list_tasks(self.db), [saved])

    def test_optional_deadline(self):
        saved = create_task(self.db, TaskDraft("Read notes"))
        self.assertIsNone(saved.deadline)
        self.assertIsNone(list_tasks(self.db)[0].deadline)

    def test_past_deadline_can_be_stored(self):
        saved = create_task(self.db, TaskDraft("Overdue", deadline=date(2000, 1, 1)))
        self.assertEqual(saved.deadline, date(2000, 1, 1))

    def test_stable_distinct_ids_newest_first(self):
        first = create_task(self.db, TaskDraft("First"))
        second = create_task(self.db, TaskDraft("Second"))
        self.assertGreater(second.id, first.id)
        self.assertEqual(list_tasks(self.db), [second, first])

    def test_sql_like_title_is_plain_text(self):
        title = "Read O'Reilly; DROP TABLE tasks; --"
        create_task(self.db, TaskDraft(title))
        create_task(self.db, TaskDraft("Another task"))
        self.assertEqual(list_tasks(self.db)[1].title, title)

    def test_invalid_inputs_do_not_write(self):
        cases = [
            {"title": "  "},
            {"title": "x" * 121},
            {"category": ""},
            {"category": "x" * 41},
            {"priority": 0},
            {"priority": 4},
            {"priority": True},
            {"estimate_minutes": 0},
            {"estimate_minutes": -5},
            {"estimate_minutes": 1.5},
            {"estimate_minutes": True},
            {"estimate_minutes": 2**63},
            {"deadline": "2026-11-26"},
            {"deadline": datetime(2026, 11, 26)},
        ]
        for values in cases:
            with self.subTest(values=values), self.assertRaises(ValueError):
                create_task(self.db, TaskDraft(**({"title": "Valid"} | values)))
        self.assertEqual(list_tasks(self.db), [])

    def test_database_rejects_contradictory_completion_state(self):
        saved = create_task(self.db, TaskDraft("Read notes"))
        with closing(sqlite3.connect(self.db)) as connection, connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE tasks SET status = 'completed' WHERE id = ?", (saved.id,)
                )
        self.assertEqual(list_tasks(self.db)[0].status, "pending")


if __name__ == "__main__":
    unittest.main()
