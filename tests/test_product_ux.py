"""Release-level UX data and scheduling tests, without Streamlit/browser dependencies."""

import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from workspace.advanced_planner import Slot, effective_windows, make_revision, validate_revision
from workspace.advanced_repository import (
    StaleProposalError,
    accept_revision,
    add_fixed_event,
    list_task_categories,
    load_snapshot,
    save_week_preferences,
    update_fixed_event,
)
from workspace.manual_planning import move_proposed_block
from workspace.models import TaskDraft
from workspace.quick_tasks import create_quick_task, edit_quick_task
from workspace.repository import delete_task, initialize_database, list_tasks

TUESDAY = date(2026, 11, 17)
WEDNESDAY = TUESDAY + timedelta(days=1)
NOW = datetime(2026, 11, 17, 8, 0)

CALENDAR = Path(__file__).resolve().parents[1] / "workspace/views/weekly_calendar.py"
SPEC = importlib.util.spec_from_file_location("ux_calendar_renderer", CALENDAR)
RENDERER = importlib.util.module_from_spec(SPEC)
with patch.dict(sys.modules, {"streamlit": MagicMock()}):
    SPEC.loader.exec_module(RENDERER)


class ProductUXTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db = Path(folder.name) / "workspace.db"
        initialize_database(self.db)

    def test_custom_categories_survive_task_deletion(self):
        task_id = create_quick_task(self.db, TaskDraft("Organize meeting", "Student association"))
        self.assertIn("Student association", list_task_categories(self.db))
        delete_task(self.db, task_id)
        self.assertIn("Student association", list_task_categories(self.db))
        self.assertIn("University", list_task_categories(self.db))
        self.assertIn("Social", list_task_categories(self.db))
        self.assertEqual(list_tasks(self.db), [])

    def test_new_due_time_requires_a_due_date(self):
        with self.assertRaisesRegex(ValueError, "deadline time"):
            create_quick_task(self.db, TaskDraft("No date"), due_minute=780)
        self.assertEqual(list_tasks(self.db), [])

    def test_due_time_limits_planning_and_is_backwards_compatible(self):
        create_quick_task(
            self.db,
            TaskDraft("Submit report", "University", TUESDAY, 3, 120),
            due_minute=10 * 60 + 30,
        )
        save_week_preferences(self.db, (TUESDAY,), 180, 9 * 60, 12 * 60)
        snapshot = load_snapshot(self.db)
        step = snapshot.steps[0]
        self.assertEqual(step.deadline_minute, 10 * 60 + 30)
        self.assertEqual(snapshot.preferences[0].start, 540)
        proposal = make_revision(snapshot, NOW)
        self.assertEqual([(slot.start, slot.end) for slot in proposal.slots], [(540, 630)])
        self.assertEqual(proposal.shortfalls[0].minutes, 30)
        validate_revision(snapshot, proposal, NOW)
        forged = replace(
            proposal,
            slots=(Slot(step.id, TUESDAY, 600, 720),),
            shortfalls=(),
        )
        with self.assertRaisesRegex(ValueError, "deadline time"):
            validate_revision(snapshot, forged, NOW)

    def test_edit_due_time_then_clear_date(self):
        task_id = create_quick_task(
            self.db, TaskDraft("Prepare notes", deadline=TUESDAY), due_minute=15 * 60
        )
        edit_quick_task(
            self.db,
            task_id,
            TaskDraft("Prepare notes", deadline=WEDNESDAY),
            60,
            due_minute=11 * 60,
        )
        self.assertEqual(load_snapshot(self.db).steps[0].deadline_minute, 660)
        edit_quick_task(self.db, task_id, TaskDraft("Prepare notes"), 60, due_minute=None)
        self.assertIsNone(load_snapshot(self.db).steps[0].deadline_minute)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM task_deadline_times").fetchone()[0], 0
            )

    def test_event_type_and_edit_persist_and_invalidate_preview(self):
        create_quick_task(self.db, TaskDraft("Read notes", deadline=TUESDAY))
        save_week_preferences(self.db, (TUESDAY,), 120, 9 * 60, 12 * 60)
        event_id = add_fixed_event(self.db, "Statistics class", TUESDAY, 9 * 60, 10 * 60, "Lecture")
        before = load_snapshot(self.db)
        self.assertEqual(before.events[0].kind, "Lecture")
        proposal = make_revision(before, NOW)
        update_fixed_event(self.db, event_id, "Gym", TUESDAY, 9 * 60, 10 * 60, "Exercise")
        current = load_snapshot(self.db)
        self.assertEqual((current.events[0].title, current.events[0].kind), ("Gym", "Exercise"))
        with self.assertRaises(StaleProposalError):
            accept_revision(self.db, proposal, NOW)
        self.assertFalse(current.sessions)

    def test_date_specific_preferences_and_events_produce_gaps(self):
        create_quick_task(self.db, TaskDraft("Exam", deadline=WEDNESDAY, estimate_minutes=120))
        save_week_preferences(self.db, (TUESDAY, WEDNESDAY), 60, 9 * 60, 12 * 60)
        add_fixed_event(self.db, "Lecture", TUESDAY, 9 * 60, 10 * 60, "Lecture")
        proposal = make_revision(load_snapshot(self.db), NOW)
        self.assertEqual(
            [(slot.day, slot.start, slot.end) for slot in proposal.slots],
            [(TUESDAY, 600, 660), (WEDNESDAY, 540, 600)],
        )
        self.assertEqual(proposal.shortfalls, ())
        # Only the selected dates have automatic windows; the following day doesn't repeat.
        snapshot = load_snapshot(self.db)
        self.assertFalse(
            any(w.day == WEDNESDAY + timedelta(days=1) for w in effective_windows(snapshot))
        )

    def test_rescheduling_changes_only_one_session_and_never_previews_to_db(self):
        create_quick_task(self.db, TaskDraft("Task A", deadline=WEDNESDAY))
        create_quick_task(self.db, TaskDraft("Task B", deadline=WEDNESDAY))
        save_week_preferences(self.db, (TUESDAY,), 180, 9 * 60, 14 * 60)
        accept_revision(self.db, make_revision(load_snapshot(self.db), NOW), NOW)
        before = load_snapshot(self.db)
        self.assertEqual(len(before.sessions), 2)
        first, second = sorted(before.sessions, key=lambda s: s.start)
        revision = make_revision(before, NOW, reschedule_session_id=first.id)
        self.assertEqual(revision.unchanged, 1)
        self.assertEqual(revision.added_or_changed, 1)
        self.assertFalse(
            any(
                slot.start == first.start and slot.step_id == first.step_id
                for slot in revision.slots
            )
        )
        self.assertEqual(load_snapshot(self.db).sessions, before.sessions)
        accept_revision(self.db, revision, NOW)
        after = load_snapshot(self.db)
        current = [s for s in after.sessions if s.status == "planned"]
        self.assertEqual(len(current), 2)
        self.assertIn(second.id, {s.id for s in current})
        self.assertNotIn(first.id, {s.id for s in current})

    def test_calendar_html_has_clickable_safe_blocks_and_actual_assignment(self):
        task_id = create_quick_task(self.db, TaskDraft("Economics assignment", deadline=TUESDAY))
        save_week_preferences(self.db, (TUESDAY,), 60, 9 * 60, 12 * 60)
        event_id = add_fixed_event(
            self.db,
            '<img src=x onerror="alert(1)">',
            TUESDAY,
            11 * 60,
            12 * 60,
            "Social",
        )
        accept_revision(self.db, make_revision(load_snapshot(self.db), NOW), NOW)
        snap = load_snapshot(self.db)
        session = snap.sessions[0]
        slot = Slot(session.step_id, session.day, session.start, session.end)
        html = RENDERER.calendar_html(
            snap.events,
            (slot,),
            {s.id: s for s in snap.steps},
            TUESDAY,
            TUESDAY,
            session_links={(slot.step_id, slot.day, slot.start, slot.end): session.id},
        )
        self.assertIn(f'href="?session={session.id}&date={TUESDAY.isoformat()}"', html)
        self.assertIn(f'href="?event={event_id}&date={TUESDAY.isoformat()}"', html)
        self.assertIn("Economics assignment", html)
        self.assertNotIn("Focus time</div>", html)
        self.assertIn("wp-social", html)
        self.assertIn("&lt;img", html)
        self.assertNotIn('<img src=x onerror="alert(1)">', html)
        self.assertEqual(list_tasks(self.db)[0].id, task_id)

    def test_manual_suggestion_can_change_time_without_saving(self):
        create_quick_task(self.db, TaskDraft("Practice", deadline=WEDNESDAY))
        save_week_preferences(self.db, (TUESDAY,), 120, 9 * 60, 14 * 60)
        before = load_snapshot(self.db)
        proposal = make_revision(before, NOW)
        adjusted = move_proposed_block(before, proposal, 0, TUESDAY, 11 * 60, NOW)
        self.assertEqual((adjusted.slots[0].start, adjusted.slots[0].end), (660, 720))
        self.assertFalse(load_snapshot(self.db).sessions)
        accept_revision(self.db, adjusted, NOW)
        self.assertEqual(load_snapshot(self.db).sessions[0].start, 660)

    def test_manual_suggestion_rejects_conflict_and_keeps_original(self):
        create_quick_task(self.db, TaskDraft("Read", deadline=WEDNESDAY))
        save_week_preferences(self.db, (TUESDAY,), 120, 9 * 60, 14 * 60)
        add_fixed_event(self.db, "Lecture", TUESDAY, 11 * 60, 12 * 60, "Lecture")
        before = load_snapshot(self.db)
        proposal = make_revision(before, NOW)
        with self.assertRaisesRegex(ValueError, "conflict"):
            move_proposed_block(before, proposal, 0, TUESDAY, 11 * 60, NOW)
        self.assertEqual(load_snapshot(self.db).fingerprint, before.fingerprint)
        self.assertFalse(load_snapshot(self.db).sessions)

    def test_migration_preserves_old_task_and_missing_times(self):
        from workspace.repository import create_task

        old = create_task(self.db, TaskDraft("Original", "University"))
        snapshot = load_snapshot(self.db)
        self.assertIsNone(snapshot.steps[0].deadline_minute if snapshot.steps else None)
        self.assertEqual(list_tasks(self.db)[0].id, old.id)
        self.assertIn("University", list_task_categories(self.db))


if __name__ == "__main__":
    unittest.main()
