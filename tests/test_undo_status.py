"""Undo explanations should be honest even after intervening edits."""

from datetime import date, datetime

from workspace.advanced_planner import make_revision
from workspace.advanced_repository import (
    accept_revision,
    add_fixed_event,
    load_snapshot,
    plan_undo_status,
    save_week_preferences,
)
from workspace.models import TaskDraft
from workspace.quick_tasks import create_quick_task


def test_undo_states_after_approval_and_new_calendar_event(tmp_path):
    db = tmp_path / "undo.db"
    today = date(2026, 11, 25)
    create_quick_task(db, TaskDraft("Testing", "University", today, 2, 60))
    save_week_preferences(db, (today,), 120, 9 * 60, 13 * 60)
    now = datetime(2026, 11, 25, 8)
    snap = load_snapshot(db)
    assert plan_undo_status(db) == "none"
    accept_revision(db, make_revision(snap, now), now)
    assert plan_undo_status(db) == "ready"
    add_fixed_event(db, "Gym", today, 1000, 1060, "Exercise")
    assert plan_undo_status(db) == "changed"
