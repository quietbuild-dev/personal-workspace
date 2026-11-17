"""First advanced milestone: pure scheduling, persistence and safety invariants."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

from workspace.advanced_planner import (
    Slot,
    accepted_conflicts,
    make_revision,
    validate_revision,
)
from workspace.advanced_repository import (
    StaleProposalError,
    accept_revision,
    add_fixed_event,
    add_step,
    add_window,
    initialize_advanced,
    load_snapshot,
    record_session,
    set_checklist_done,
    set_timed_remaining,
)
from workspace.models import TaskDraft
from workspace.repository import (
    create_task,
    delete_task,
    initialize_database,
    list_tasks,
    update_task,
)

TUESDAY = date(2026, 11, 17)
NOW = datetime(2026, 11, 17, 8, 0)
WEDNESDAY = date(2026, 11, 18)
FRIDAY = date(2026, 11, 20)


class AdvancedPlannerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "tasks.db"
        initialize_database(self.db)
        self.task = create_task(self.db, TaskDraft("Economics exam", "University", FRIDAY, 3, 180))
        initialize_advanced(self.db)
        self.step = add_step(self.db, self.task.id, "Revision", "timed", 120)
        self.checklist = add_step(self.db, self.task.id, "Download past papers", "checklist")

    def current(self, *, preserve=True, now=NOW):
        snap = load_snapshot(self.db)
        return snap, make_revision(snap, now, preserve_existing=preserve)

    def test_additive_migration_does_not_erase_tasks(self):
        initialize_advanced(self.db)
        initialize_advanced(self.db)
        self.assertEqual(list_tasks(self.db)[0].id, self.task.id)
        self.assertEqual(len(load_snapshot(self.db).steps), 2)

    def test_lecture_splits_sessions_without_overlap(self):
        add_window(self.db, TUESDAY, 13 * 60, 17 * 60)
        add_fixed_event(self.db, "Lecture", TUESDAY, 14 * 60, 15 * 60)
        _, proposal = self.current()
        self.assertEqual([(s.start, s.end) for s in proposal.slots], [(780, 840), (900, 960)])
        self.assertEqual(proposal.shortfalls, ())
        self.assertEqual(proposal.planned_minutes, 120)

    def test_preview_and_rejection_never_change_database(self):
        add_window(self.db, TUESDAY, 9 * 60, 11 * 60)
        snap, proposal = self.current()
        self.assertEqual(snap.sessions, ())
        self.assertEqual(load_snapshot(self.db).sessions, ())  # User rejects proposal.
        self.assertEqual(accept_revision(self.db, proposal, NOW), 1)
        self.assertEqual(len(load_snapshot(self.db).sessions), 1)

    def test_missed_session_replans_only_missing_work(self):
        add_window(self.db, TUESDAY, 13 * 60, 14 * 60)
        add_window(self.db, WEDNESDAY, 10 * 60, 11 * 60)
        _, proposal = self.current()
        self.assertEqual(len(proposal.slots), 2)
        accept_revision(self.db, proposal, NOW)
        before = load_snapshot(self.db)
        tue = next(s for s in before.sessions if s.day == TUESDAY)
        wed = next(s for s in before.sessions if s.day == WEDNESDAY)
        record_session(self.db, tue.id, "missed", now=datetime(2026, 11, 17, 14, 0))
        add_window(self.db, WEDNESDAY, 15 * 60, 16 * 60)
        snap, revision = self.current(now=datetime(2026, 11, 18, 8, 0))
        self.assertEqual(revision.unchanged, 1)
        self.assertIn(Slot(self.step, WEDNESDAY, 600, 660), revision.slots)
        self.assertIn(Slot(self.step, WEDNESDAY, 900, 960), revision.slots)
        self.assertEqual(next(s for s in snap.sessions if s.id == tue.id).status, "missed")
        self.assertEqual(revision.shortfalls, ())
        accept_revision(self.db, revision, datetime(2026, 11, 18, 8, 0))
        current_planned = [s for s in load_snapshot(self.db).sessions if s.status == "planned"]
        self.assertEqual(len(current_planned), 2)
        self.assertEqual(
            {(s.day, s.start, s.end) for s in current_planned},
            {(WEDNESDAY, 600, 660), (WEDNESDAY, 900, 960)},
        )
        self.assertEqual(load_snapshot(self.db).steps[0].remaining_minutes, 120)
        self.assertEqual(wed.status, "planned")  # Historical in-memory snapshot unchanged.

    def test_completed_session_reduces_work_and_replans_remainder(self):
        add_window(self.db, TUESDAY, 9 * 60, 10 * 60)
        add_window(self.db, WEDNESDAY, 9 * 60, 10 * 60)
        _, proposal = self.current()
        accept_revision(self.db, proposal, NOW)
        session = next(s for s in load_snapshot(self.db).sessions if s.day == TUESDAY)
        record_session(self.db, session.id, "done", 30, now=datetime(2026, 11, 17, 10, 5))
        snapshot, revision = self.current()
        self.assertEqual(next(s for s in snapshot.steps if s.id == self.step).remaining_minutes, 90)
        self.assertEqual(revision.unchanged, 1)
        self.assertEqual(sum(s.minutes for s in revision.slots), 90)
        self.assertEqual(revision.shortfalls, ())
        with self.assertRaises(ValueError):
            # Cannot double-log work.
            record_session(self.db, session.id, "done", 10, now=datetime(2026, 11, 17, 10, 6))

    def test_stale_proposal_cannot_overwrite_new_lecture(self):
        add_window(self.db, TUESDAY, 13 * 60, 16 * 60)
        _, proposal = self.current()
        add_fixed_event(self.db, "New lecture", TUESDAY, 13 * 60, 14 * 60)
        with self.assertRaises(StaleProposalError):
            accept_revision(self.db, proposal, NOW)
        self.assertEqual(load_snapshot(self.db).sessions, ())

    def test_changed_task_priority_invalidates_preview(self):
        add_window(self.db, TUESDAY, 9 * 60, 12 * 60)
        _, proposal = self.current()
        update_task(
            self.db, self.task.id, TaskDraft("Economics exam", "University", FRIDAY, 2, 180), 180
        )
        with self.assertRaises(StaleProposalError):
            accept_revision(self.db, proposal, NOW)

    def test_acceptance_refuses_overlap_even_when_tampered(self):
        add_window(self.db, TUESDAY, 13 * 60, 16 * 60)
        add_fixed_event(self.db, "Class", TUESDAY, 14 * 60, 15 * 60)
        snapshot, proposal = self.current()
        fake = replace(proposal, slots=(Slot(self.step, TUESDAY, 840, 960),))
        with self.assertRaisesRegex(ValueError, "conflict"):
            validate_revision(snapshot, fake, NOW)
        self.assertEqual(load_snapshot(self.db).sessions, ())

    def test_acceptance_refuses_allocation_over_remaining(self):
        add_window(self.db, TUESDAY, 10 * 60, 14 * 60)
        snapshot, proposal = self.current()
        fake = replace(proposal, slots=(Slot(self.step, TUESDAY, 600, 780),))
        with self.assertRaises(ValueError):
            validate_revision(snapshot, fake, NOW)

    def test_shortfalls_distinguish_overdue_this_week_and_next_week(self):
        due_now = add_step(self.db, self.task.id, "Practice", "timed", 30)
        create = create_task(self.db, TaskDraft("Overdue", "Personal", date(2026, 11, 16)))
        overdue = add_step(self.db, create.id, "Overdue work", "timed", 25)
        later = create_task(self.db, TaskDraft("Future project", "Personal", date(2026, 12, 1)))
        future = add_step(self.db, later.id, "Future work", "timed", 40)
        snapshot, proposal = self.current()
        by_id = {item.step_id: (item.minutes, item.reason) for item in proposal.shortfalls}
        self.assertEqual(by_id[overdue], (25, "overdue"))
        self.assertEqual(by_id[future], (40, "outside_week"))
        self.assertEqual(by_id[due_now], (30, "could_not_fit"))
        self.assertEqual(by_id[self.step], (120, "could_not_fit"))
        self.assertEqual(sum(item.minutes for item in proposal.shortfalls), 215)

    def test_acceptance_keeps_ids_of_unchanged_sessions(self):
        add_window(self.db, TUESDAY, 9 * 60, 10 * 60)
        add_window(self.db, WEDNESDAY, 9 * 60, 10 * 60)
        _, proposal = self.current()
        accept_revision(self.db, proposal, NOW)
        before = load_snapshot(self.db)
        old_wed_id = next(s.id for s in before.sessions if s.day == WEDNESDAY)
        # Extra time is available but the previous two valid sessions remain.
        add_window(self.db, WEDNESDAY, 11 * 60, 12 * 60)
        _, update = self.current()
        self.assertEqual(update.unchanged, 2)
        accept_revision(self.db, update, NOW)
        after = load_snapshot(self.db)
        self.assertEqual(next(s.id for s in after.sessions if s.day == WEDNESDAY), old_wed_id)

    def test_replanning_baseline_moves_more_or_equal_sessions(self):
        add_window(self.db, TUESDAY, 9 * 60, 12 * 60)
        _, proposal = self.current()
        accept_revision(self.db, proposal, NOW)
        add_window(self.db, WEDNESDAY, 9 * 60, 12 * 60)
        _, stable = self.current(preserve=True)
        _, baseline = self.current(preserve=False)
        self.assertEqual(stable.unchanged, 1)
        self.assertLessEqual(stable.removed_or_changed, baseline.removed_or_changed)
        self.assertEqual(stable.planned_minutes, baseline.planned_minutes)

    def test_conflicts_report_new_fixed_event_without_modifying_schedule(self):
        add_window(self.db, TUESDAY, 9 * 60, 11 * 60)
        _, proposal = self.current()
        accept_revision(self.db, proposal, NOW)
        add_fixed_event(self.db, "New appointment", TUESDAY, 9 * 60, 10 * 60)
        snapshot = load_snapshot(self.db)
        self.assertTrue(accepted_conflicts(snapshot, NOW))
        self.assertEqual(len([s for s in snapshot.sessions if s.status == "planned"]), 1)
        revision = make_revision(snapshot, NOW)
        self.assertEqual(revision.planned_minutes, 60)  # Remaining valid gap.
        self.assertEqual(sum(s.minutes for s in revision.shortfalls), 60)

    def test_checklist_updates_and_delete_cascade(self):
        set_checklist_done(self.db, self.checklist, True)
        self.assertTrue(
            next(s for s in load_snapshot(self.db).steps if s.id == self.checklist).checked
        )
        delete_task(self.db, self.task.id)
        snapshot = load_snapshot(self.db)
        self.assertFalse(snapshot.steps)
        self.assertFalse(snapshot.sessions)
        with closing(sqlite3.connect(self.db)) as connection:
            count = connection.execute("SELECT count(*) FROM study_steps").fetchone()[0]
            self.assertEqual(count, 0)

    def test_repeated_work_updates_cannot_exceed_remaining(self):
        add_window(self.db, TUESDAY, 9 * 60, 12 * 60)
        _, proposal = self.current()
        accept_revision(self.db, proposal, NOW)
        session = load_snapshot(self.db).sessions[0]
        with self.assertRaises(ValueError):
            record_session(self.db, session.id, "done", 121, now=datetime(2026, 11, 17, 9, 1))
        self.assertEqual(load_snapshot(self.db).steps[0].remaining_minutes, 120)

    def test_timed_step_remaining_edits_require_new_preview(self):
        add_window(self.db, TUESDAY, 9 * 60, 11 * 60)
        _, proposal = self.current()
        set_timed_remaining(self.db, self.step, 45)
        with self.assertRaises(StaleProposalError):
            accept_revision(self.db, proposal, NOW)
        _, updated = self.current()
        self.assertEqual(updated.planned_minutes, 45)

    def test_week_boundary_and_past_time_are_respected(self):
        add_window(self.db, TUESDAY, 9 * 60, 12 * 60)
        add_window(self.db, date(2026, 11, 23), 9 * 60, 12 * 60)
        _, proposal = self.current(now=datetime(2026, 11, 17, 10, 30))
        self.assertEqual(proposal.slots[0].start, 630)
        self.assertEqual(proposal.slots[0].end, 720)
        self.assertTrue(proposal.shortfalls)
        self.assertEqual(proposal.shortfalls[0].minutes, 30)

    def test_deterministic_input_yields_identical_proposals(self):
        add_window(self.db, TUESDAY, 9 * 60, 12 * 60)
        snapshot = load_snapshot(self.db)
        self.assertEqual(make_revision(snapshot, NOW), make_revision(snapshot, NOW))


if __name__ == "__main__":
    unittest.main()
