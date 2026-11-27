"""Regression checks for the final, deliberately simple product refinements."""

from datetime import date, datetime

import pytest

from workspace.advanced_planner import Slot, validate_revision
from workspace.advanced_repository import (
    accept_revision,
    add_fixed_event,
    add_window,
    delete_fixed_event,
    get_event_notes,
    load_snapshot,
    update_fixed_event,
)
from workspace.energy_today import energy_proposal
from workspace.models import TaskDraft
from workspace.optimizer import proposal_from_slots
from workspace.quick_tasks import create_quick_task
from workspace.recurrence import add_recurring_event

DAY = date(2026, 11, 25)
NOW = datetime(2026, 11, 25, 8)


def test_event_notes_optional_editable_and_deletable(tmp_path):
    db = tmp_path / "notes.db"
    plain = add_fixed_event(db, "No notes", DAY, 600, 620, "Personal")
    assert get_event_notes(db, plain) == ""
    event = add_fixed_event(db, "Lecture", DAY, 650, 690, "Lecture", "Room 301")
    assert get_event_notes(db, event) == "Room 301"
    update_fixed_event(db, event, "Lecture moved", DAY, 660, 700, "Lecture", notes="Room 302")
    assert get_event_notes(db, event) == "Room 302"
    update_fixed_event(db, event, "Lecture moved", DAY, 660, 700, "Lecture", notes="")
    assert get_event_notes(db, event) == ""
    update_fixed_event(db, event, "Lecture moved", DAY, 660, 700, "Lecture", notes="Final")
    delete_fixed_event(db, event)
    assert get_event_notes(db, event) == ""


def test_old_event_editor_preserves_notes_without_explicit_new_notes(tmp_path):
    db = tmp_path / "notes.db"
    event = add_fixed_event(db, "Meeting", DAY, 600, 645, "Social", "Bring documents")
    update_fixed_event(db, event, "Meeting", DAY, 610, 655, "Social")
    assert get_event_notes(db, event) == "Bring documents"


def test_notes_validation_happens_before_database_writes(tmp_path):
    db = tmp_path / "notes.db"
    before = load_snapshot(db)
    with pytest.raises(ValueError, match="notes"):
        add_fixed_event(db, "Meeting", DAY, 600, 645, "Social", "x" * 4001)
    assert load_snapshot(db) == before


def test_recurring_notes_saved_to_all_occurrences(tmp_path):
    db = tmp_path / "notes.db"
    ids = add_recurring_event(
        db,
        "Tutoring",
        DAY,
        600,
        630,
        "Lecture",
        "Daily",
        date(2026, 11, 27),
        notes="Online",
    )
    assert len(ids) == 3
    assert all(get_event_notes(db, event_id) == "Online" for event_id in ids)


def _saved_study(tmp_path, minutes=120, window_minutes=240):
    db = tmp_path / "focus.db"
    create_quick_task(db, TaskDraft("Study statistics", "Study", date(2026, 11, 27), 3, minutes))
    add_window(db, DAY, 540, 540 + window_minutes)
    snapshot = load_snapshot(db)
    slot = Slot(snapshot.steps[0].id, DAY, 540, 540 + minutes)
    accept_revision(db, proposal_from_slots(snapshot, NOW, (slot,)), NOW)
    return db, load_snapshot(db)


def test_normal_energy_never_changes_booked_work(tmp_path):
    db, snapshot = _saved_study(tmp_path)
    proposal = energy_proposal(snapshot, NOW, "Normal", DAY)
    saved = {(s.step_id, s.day, s.start, s.end) for s in snapshot.sessions if s.status == "planned"}
    assert set(proposal.slots) == {Slot(*item) for item in saved}
    assert load_snapshot(db) == snapshot


def test_low_energy_four_short_blocks_then_long_rest(tmp_path):
    _, snapshot = _saved_study(tmp_path, minutes=125, window_minutes=300)
    proposal = energy_proposal(snapshot, NOW, "Low energy", DAY, break_minutes=5)
    validate_revision(snapshot, proposal, NOW)
    slots = sorted(proposal.slots, key=lambda slot: slot.start)
    assert len(slots) == 5
    assert all(20 <= slot.minutes <= 25 for slot in slots)
    assert sum(slot.minutes for slot in slots) == 125
    gaps = [b.start - a.end for a, b in zip(slots, slots[1:])]
    assert gaps == [5, 5, 5, 15]


def test_low_energy_cannot_reduce_work_to_make_room_for_breaks(tmp_path):
    db, snapshot = _saved_study(tmp_path, minutes=120, window_minutes=120)
    proposal = energy_proposal(snapshot, NOW, "Low energy", DAY, break_minutes=5)
    assert proposal.slots == (Slot(snapshot.steps[0].id, DAY, 540, 660),)
    assert load_snapshot(db) == snapshot


def test_simple_sort_options_and_ui_copy():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    board = (root / "workspace/views/task_board.py").read_text(encoding="utf-8")
    home = (root / "workspace/views/home_briefing.py").read_text(encoding="utf-8")
    calendar = (root / "workspace/views/week.py").read_text(encoding="utf-8")
    assert '("Deadline", "Priority", "Category")' in board
    assert "Search tasks" not in board
    assert "st.switch_page(" in home
    assert "Coming up" not in home
    assert "get_event_notes(DEFAULT_DB_PATH, event.id)" in calendar
    assert '"Notes (optional)"' in calendar
    assert "What would change" not in calendar
