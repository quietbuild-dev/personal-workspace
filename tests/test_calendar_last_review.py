"""Calendar presentation and reversible stale-booking regression tests."""

import sqlite3
from datetime import date, datetime

import pytest

from workspace.advanced_repository import add_window, load_snapshot
from workspace.energy_today import energy_proposal
from workspace.life_planning import preview_time_protection_many
from workspace.models import TaskDraft
from workspace.quick_tasks import create_quick_task, toggle_quick_task
from workspace.scoped_planning import saved_future_slots
from workspace.stale_bookings import (
    outdated_planned_sessions,
    outdated_undo_available,
    remove_outdated_bookings,
    undo_outdated_cleanup,
)

NOW = datetime(2026, 11, 27, 9, 0)
FRIDAY = date(2026, 11, 27)
SATURDAY = date(2026, 11, 28)


def setup_outdated(tmp_path):
    db = tmp_path / "cleanup.db"
    completed_id = create_quick_task(
        db, TaskDraft("Completed assignment", "Study", SATURDAY, 2, 60)
    )
    active_id = create_quick_task(db, TaskDraft("Still active", "Study", SATURDAY, 3, 60))
    add_window(db, SATURDAY, 540, 1080)
    snapshot = load_snapshot(db)
    steps = {step.task_id: step.id for step in snapshot.steps if step.kind == "timed"}
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO scheduled_sessions(step_id,day,start_minute,end_minute) VALUES (?,?,?,?)",
            (steps[completed_id], SATURDAY.isoformat(), 600, 660),
        )
        conn.execute(
            "INSERT INTO scheduled_sessions(step_id,day,start_minute,end_minute) VALUES (?,?,?,?)",
            (steps[active_id], SATURDAY.isoformat(), 720, 780),
        )
        conn.execute(
            "INSERT INTO scheduled_sessions("
            "step_id,day,start_minute,end_minute,status,actual_minutes) "
            "VALUES (?,?,?,?,?,?)",
            (steps[completed_id], FRIDAY.isoformat(), 480, 500, "done", 20),
        )
    toggle_quick_task(db, completed_id, True)
    return db


def test_explicit_cleanup_never_modifies_preview_and_preserves_history(tmp_path):
    db = setup_outdated(tmp_path)
    original = load_snapshot(db)
    outdated = outdated_planned_sessions(original, NOW)
    assert len(outdated) == 1
    assert not outdated_undo_available(db)
    with pytest.raises(ValueError, match="outdated study booking"):
        saved_future_slots(original, NOW)
    with pytest.raises(ValueError, match="outdated study booking"):
        energy_proposal(original, NOW, "Low energy", SATURDAY)
    with pytest.raises(ValueError, match="outdated study booking"):
        preview_time_protection_many(original, NOW, ((SATURDAY, 720, 780),))
    assert load_snapshot(db) == original

    removed = remove_outdated_bookings(db, NOW, original.fingerprint, (outdated[0].id,))
    assert removed == 1
    cleaned = load_snapshot(db)
    assert sum(s.status == "planned" for s in cleaned.sessions) == 1
    assert any(s.status == "done" and s.actual_minutes == 20 for s in cleaned.sessions)
    assert outdated_planned_sessions(cleaned, NOW) == ()
    assert len(saved_future_slots(cleaned, NOW)) == 1
    assert outdated_undo_available(db)
    assert energy_proposal(cleaned, NOW, "Normal", SATURDAY).slots
    protected = preview_time_protection_many(cleaned, NOW, ((SATURDAY, 720, 780),))
    assert protected.feasible, protected.explanation
    assert sum(slot.minutes for slot in protected.revision.slots) == 60
    assert load_snapshot(db) == cleaned  # a preview is still read-only
    assert undo_outdated_cleanup(db) == 1
    assert load_snapshot(db).sessions == original.sessions
    assert not outdated_undo_available(db)


def test_cleanup_refuses_stale_snapshot_and_wrong_ids(tmp_path):
    db = setup_outdated(tmp_path)
    before = load_snapshot(db)
    stale = outdated_planned_sessions(before, NOW)
    with pytest.raises(ValueError, match="Review the latest"):
        remove_outdated_bookings(db, NOW, before.fingerprint, (9999,))
    with pytest.raises(ValueError, match="Select outdated"):
        remove_outdated_bookings(db, NOW, before.fingerprint, ())
    with pytest.raises(ValueError, match="Calendar changed"):
        remove_outdated_bookings(db, NOW, "stale-hash", (stale[0].id,))
    assert load_snapshot(db).sessions == before.sessions


def test_cleanup_undo_denied_after_new_data_changes(tmp_path):
    db = setup_outdated(tmp_path)
    before = load_snapshot(db)
    stale = outdated_planned_sessions(before, NOW)
    remove_outdated_bookings(db, NOW, before.fingerprint, (stale[0].id,))
    create_quick_task(db, TaskDraft("New task", "Personal", SATURDAY, 1, 20))
    assert not outdated_undo_available(db)
    with pytest.raises(ValueError, match="Calendar changed"):
        undo_outdated_cleanup(db)


def test_calendar_markup_uses_no_floating_labels():
    from workspace.advanced_planner import FixedEvent
    from workspace.views.weekly_calendar import calendar_html

    event = FixedEvent(1, "Quick 15-minute plan", SATURDAY, 600, 615, "Personal")
    html = calendar_html((event,), (), {}, SATURDAY, SATURDAY)
    assert "wp-short" in html
    assert "overflow:visible!important" not in html
    assert "box-shadow:0 2px 6px" not in html
    assert 'title="Quick 15-minute plan' in html
    assert "width:min(100%,980px)" in html


def test_comparison_calendar_has_taller_human_readable_blocks():
    from workspace.advanced_planner import FixedEvent
    from workspace.views.schedule_comparison import before_after_html

    event = FixedEvent(1, "Morning errands", SATURDAY, 600, 615, "Personal")
    html = before_after_html(SATURDAY, (event,), (), (), {})
    assert "scale = 1.10" not in html  # layout calculation does not leak into HTML
    assert "cmp-compact" in html
    assert "overflow:hidden" in html
    assert 'title="Morning errands' in html
