"""Targeted safeguards for Home native To-do rows and checklist completion."""

from datetime import date
from unittest.mock import MagicMock

import pytest

pytest.importorskip("streamlit")

from workspace.advanced_repository import add_step, load_snapshot
from workspace.models import TaskDraft
from workspace.overview import load_overview
from workspace.quick_tasks import create_quick_task
from workspace.repository import list_tasks
from workspace.task_modes import save_task_mode
from workspace.task_progress import save_progress_preference
from workspace.views import home


def _setup_task(tmp_path, monkeypatch, mode="checklist"):
    db = tmp_path / "checklist-polish.db"
    task_id = create_quick_task(db, TaskDraft("Project"), schedule=False)
    save_task_mode(db, task_id, "progress")
    save_progress_preference(db, task_id, mode, 25 if mode == "manual" else 0)
    first = add_step(db, task_id, "Part A", "checklist")
    second = add_step(db, task_id, "Part B", "checklist")
    fake = MagicMock()
    fake.session_state = {}
    monkeypatch.setattr(home, "st", fake)
    monkeypatch.setattr(home, "DEFAULT_DB_PATH", db)
    overview = load_overview(db, date(2026, 11, 27))
    items = [s for s in overview.advanced.steps if s.kind == "checklist"]
    return db, overview.tasks[0], items, (first, second), fake


def test_partial_checklist_does_not_finish_parent(tmp_path, monkeypatch):
    db, task, items, _ids, _fake = _setup_task(tmp_path, monkeypatch)
    home._save_checklist_item(task, items[0], items, True)
    assert list_tasks(db)[0].status == "pending"
    assert sum(step.checked for step in load_snapshot(db).steps if step.kind == "checklist") == 1


def test_last_subtask_completes_parent_and_keeps_undo_context(tmp_path, monkeypatch):
    db, task, items, _ids, fake = _setup_task(tmp_path, monkeypatch)
    home._save_checklist_item(task, items[0], items, True)
    overview = load_overview(db, date(2026, 11, 27))
    updated_items = [s for s in overview.advanced.steps if s.kind == "checklist"]
    home._save_checklist_item(overview.tasks[0], updated_items[1], updated_items, True)
    assert list_tasks(db)[0].status == "completed"
    assert all(s.checked for s in load_snapshot(db).steps if s.kind == "checklist")
    assert fake.session_state["just_completed_task"][0] == task.id


def test_manual_progress_with_subtasks_auto_finishes_on_last_check(tmp_path, monkeypatch):
    db, task, items, _ids, _fake = _setup_task(tmp_path, monkeypatch, "manual")
    home._save_checklist_item(task, items[0], items, True)
    overview = load_overview(db, date(2026, 11, 27))
    updated_items = [s for s in overview.advanced.steps if s.kind == "checklist"]
    home._save_checklist_item(overview.tasks[0], updated_items[1], updated_items, True)
    assert list_tasks(db)[0].status == "completed"


def test_unchecking_never_completes_parent(tmp_path, monkeypatch):
    db, task, items, _ids, _fake = _setup_task(tmp_path, monkeypatch)
    home._save_checklist_item(task, items[0], items, False)
    assert list_tasks(db)[0].status == "pending"
