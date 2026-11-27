"""Progress choice is per task, saved locally, and never books study time."""

from datetime import date
from types import SimpleNamespace

import pytest

from workspace.advanced_repository import load_snapshot
from workspace.models import TaskDraft
from workspace.quick_tasks import create_quick_task, restore_just_completed_task, toggle_quick_task
from workspace.repository import delete_task, list_tasks
from workspace.task_progress import (
    ProgressPreference,
    load_progress_preferences,
    progress_details,
    save_progress_preference,
)


def _task(db, title="Exam notes", minutes=120):
    return create_quick_task(db, TaskDraft(title, "University", date(2026, 12, 2), 3, minutes))


def test_manual_percentage_is_local_and_does_not_count_as_logged_study(tmp_path):
    alice = tmp_path / "alice.db"
    mia = tmp_path / "mia.db"
    task_id = _task(alice)
    other_id = _task(mia)
    before = load_snapshot(alice)
    save_progress_preference(alice, task_id, "manual", 65)
    pref = load_progress_preferences(alice)[task_id]
    assert pref == ProgressPreference("manual", 65)
    assert progress_details(list_tasks(alice)[0], preference=pref) == (65, "My progress estimate")
    assert other_id not in load_progress_preferences(mia)
    after = load_snapshot(alice)
    assert after.fingerprint == before.fingerprint
    assert after.steps[0].remaining_minutes == before.steps[0].remaining_minutes
    delete_task(alice, task_id)
    assert task_id not in load_progress_preferences(alice)


def test_explicit_progress_mode_wins_over_optional_checklist():
    task = SimpleNamespace(status="pending", remaining_minutes=90, estimate_minutes=120)
    checks = [SimpleNamespace(checked=True), SimpleNamespace(checked=False)]
    timed = [SimpleNamespace(kind="timed", estimate_minutes=120, remaining_minutes=90)]
    assert progress_details(task, checks, timed) == (50, "Checklist completed")
    # The user's saved choice remains authoritative even when subtasks exist.
    assert progress_details(task, checks, timed, ProgressPreference("time")) == (
        25,
        "Work completed",
    )
    assert progress_details(task, checks, timed, ProgressPreference("manual", 30)) == (
        30,
        "My progress estimate",
    )
    assert progress_details(task, checks, timed, ProgressPreference("checklist")) == (
        50,
        "Checklist completed",
    )


def test_progress_method_validated(tmp_path):
    db = tmp_path / "progress.db"
    task_id = _task(db)
    for mode, pct in (("unknown", 10), ("manual", 101), ("manual", -1)):
        with pytest.raises(ValueError):
            save_progress_preference(db, task_id, mode, pct)
    with pytest.raises(ValueError):
        save_progress_preference(db, task_id + 1, "auto", 10)


def test_recent_task_completion_can_restore_partial_work_atomically(tmp_path):
    from workspace.quick_tasks import edit_quick_task

    db = tmp_path / "undo_task.db"
    task_id = _task(db)
    draft = TaskDraft("Exam notes", "University", date(2026, 12, 2), 3, 120)
    edit_quick_task(db, task_id, draft, 40)
    toggle_quick_task(db, task_id, True)
    assert list_tasks(db)[0].status == "completed"
    restore_just_completed_task(db, task_id, 40)
    reopened = list_tasks(db)[0]
    assert reopened.status == "pending" and reopened.remaining_minutes == 40
    assert load_snapshot(db).steps[0].remaining_minutes == 40
