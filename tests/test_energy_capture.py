"""Safe, temporary focus-mode plans."""

from datetime import date, datetime

import pytest

from workspace.advanced_planner import Slot, validate_revision
from workspace.advanced_repository import (
    StaleProposalError,
    accept_revision,
    add_fixed_event,
    add_window,
    load_snapshot,
    plan_undo_status,
    undo_last_plan,
)
from workspace.energy_today import MODE_MINUTES, divide_slot, energy_proposal, focus_suggestions
from workspace.models import TaskDraft
from workspace.optimizer import proposal_from_slots
from workspace.quick_tasks import create_quick_task

NOW = datetime(2026, 11, 25, 9, 0)
WED = date(2026, 11, 25)
FRI = date(2026, 11, 27)


def prepared_db(tmp_path):
    db = tmp_path / "energy.db"
    task_id = create_quick_task(
        db, TaskDraft("Algorithms exam", "University", FRI, 3, 120)
    )
    add_window(db, WED, 10 * 60, 14 * 60)
    return db, task_id


def book_energy(db, slots=None):
    snapshot = load_snapshot(db)
    step_id = snapshot.steps[0].id
    slots = slots or (Slot(step_id, WED, 600, 720),)
    accept_revision(db, proposal_from_slots(snapshot, NOW, slots), NOW)


def test_slot_division_preserves_coverage_without_overlaps():
    original = Slot(9, WED, 600, 721)
    for cap in MODE_MINUTES.values():
        segments = divide_slot(original, cap)
        assert sum(s.minutes for s in segments) == original.minutes
        assert all(20 <= s.minutes <= cap for s in segments)
        assert segments[0].start == original.start
        assert segments[-1].end == original.end
        assert all(a.end == b.start for a, b in zip(segments, segments[1:]))


def test_low_energy_preview_does_not_write_and_is_valid(tmp_path):
    db, _ = prepared_db(tmp_path)
    book_energy(db)
    saved = load_snapshot(db)
    proposal = energy_proposal(saved, NOW, "Low energy", WED)
    assert load_snapshot(db) == saved
    assert proposal.shortfalls == ()
    assert sum(slot.minutes for slot in proposal.slots) == 120
    assert len([slot for slot in proposal.slots if slot.day == WED]) == 5
    validate_revision(saved, proposal, NOW)


def test_accept_and_undo_restore_original_accepted_study_blocks(tmp_path):
    db, _ = prepared_db(tmp_path)
    book_energy(db)
    original = energy_proposal(load_snapshot(db), NOW, "Deep focus", WED)
    accept_revision(db, original, NOW)
    before = load_snapshot(db)
    assert plan_undo_status(db) == "ready"
    low = energy_proposal(before, NOW, "Low energy", WED)
    assert len(low.slots) > len(original.slots)
    accept_revision(db, low, NOW)
    assert plan_undo_status(db) == "ready"
    assert len(load_snapshot(db).sessions) == len(low.slots)
    undo_last_plan(db, NOW)
    assert load_snapshot(db).sessions == before.sessions


def test_preview_rechecks_changed_commitments_before_save(tmp_path):
    db, _ = prepared_db(tmp_path)
    book_energy(db)
    preview = energy_proposal(load_snapshot(db), NOW, "Low energy", WED)
    add_fixed_event(db, "Surprise lecture", WED, 11 * 60, 12 * 60, "Lecture")
    prior = load_snapshot(db)
    with pytest.raises(StaleProposalError):
        accept_revision(db, preview, NOW)
    assert load_snapshot(db) == prior


def test_focus_modes_reject_out_of_week_dates_and_bad_names(tmp_path):
    db, _ = prepared_db(tmp_path)
    snapshot = load_snapshot(db)
    with pytest.raises(ValueError, match="current planning week"):
        energy_proposal(snapshot, NOW, "Low energy", date(2026, 12, 1))
    with pytest.raises(ValueError, match="Choose Low energy"):
        energy_proposal(snapshot, NOW, "Unknown", WED)


def test_commitment_gaps_are_respected(tmp_path):
    db, _ = prepared_db(tmp_path)
    book_energy(db, (Slot(load_snapshot(db).steps[0].id, WED, 600, 660),
                     Slot(load_snapshot(db).steps[0].id, WED, 720, 780)))
    add_fixed_event(db, "Lecture", WED, 11 * 60, 12 * 60, "Lecture")
    snap = load_snapshot(db)
    proposal = energy_proposal(snap, NOW, "Low energy", WED)
    validate_revision(snap, proposal, NOW)
    assert all(s.end <= 660 or s.start >= 720 for s in proposal.slots)
    assert proposal.planned_minutes == 120


def test_priority_and_deadline_come_before_soft_focus_order(tmp_path):
    db, _ = prepared_db(tmp_path)
    create_quick_task(db, TaskDraft("Short exercise", "University", WED, 1, 20))
    book_energy(db)
    snap = load_snapshot(db)
    low = energy_proposal(snap, NOW, "Low energy", WED)
    titles = [step.task_title for step in focus_suggestions(snap, low, "Low energy", WED)]
    assert titles == ["Algorithms exam"], "Unbooked tasks cannot be added by Energy Today."


def test_energy_refuses_to_auto_schedule_unbooked_tasks(tmp_path):
    db, _ = prepared_db(tmp_path)
    with pytest.raises(ValueError, match="No booked study"):
        energy_proposal(load_snapshot(db), NOW, "Low energy", WED)


def test_energy_unchanged_other_days(tmp_path):
    db, _ = prepared_db(tmp_path)
    add_window(db, FRI, 600, 780)
    step = load_snapshot(db).steps[0].id
    book_energy(db, (Slot(step, WED, 600, 660), Slot(step, FRI, 660, 720)))
    snapshot = load_snapshot(db)
    proposal = energy_proposal(snapshot, NOW, "Low energy", WED)
    old_friday = {(s.step_id, s.day, s.start, s.end) for s in snapshot.sessions if s.day == FRI}
    new_friday = {(s.step_id, s.day, s.start, s.end) for s in proposal.slots if s.day == FRI}
    assert old_friday == new_friday
    assert sum(s.minutes for s in proposal.slots) == 120
    assert all(s.minutes >= 20 for s in proposal.slots)


def test_demo_uses_isolated_file_and_protects_existing(tmp_path):
    from scripts.create_energy_capture_demo import create_demo

    path = tmp_path / "standalone-demo.db"
    day = create_demo(path, NOW)
    assert day == date(2026, 11, 26)
    snapshot = load_snapshot(path)
    assert len(snapshot.sessions) == 1
    assert snapshot.sessions[0].end - snapshot.sessions[0].start == 120
    with pytest.raises(ValueError, match="already exists"):
        create_demo(path, NOW)
