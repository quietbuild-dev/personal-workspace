"""Data migration, persistence, deletion and complete end-to-end replan flows."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

from workspace.models import TaskDraft
from workspace.overview import load_overview
from workspace.repository import (
    create_task,
    delete_task,
    initialize_database,
    list_tasks,
    load_availability,
    save_availability,
    update_task,
)

TODAY = date(2026, 11, 11)


class AvailabilityAndIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Path(self.directory.name) / "data" / "existing.db"
        initialize_database(self.db)

    def test_missing_availability_is_zero_and_saved_dates_persist(self):
        self.assertEqual(load_availability(self.db, TODAY, TODAY + timedelta(days=2)),
                         {TODAY: 0, TODAY + timedelta(days=1): 0,
                          TODAY + timedelta(days=2): 0})
        save_availability(self.db, {TODAY: 80, TODAY + timedelta(days=1): 0})
        initialize_database(self.db)
        self.assertEqual(load_availability(self.db, TODAY, TODAY + timedelta(days=1)),
                         {TODAY: 80, TODAY + timedelta(days=1): 0})

    def test_updates_one_date_without_overwriting_other_days(self):
        next_day = TODAY + timedelta(days=1)
        save_availability(self.db, {TODAY: 50, next_day: 100})
        save_availability(self.db, {TODAY: 25})
        self.assertEqual(load_availability(self.db, TODAY, next_day),
                         {TODAY: 25, next_day: 100})

    def test_invalid_availability_rejects_all_without_partial_writes(self):
        for invalid in (-1, 1441, True, 23.5, "50", None):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                save_availability(self.db, {TODAY: 80, TODAY + timedelta(days=1): invalid})
            self.assertEqual(load_availability(self.db, TODAY, TODAY), {TODAY: 0})
        with self.assertRaises(ValueError):
            save_availability(self.db, {"Wednesday": 10})
        with self.assertRaises(ValueError):
            load_availability(self.db, TODAY, TODAY - timedelta(days=1))

    def test_database_enforces_availability_bounds(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO daily_availability VALUES (?, ?)",
                                   (TODAY.isoformat(), -2))

    def test_previous_week_does_not_become_capacity_next_week(self):
        save_availability(self.db, {TODAY: 200})
        following = TODAY + timedelta(days=7)
        self.assertEqual(load_availability(self.db, following, following), {following: 0})

    def test_additive_migration_preserves_preexisting_tasks(self):
        legacy = Path(self.directory.name) / "legacy.db"
        with closing(sqlite3.connect(legacy)) as connection, connection:
            connection.execute("""CREATE TABLE tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
                category TEXT NOT NULL, deadline TEXT, priority INTEGER NOT NULL,
                estimate_minutes INTEGER NOT NULL, remaining_minutes INTEGER NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL, completed_at TEXT)""")
            connection.execute("""INSERT INTO tasks VALUES (
                42, 'Original task', 'University', '2026-11-13', 3, 90, 90,
                'pending', '2026-11-10T10:00:00+00:00', NULL)""")
        initialize_database(legacy)
        self.assertEqual([(t.id, t.title) for t in list_tasks(legacy)],
                         [(42, "Original task")])
        save_availability(legacy, {TODAY: 60})
        initialize_database(legacy)
        self.assertEqual(load_availability(legacy, TODAY, TODAY), {TODAY: 60})
        self.assertEqual(list_tasks(legacy)[0].id, 42)

    def test_delete_validation_unknown_id_and_unchanged_other_records(self):
        first = create_task(self.db, TaskDraft("First"))
        second = create_task(self.db, TaskDraft("Second"))
        for bad in (0, -1, True, 1.5, "1", 2**63):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                delete_task(self.db, bad)
        with self.assertRaisesRegex(ValueError, "no longer exists"):
            delete_task(self.db, 999)
        delete_task(self.db, first.id)
        self.assertEqual(list_tasks(self.db), [second])
        with self.assertRaises(ValueError):
            delete_task(self.db, first.id)

    def test_create_plan_complete_reopen_replan_delete(self):
        draft = TaskDraft("Project report", "University", TODAY, 3, 90)
        task = create_task(self.db, draft)
        other = create_task(self.db, TaskDraft("Backlog", estimate_minutes=60))
        save_availability(self.db, {TODAY: 90})
        before = load_overview(self.db, TODAY)
        self.assertEqual(before.metrics.open_tasks, 2)
        self.assertEqual([(a.task_id, a.minutes) for a in before.plan.allocations],
                         [(task.id, 90)])
        self.assertEqual(before.metrics.remaining_minutes, 150)

        completed = update_task(self.db, task.id, draft, 0)
        after = load_overview(self.db, TODAY)
        self.assertEqual(completed.status, "completed")
        self.assertEqual([(a.task_id, a.minutes) for a in after.plan.allocations],
                         [(other.id, 60)])
        self.assertEqual(after.metrics.remaining_minutes, 60)
        self.assertEqual(after.metrics.completion_percentage, 100)

        update_task(self.db, task.id, draft, 40)
        reopened = load_overview(self.db, TODAY)
        self.assertEqual(reopened.metrics.remaining_minutes, 100)
        self.assertEqual([(a.task_id, a.minutes) for a in reopened.plan.allocations],
                         [(task.id, 40), (other.id, 50)])

        delete_task(self.db, task.id)
        final = load_overview(self.db, TODAY)
        self.assertEqual([t.id for t in final.tasks], [other.id])
        self.assertEqual(final.metrics.remaining_minutes, 60)
        self.assertEqual(final.metrics.open_tasks, 1)
        self.assertIsNone(final.metrics.completion_percentage)
        self.assertEqual(sum(a.minutes for a in final.plan.allocations), 60)
        self.assertEqual(final.availability[TODAY], 90)


if __name__ == "__main__":
    unittest.main()
