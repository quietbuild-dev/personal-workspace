"""Regression tests for quick tasks and approval-based scheduling."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path

from workspace.advanced_planner import make_revision
from workspace.advanced_repository import (
    StaleProposalError,
    accept_revision,
    add_step,
    add_window,
    load_snapshot,
    set_checklist_done,
)
from workspace.models import TaskDraft
from workspace.quick_tasks import (
    add_detailed_timed_step,
    create_quick_task,
    edit_quick_task,
    enable_quick_planning,
    linked_step_ids,
    toggle_quick_task,
)
from workspace.repository import create_task, delete_task, list_tasks
from workspace.simple_planning import proposal_notice

TODAY = date(2026, 11, 12)
NOW = datetime(2026, 11, 12, 8, 0)


class QuickTasksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "workspace.db"

    def test_atomic_create_creates_only_one_schedulable_step(self):
        task_id = create_quick_task(
            self.db, TaskDraft("Study economics", "Economics", TODAY, 3, 90)
        )
        tasks = list_tasks(self.db)
        snapshot = load_snapshot(self.db)
        self.assertEqual([item.id for item in tasks], [task_id])
        self.assertEqual(len(snapshot.steps), 1)
        self.assertEqual(snapshot.steps[0].task_id, task_id)
        self.assertEqual(snapshot.steps[0].kind, "timed")
        self.assertEqual(snapshot.steps[0].remaining_minutes, 90)
        self.assertEqual(linked_step_ids(self.db), {task_id: snapshot.steps[0].id})
        self.assertFalse(snapshot.sessions)

    def test_bad_quick_task_does_not_leave_a_partial_parent(self):
        with self.assertRaises(ValueError):
            create_quick_task(self.db, TaskDraft("   "))
        # Validation happens before creating tables, but a fresh initialization is safe.
        self.assertEqual(linked_step_ids(self.db), {})
        self.assertEqual(list_tasks(self.db), [])

    def test_proposal_appears_automatically_without_mutation_and_can_be_accepted(self):
        task_id = create_quick_task(
            self.db, TaskDraft("Read notes", deadline=TODAY, estimate_minutes=90)
        )
        add_window(self.db, TODAY, 9 * 60, 11 * 60)
        before = load_snapshot(self.db)
        notice = proposal_notice(before, NOW)
        self.assertTrue(notice.changed)
        self.assertEqual(notice.new_sessions, 1)
        self.assertEqual(notice.revision.planned_minutes, 90)
        self.assertEqual(load_snapshot(self.db).fingerprint, before.fingerprint)
        self.assertEqual(load_snapshot(self.db).sessions, ())
        self.assertEqual(accept_revision(self.db, notice.revision, NOW), 1)
        after = load_snapshot(self.db)
        self.assertEqual(len(after.sessions), 1)
        self.assertEqual(after.sessions[0].step_id, linked_step_ids(self.db)[task_id])
        self.assertFalse(proposal_notice(after, NOW).changed)

    def test_completed_quick_task_removes_future_work_only_after_approval(self):
        task_id = create_quick_task(
            self.db, TaskDraft("Assignment", deadline=TODAY, estimate_minutes=60)
        )
        add_window(self.db, TODAY, 9 * 60, 11 * 60)
        accept_revision(self.db, make_revision(load_snapshot(self.db), NOW), NOW)
        saved = load_snapshot(self.db).sessions[0]
        toggle_quick_task(self.db, task_id, True)
        completed = list_tasks(self.db)[0]
        self.assertEqual(completed.status, "completed")
        self.assertEqual(load_snapshot(self.db).steps[0].remaining_minutes, 0)
        # The accepted schedule is not silently replaced by a task status action.
        self.assertEqual(load_snapshot(self.db).sessions[0], saved)
        proposed = proposal_notice(load_snapshot(self.db), NOW)
        self.assertEqual(proposed.removed_sessions, 1)
        accept_revision(self.db, proposed.revision, NOW)
        self.assertFalse(load_snapshot(self.db).sessions)
        toggle_quick_task(self.db, task_id, False)
        self.assertEqual(list_tasks(self.db)[0].remaining_minutes, 60)
        self.assertEqual(load_snapshot(self.db).steps[0].remaining_minutes, 60)

    def test_checklists_cannot_be_silently_marked_done(self):
        task_id = create_quick_task(self.db, TaskDraft("Read paper"))
        checklist = add_step(self.db, task_id, "Download article", "checklist")
        with self.assertRaisesRegex(ValueError, "checklist"):
            toggle_quick_task(self.db, task_id, True)
        self.assertEqual(list_tasks(self.db)[0].status, "pending")
        self.assertEqual(load_snapshot(self.db).steps[0].remaining_minutes, 60)
        set_checklist_done(self.db, checklist, True)
        toggle_quick_task(self.db, task_id, True)
        self.assertEqual(list_tasks(self.db)[0].status, "completed")

    def test_edit_syncs_auto_timed_work_and_validation_rolls_back(self):
        task_id = create_quick_task(self.db, TaskDraft("Draft report", estimate_minutes=80))
        with self.assertRaisesRegex(ValueError, "Remaining"):
            edit_quick_task(self.db, task_id, TaskDraft("New title", estimate_minutes=30), 40)
        self.assertEqual(list_tasks(self.db)[0].title, "Draft report")
        self.assertEqual(load_snapshot(self.db).steps[0].estimate_minutes, 80)
        edit_quick_task(self.db, task_id, TaskDraft("New title", "Work", TODAY, 3, 45), 25)
        self.assertEqual(list_tasks(self.db)[0].title, "New title")
        self.assertEqual(load_snapshot(self.db).steps[0].estimate_minutes, 45)
        self.assertEqual(load_snapshot(self.db).steps[0].remaining_minutes, 25)

    def test_existing_tasks_can_opt_into_calendar_once(self):
        # No existing tasks or data are modified by the quick-task migration.
        create_quick_task(self.db, TaskDraft("New"))
        old = create_task(self.db, TaskDraft("Legacy", estimate_minutes=45))
        self.assertTrue(enable_quick_planning(self.db, old.id))
        self.assertFalse(enable_quick_planning(self.db, old.id))
        self.assertEqual(len(load_snapshot(self.db).steps), 2)

    def test_existing_custom_timed_steps_not_duplicated(self):
        create_quick_task(self.db, TaskDraft("New"))
        old = create_task(self.db, TaskDraft("Legacy"))
        add_step(self.db, old.id, "Already scheduled", "timed", 30)
        with self.assertRaisesRegex(ValueError, "already"):
            enable_quick_planning(self.db, old.id)
        self.assertEqual(len(load_snapshot(self.db).steps), 2)

    def test_custom_study_steps_cannot_be_completed_indirectly(self):
        task_id = create_quick_task(self.db, TaskDraft("Large exam"))
        add_step(self.db, task_id, "Extra practice", "timed", 20)
        with self.assertRaisesRegex(ValueError, "other"):
            toggle_quick_task(self.db, task_id, True)
        self.assertEqual([s.remaining_minutes for s in load_snapshot(self.db).steps], [60, 20])

    def test_delete_cascades_both_auto_step_and_link(self):
        task_id = create_quick_task(self.db, TaskDraft("Temporary"))
        delete_task(self.db, task_id)
        self.assertEqual(linked_step_ids(self.db), {})
        self.assertFalse(load_snapshot(self.db).steps)

    def test_stale_proposal_rejected_after_quick_task_change(self):
        create_quick_task(self.db, TaskDraft("First"))
        add_window(self.db, TODAY, 9 * 60, 11 * 60)
        proposal = make_revision(load_snapshot(self.db), NOW)
        create_quick_task(self.db, TaskDraft("Second"))
        with self.assertRaises(StaleProposalError):
            accept_revision(self.db, proposal, NOW)
        self.assertEqual(load_snapshot(self.db).sessions, ())

    def test_quick_task_link_table_has_foreign_keys(self):
        create_quick_task(self.db, TaskDraft("Demo"))
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO quick_task_links(task_id,step_id) VALUES (?,?)", (999, 999)
                )

    def test_split_focus_step_conserves_total_minutes_and_previews_changes(self):
        task_id = create_quick_task(self.db, TaskDraft("Exam", estimate_minutes=120))
        add_window(self.db, TODAY, 9 * 60, 12 * 60)
        before = load_snapshot(self.db)
        new_id = add_detailed_timed_step(self.db, task_id, "Practice questions", 45)
        after = load_snapshot(self.db)
        self.assertEqual(
            [(step.title, step.estimate_minutes, step.remaining_minutes) for step in after.steps],
            [("Focus time", 75, 75), ("Practice questions", 45, 45)],
        )
        self.assertEqual(sum(s.remaining_minutes for s in after.steps), 120)
        self.assertEqual(new_id, after.steps[1].id)
        self.assertNotEqual(before.fingerprint, after.fingerprint)
        self.assertEqual(proposal_notice(after, NOW).revision.planned_minutes, 120)
        # Editing the parent budget must subtract independently detailed steps.
        edit_quick_task(self.db, task_id, TaskDraft("Exam", estimate_minutes=150), 100)
        after_edit = load_snapshot(self.db)
        self.assertEqual(
            [(s.estimate_minutes, s.remaining_minutes) for s in after_edit.steps],
            [(105, 55), (45, 45)],
        )

    def test_cannot_split_more_than_available_focus_time(self):
        task_id = create_quick_task(self.db, TaskDraft("Exam", estimate_minutes=60))
        with self.assertRaisesRegex(ValueError, "fit within remaining"):
            add_detailed_timed_step(self.db, task_id, "Too much", 90)
        self.assertEqual(len(load_snapshot(self.db).steps), 1)

    def test_future_task_remains_outside_week_without_false_infeasibility(self):
        create_quick_task(self.db, TaskDraft("Long-term", deadline=TODAY + timedelta(days=30)))
        proposal = proposal_notice(load_snapshot(self.db), NOW)
        self.assertEqual(proposal.shortfall_minutes, 0)
        self.assertFalse(proposal.changed)
        self.assertEqual(proposal.revision.shortfalls[0].reason, "outside_week")


if __name__ == "__main__":
    unittest.main()
