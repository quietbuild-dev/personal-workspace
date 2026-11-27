"""Checklist-driven progress and reversible task completion: no DB migrations."""

from datetime import date
from types import SimpleNamespace

from workspace.advanced_repository import add_step, load_snapshot, set_checklist_done
from workspace.models import TaskDraft
from workspace.quick_tasks import create_quick_task, restore_just_completed_task, toggle_quick_task
from workspace.repository import list_tasks
from workspace.task_progress import ProgressPreference, progress_details, progress_html


def test_checklist_progress_only_when_selected_or_legacy_auto(tmp_path):
    db = tmp_path / "checklist.db"
    task_id = create_quick_task(db, TaskDraft("Project", deadline=date(2026, 12, 9)))
    ids = [add_step(db, task_id, f"Step {i + 1}", "checklist") for i in range(4)]
    before = load_snapshot(db)
    task = list_tasks(db)[0]
    checklist = [s for s in before.steps if s.kind == "checklist"]
    for pref in (None, ProgressPreference("checklist")):
        assert progress_details(task, checklist, preference=pref) == (0, "Checklist completed")
    assert progress_details(task, checklist, preference=ProgressPreference("manual", 85)) == (
        85,
        "My progress estimate",
    )
    set_checklist_done(db, ids[0], True)
    set_checklist_done(db, ids[1], True)
    snapshot = load_snapshot(db)
    items = [s for s in snapshot.steps if s.kind == "checklist"]
    assert progress_details(task, items, preference=ProgressPreference("checklist")) == (
        50,
        "Checklist completed",
    )
    assert progress_details(task, items, preference=ProgressPreference("manual", 85)) == (
        85,
        "My progress estimate",
    )
    html = progress_html(task, items)
    assert 'aria-valuenow="50"' in html
    assert "2 of 4 subtasks complete" in html
    assert list_tasks(db)[0].remaining_minutes == task.remaining_minutes
    assert list_tasks(db)[0].status == "pending"


def test_completed_task_can_be_undone_without_losing_partial_time(tmp_path):
    db = tmp_path / "undo.db"
    task_id = create_quick_task(db, TaskDraft("Assignment", deadline=date(2026, 12, 9)))
    from workspace.quick_tasks import edit_quick_task

    draft = TaskDraft("Assignment", deadline=date(2026, 12, 9))
    edit_quick_task(db, task_id, draft, 30)
    task = list_tasks(db)[0]
    assert task.remaining_minutes == 30
    set_ids = [add_step(db, task_id, f"Step {i}", "checklist") for i in range(2)]
    for step_id in set_ids:
        set_checklist_done(db, step_id, True)
    toggle_quick_task(db, task_id, True)
    assert list_tasks(db)[0].status == "completed"
    restore_just_completed_task(db, task_id, 30)
    task = list_tasks(db)[0]
    assert task.status == "pending"
    assert task.remaining_minutes == 30
    assert sum(s.checked for s in load_snapshot(db).steps if s.kind == "checklist") == 2


def test_completed_checklist_progress_and_fallback_without_subtasks():
    task = SimpleNamespace(status="completed", estimate_minutes=120, remaining_minutes=0)
    items = [SimpleNamespace(checked=True), SimpleNamespace(checked=False)]
    assert progress_details(task, items) == (100, "Completed")
    pending = SimpleNamespace(status="pending", estimate_minutes=120, remaining_minutes=30)
    assert progress_details(pending, ()) == (75, "Work completed")


def test_home_checklist_updates_storage_without_a_progress_slider(tmp_path, monkeypatch):
    import pytest

    pytest.importorskip("streamlit")
    from unittest.mock import MagicMock

    from workspace.overview import load_overview
    from workspace.views import home

    db = tmp_path / "home_checklist.db"
    task_id = create_quick_task(db, TaskDraft("Check the work"))
    ids = [add_step(db, task_id, f"Part {i}", "checklist") for i in (1, 2)]
    overview = load_overview(db, date(2026, 11, 27))
    fake = MagicMock()
    fake.session_state = {}
    fake.checkbox.side_effect = lambda label, *, value, **kwargs: (
        True if label == "Part 1" else value
    )
    monkeypatch.setattr(home, "st", fake)
    monkeypatch.setattr(home, "DEFAULT_DB_PATH", db)
    assert home._task_checklist(overview, overview.tasks[0], key_prefix="tasks")
    checks = [step for step in load_snapshot(db).steps if step.kind == "checklist"]
    assert sum(int(step.checked) for step in checks) == 1
    assert all(step.id in ids for step in checks)
    assert progress_details(list_tasks(db)[0], checks)[0] == 50
    fake.slider.assert_not_called()


def test_home_recent_completion_restores_earlier_remaining_minutes(tmp_path, monkeypatch):
    import pytest

    pytest.importorskip("streamlit")
    from unittest.mock import MagicMock

    from workspace.quick_tasks import edit_quick_task
    from workspace.views import home

    db = tmp_path / "home_undo.db"
    draft = TaskDraft("Read", deadline=date(2026, 12, 9))
    task_id = create_quick_task(db, draft)
    edit_quick_task(db, task_id, draft, 30)
    fake = MagicMock()
    fake.session_state = {}
    monkeypatch.setattr(home, "st", fake)
    monkeypatch.setattr(home, "DEFAULT_DB_PATH", db)
    task = list_tasks(db)[0]
    home._remember_task_done(task)
    assert list_tasks(db)[0].status == "completed"
    assert fake.session_state["just_completed_task"][2] == 30
    home._reopen_task(task)
    reopened = list_tasks(db)[0]
    assert reopened.status == "pending" and reopened.remaining_minutes == 30
