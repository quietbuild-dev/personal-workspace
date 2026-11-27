"""Regression tests for user-requested cleanup and real calendar recurrence."""

from datetime import date

import pytest

from tests.test_life_planning import FRIDAY, NOW, THURSDAY, prepared_db
from workspace.advanced_repository import add_fixed_event, load_snapshot
from workspace.life_planning import (
    accept_time_protection,
    preview_time_protection_many,
    undo_last_plan_with_protection,
)
from workspace.recurrence import (
    add_recurring_event,
    delete_recurring_series,
    occurrences,
    series_info,
)
from workspace.task_modes import is_simple_task, load_task_modes, save_task_mode


def test_monthly_recurrence_preserves_end_of_month():
    assert occurrences(date(2026, 1, 31), date(2026, 4, 30), "Monthly") == (
        date(2026, 1, 31), date(2026, 2, 28),
        date(2026, 3, 31), date(2026, 4, 30),
    )


def test_yearly_leap_day_is_clamped():
    assert occurrences(date(2028, 2, 29), date(2030, 3, 1), "Yearly") == (
        date(2028, 2, 29), date(2029, 2, 28), date(2030, 2, 28)
    )


def test_recurrence_is_one_transaction_and_series_delete(tmp_path):
    db, _, _ = prepared_db(tmp_path)
    ids = add_recurring_event(
        db, "Algorithms", FRIDAY, 600, 660, "Lecture", "Weekly",
        date(2026, 12, 18),
    )
    assert len(ids) == 4
    assert series_info(db, ids[0])[1:] == ("Weekly", 4)
    assert all(event.id in ids for event in load_snapshot(db).events if event.title == "Algorithms")
    assert delete_recurring_series(db, ids[1]) == 4
    assert not any(event.title == "Algorithms" for event in load_snapshot(db).events)


def test_recurrence_invalid_dates_leave_db_unchanged(tmp_path):
    db, _, _ = prepared_db(tmp_path)
    before = load_snapshot(db)
    with pytest.raises(ValueError):
        add_recurring_event(db, "Lecture", FRIDAY, 600, 660, "Lecture", "Monthly", THURSDAY)
    assert load_snapshot(db) == before


def test_explicit_simple_mode_overrides_legacy_steps(tmp_path):
    db, task, _ = prepared_db(tmp_path)
    snapshot = load_snapshot(db)
    assert not is_simple_task(task, snapshot.steps, load_task_modes(db))
    save_task_mode(db, task.id, "simple")
    assert is_simple_task(task, snapshot.steps, load_task_modes(db))
    save_task_mode(db, task.id, "progress")
    assert not is_simple_task(task, snapshot.steps, load_task_modes(db))


def test_multiple_protected_windows_and_undo_with_social_plan(tmp_path):
    db, task, _ = prepared_db(tmp_path)
    add_fixed_event(db, "Dinner", FRIDAY, 1080, 1170, "Social")
    before = load_snapshot(db)
    windows = ((THURSDAY, 1080, 1200), (FRIDAY, 1020, 1260))
    preview = preview_time_protection_many(
        before, NOW, windows, required_ids=frozenset({task.id}),
    )
    assert preview.feasible, preview.explanation
    accept_time_protection(db, preview, NOW)
    accepted = load_snapshot(db)
    assert sum(
        event.title == "Personal time (protected)" for event in accepted.events
    ) == 2
    assert any(event.title == "Dinner" for event in accepted.events)
    undo_last_plan_with_protection(db, NOW)
    assert load_snapshot(db) == before


def test_overlapping_multiple_windows_are_rejected(tmp_path):
    db, _, _ = prepared_db(tmp_path)
    with pytest.raises(ValueError, match="overlap"):
        preview_time_protection_many(
            load_snapshot(db), NOW,
            ((FRIDAY, 1000, 1200), (FRIDAY, 1100, 1250)),
        )
