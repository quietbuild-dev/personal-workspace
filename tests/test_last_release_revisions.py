"""Last-release regression checks: local export, progress closing, and readable comparisons."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from workspace.calendar_export import save_calendar_to_downloads
from workspace.views.schedule_comparison import before_after_html


def test_local_calendar_export_reports_real_path_and_preserves_old_files(tmp_path):
    start = date(2026, 11, 23)
    first = save_calendar_to_downloads(b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", start, tmp_path)
    second = save_calendar_to_downloads(b"SECOND", start, tmp_path)
    assert first.name == "personal-workspace-2026-11-23.ics"
    assert second.name == "personal-workspace-2026-11-23-2.ics"
    assert first.read_bytes() == b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"
    assert second.read_bytes() == b"SECOND"
    assert first.parent == tmp_path


def test_local_calendar_export_does_not_create_unrequested_folders(tmp_path):
    with pytest.raises(FileNotFoundError, match="Downloads folder not found"):
        save_calendar_to_downloads(b"data", date(2026, 11, 23), tmp_path / "absent")


def test_schedule_comparison_uses_solid_blocks_and_legible_unchanged_sessions():
    from workspace.advanced_planner import FixedEvent

    day = date(2026, 11, 27)
    event = FixedEvent(11, "Lunch with classmates", day, 750, 810, "Social")
    html = before_after_html(day, (event,), (), (), {})
    assert "border:1px dashed" not in html
    assert ".cmp-old{" in html
    assert ".cmp-same {opacity:.9!important;}" in html
    assert "Lunch with classmates" in html


def test_home_task_summary_is_rendered_directly_after_its_own_actions(monkeypatch):
    pytest.importorskip("streamlit")
    from workspace.views import home

    fake = MagicMock()
    fake.session_state = {"open_task_details": 42, "home_details_origin": "home"}
    fake.columns.side_effect = lambda values, **_: [fake] * len(values)
    fake.button.return_value = False
    monkeypatch.setattr(home, "st", fake)
    monkeypatch.setattr(home, "category_colors", lambda *_: {"Personal": "#abc"})
    monkeypatch.setattr(home, "list_task_due_times", lambda *_: {})
    rendered = []
    monkeypatch.setattr(home, "_edit_task", lambda *_: rendered.append("42"))

    home._home_task_actions(SimpleNamespace(id=41), object())
    assert rendered == []
    home._home_task_actions(SimpleNamespace(id=42), object())
    assert rendered == ["42"]
    home._home_task_actions(SimpleNamespace(id=43), object(), key_prefix="home_due")
    assert rendered == ["42"]


def test_both_progress_modes_close_after_saving(monkeypatch):
    pytest.importorskip("streamlit")
    from workspace.views import home

    fake = MagicMock()
    fake.session_state = {
        "partial_task_id": 24,
        "open_task_details": 24,
        "home_quick_progress": 24,
        "home_details_origin": "home",
        "task_more_details_id": 24,
    }
    monkeypatch.setattr(home, "st", fake)
    saved = []
    monkeypatch.setattr(
        home,
        "save_progress_preference",
        lambda path, task, mode, percent: saved.append((task, mode, percent)),
    )
    home._save_progress_preference_and_close(24, "time", 25)
    assert saved == [(24, "time", 25)]
    assert fake.session_state == {}
    fake.session_state = {"open_task_details": 5, "home_quick_progress": 5}
    home._save_progress_preference_and_close(5, "manual", 60)
    assert saved[-1] == (5, "manual", 60)
    assert fake.session_state == {}
