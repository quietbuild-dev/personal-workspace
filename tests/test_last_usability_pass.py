"""Focused safety checks for the final UI refinement pass."""

from datetime import date

import pytest

from workspace.advanced_planner import Slot
from workspace.recurrence import FREQUENCIES
from workspace.repository import initialize_database
from workspace.study_dna import (
    StudyDNA,
    custom_concentration,
    custom_focus_range,
    load_study_dna,
    preferred_overlap_minutes,
    save_study_dna,
)


def test_five_minute_time_inputs_in_calendar_and_personal_time():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    calendar_ui = (root / "workspace/views/week.py").read_text(encoding="utf-8")
    free_time_ui = (root / "workspace/views/life_time.py").read_text(encoding="utf-8")
    assert "range(0, 60, 5)" in calendar_ui
    assert "_event_time_choices(event.start, event.end)" in calendar_ui
    assert "tuple(range(0, 1441, 5))" in free_time_ui
    assert "disabled=not windows" not in free_time_ui


def test_custom_focus_times_saved_and_used_by_optimizer_preference(tmp_path):
    database = tmp_path / "study.db"
    initialize_database(database)
    focus = custom_concentration(9 * 60 + 15, 14 * 60 + 45)
    assert focus == "custom:0915-1445"
    assert custom_focus_range(focus) == (555, 885)
    profile = StudyDNA("", focus, "balanced", "steady", "moderate")
    save_study_dna(database, profile)
    saved = load_study_dna(database)
    assert saved.focus_window == (555, 885)
    assert (
        preferred_overlap_minutes((Slot(1, date(2026, 11, 27), 600, 660),), saved.focus_window)
        == 60
    )


@pytest.mark.parametrize(
    "text", ["custom:2400-2500", "custom:0955-0910", "custom:abc", "custom:0960-1210"]
)
def test_bad_custom_focus_formats_are_rejected(text):
    with pytest.raises(ValueError, match="concentration"):
        StudyDNA(concentration=text)


def test_previous_recurrence_api_unchanged():
    assert FREQUENCIES[0] == "Never"  # Only the display label changes.
