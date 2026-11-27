"""Final task-method decisions and calendar-entry-point regression checks."""

from pathlib import Path

import pytest

from workspace.advanced_repository import add_step, load_snapshot, set_checklist_done
from workspace.models import TaskDraft
from workspace.quick_tasks import create_quick_task, edit_quick_task
from workspace.repository import list_tasks
from workspace.task_modes import load_task_modes, save_task_mode
from workspace.task_progress import (
    ProgressPreference,
    load_progress_preferences,
    progress_details,
    progress_html,
    save_progress_preference,
    tracking_choice,
)

ROOT = Path(__file__).resolve().parents[1]


def test_time_mode_is_persistent_and_follows_recorded_minutes(tmp_path):
    db = tmp_path / "video.db"
    task_id = create_quick_task(db, TaskDraft("Watch lecture video", estimate_minutes=90))
    save_task_mode(db, task_id, "progress")
    save_progress_preference(db, task_id, "time")
    task = list_tasks(db)[0]
    pref = load_progress_preferences(db)[task_id]
    assert tracking_choice(task, load_task_modes(db)[task_id], pref) == "Time tracked"
    assert progress_details(task, preference=pref)[0] == 0

    edit_quick_task(db, task_id, TaskDraft("Watch lecture video", estimate_minutes=90), 50)
    updated = list_tasks(db)[0]
    timed = [s for s in load_snapshot(db).steps if s.task_id == task_id and s.kind == "timed"]
    assert updated.status == "pending"
    assert progress_details(updated, timed_steps=timed, preference=pref)[0] == 44
    html = progress_html(updated, timed_steps=timed, preference=pref)
    assert "40 of 90 min completed" in html
    assert 'aria-valuenow="44"' in html
    assert load_progress_preferences(db)[task_id] == ProgressPreference("time", 0)


def test_optional_checklist_does_not_override_saved_time_or_manual(tmp_path):
    db = tmp_path / "choice.db"
    task_id = create_quick_task(db, TaskDraft("Course", estimate_minutes=60))
    save_task_mode(db, task_id, "progress")
    save_progress_preference(db, task_id, "time")
    checklist_id = add_step(db, task_id, "Take notes", "checklist")
    set_checklist_done(db, checklist_id, True)
    item = next(s for s in load_snapshot(db).steps if s.id == checklist_id)
    task = list_tasks(db)[0]
    assert tracking_choice(task, "progress", ProgressPreference("time"), [item]) == "Time tracked"
    assert progress_details(task, [item], preference=ProgressPreference("time"))[0] == 0
    save_progress_preference(db, task_id, "manual", 35)
    pref = load_progress_preferences(db)[task_id]
    assert tracking_choice(task, "progress", pref, [item]) == "Progress bar"
    assert progress_details(task, [item], preference=pref)[0] == 35


def test_simple_to_do_never_infers_checklist_or_shows_a_bar(tmp_path):
    db = tmp_path / "todo.db"
    task_id = create_quick_task(db, TaskDraft("Pay rent"), schedule=False)
    save_task_mode(db, task_id, "simple")
    task = list_tasks(db)[0]
    assert tracking_choice(task, load_task_modes(db)[task_id]) == "Simple to-do"
    assert task.status == "pending"


def test_energy_mode_is_not_a_calendar_page_control():
    source = (ROOT / "workspace/views/week.py").read_text("utf-8")
    assert "render_energy_today" not in source
    assert "render_time_protection(snapshot, now, DEFAULT_DB_PATH)" in source
    assert '"Export calendar"' in source


def test_time_entry_helper_updates_existing_task_without_changing_method(tmp_path, monkeypatch):
    pytest.importorskip("streamlit")
    from unittest.mock import MagicMock

    from workspace.views import home

    db = tmp_path / "time-entry.db"
    task_id = create_quick_task(db, TaskDraft("Video", estimate_minutes=80))
    save_task_mode(db, task_id, "progress")
    save_progress_preference(db, task_id, "time")
    fake = MagicMock()
    fake.session_state = {"partial_task_id": task_id, "open_task_details": task_id}
    monkeypatch.setattr(home, "st", fake)
    monkeypatch.setattr(home, "DEFAULT_DB_PATH", db)
    home._save_time_progress(list_tasks(db)[0], 25)
    updated = list_tasks(db)[0]
    assert updated.remaining_minutes == 55 and updated.status == "pending"
    assert load_progress_preferences(db)[task_id].mode == "time"
    assert "partial_task_id" not in fake.session_state
    assert "open_task_details" not in fake.session_state

    with pytest.raises(ValueError, match="Completed minutes"):
        home._save_time_progress(updated, 81)
    assert list_tasks(db)[0].remaining_minutes == 55
