"""Protection is preview-only until atomic approval and has safe Undo behavior."""

from datetime import date, datetime

import pytest

from workspace.advanced_planner import Slot
from workspace.advanced_repository import (
    StaleProposalError,
    accept_revision,
    add_fixed_event,
    add_step,
    add_window,
    initialize_advanced,
    load_snapshot,
    plan_undo_status,
)
from workspace.life_planning import (
    PROTECTED_TITLE,
    accept_time_protection,
    preview_time_protection,
    undo_last_plan_with_protection,
)
from workspace.models import TaskDraft
from workspace.optimizer import proposal_from_slots
from workspace.repository import create_task, initialize_database

NOW = datetime(2026, 11, 25, 9, 0)
THURSDAY = date(2026, 11, 26)
FRIDAY = date(2026, 11, 27)


def prepared_db(tmp_path):
    db = tmp_path / "time-protection.db"
    initialize_database(db)
    task = create_task(db, TaskDraft("Finish SWE", "University", FRIDAY, 3, 60))
    initialize_advanced(db)
    step = add_step(db, task.id, "Write report", "timed", 60)
    add_window(db, THURSDAY, 10 * 60, 12 * 60)
    add_window(db, FRIDAY, 17 * 60, 19 * 60)
    snapshot = load_snapshot(db)
    accepted = proposal_from_slots(snapshot, NOW, (Slot(step, FRIDAY, 17 * 60, 18 * 60),))
    accept_revision(db, accepted, NOW)
    return db, task, step


def test_preview_protects_friday_without_mutating_saved_data(tmp_path):
    db, task, step = prepared_db(tmp_path)
    before = load_snapshot(db)
    preview = preview_time_protection(
        before, NOW, FRIDAY, 17 * 60, 21 * 60, required_ids=frozenset({task.id})
    )
    after = load_snapshot(db)
    assert before == after
    assert preview.feasible, preview.explanation
    assert preview.changed > 0
    assert any(slot.day == THURSDAY for slot in preview.revision.slots)
    assert all(
        slot.day != FRIDAY or slot.end <= 17 * 60 or slot.start >= 21 * 60
        for slot in preview.revision.slots
    )


def test_accept_and_undo_restore_both_event_and_sessions(tmp_path):
    db, task, _ = prepared_db(tmp_path)
    before = load_snapshot(db)
    preview = preview_time_protection(
        before, NOW, FRIDAY, 17 * 60, 21 * 60, required_ids=frozenset({task.id})
    )
    assert preview.feasible
    event_id = accept_time_protection(db, preview, NOW)
    protected = load_snapshot(db)
    assert any(e.id == event_id and e.title == PROTECTED_TITLE for e in protected.events)
    assert plan_undo_status(db) == "ready"
    assert all(s.day == THURSDAY for s in protected.sessions if s.status == "planned")
    assert undo_last_plan_with_protection(db, NOW) == 1
    restored = load_snapshot(db)
    assert restored.events == before.events
    assert restored.sessions == before.sessions
    assert plan_undo_status(db) == "none"


def test_fixed_event_overlap_cannot_be_moved(tmp_path):
    db, _, _ = prepared_db(tmp_path)
    add_fixed_event(db, "Class", FRIDAY, 18 * 60, 19 * 60, "Lecture")
    with pytest.raises(ValueError, match="fixed commitment"):
        preview_time_protection(load_snapshot(db), NOW, FRIDAY, 17 * 60, 21 * 60)


def test_stale_preview_cannot_change_calendar(tmp_path):
    db, task, _ = prepared_db(tmp_path)
    preview = preview_time_protection(
        load_snapshot(db), NOW, FRIDAY, 17 * 60, 21 * 60,
        required_ids=frozenset({task.id}),
    )
    add_fixed_event(db, "Added lecture", THURSDAY, 11 * 60, 12 * 60, "Lecture")
    saved = load_snapshot(db)
    with pytest.raises(StaleProposalError):
        accept_time_protection(db, preview, NOW)
    assert load_snapshot(db) == saved


def test_unavailable_alternative_does_not_save(tmp_path):
    db, task, _ = prepared_db(tmp_path)
    add_fixed_event(db, "All Thursday unavailable", THURSDAY, 10 * 60, 12 * 60)
    preview = preview_time_protection(
        load_snapshot(db), NOW, FRIDAY, 17 * 60, 21 * 60,
        required_ids=frozenset({task.id}),
    )
    assert not preview.feasible
    saved = load_snapshot(db)
    with pytest.raises(ValueError, match="feasible"):
        accept_time_protection(db, preview, NOW)
    assert load_snapshot(db) == saved


def test_changed_calendar_blocks_protection_undo(tmp_path):
    db, task, _ = prepared_db(tmp_path)
    preview = preview_time_protection(
        load_snapshot(db), NOW, FRIDAY, 17 * 60, 21 * 60,
        required_ids=frozenset({task.id}),
    )
    accept_time_protection(db, preview, NOW)
    add_fixed_event(db, "New commitment", THURSDAY, 14 * 60, 15 * 60)
    saved = load_snapshot(db)
    with pytest.raises(StaleProposalError):
        undo_last_plan_with_protection(db, NOW)
    assert load_snapshot(db) == saved


def test_outside_current_week_and_past_block_rejected(tmp_path):
    db, _, _ = prepared_db(tmp_path)
    snapshot = load_snapshot(db)
    with pytest.raises(ValueError, match="current planning week"):
        preview_time_protection(snapshot, NOW, date(2026, 12, 1), 17 * 60, 22 * 60)
    with pytest.raises(ValueError, match="future"):
        preview_time_protection(snapshot, NOW, NOW.date(), 8 * 60, 9 * 60)


def test_unrelated_undo_still_uses_standard_path(tmp_path):
    db, _, _ = prepared_db(tmp_path)
    assert plan_undo_status(db) == "ready"
    assert undo_last_plan_with_protection(db, NOW) == 0
    assert plan_undo_status(db) == "none"


def test_demo_generator_creates_separate_reversible_scenario(tmp_path):
    from scripts.create_life_demo import create_demo

    db = tmp_path / "life-demo.db"
    create_demo(db, NOW)
    snapshot = load_snapshot(db)
    assert any(session.day == FRIDAY and session.start == 17 * 60 for session in snapshot.sessions)
    assert any(event.kind == "Social" for event in snapshot.events)
    with pytest.raises(ValueError, match="existing file"):
        create_demo(db, NOW)


def test_social_commitments_allowed_inside_protected_time(tmp_path):
    db, task, _ = prepared_db(tmp_path)
    add_fixed_event(db, "Dinner", FRIDAY, 18 * 60, 19 * 60, "Social")
    preview = preview_time_protection(
        load_snapshot(db), NOW, FRIDAY, 17 * 60, 21 * 60,
        required_ids=frozenset({task.id}),
    )
    assert preview.feasible, preview.explanation
