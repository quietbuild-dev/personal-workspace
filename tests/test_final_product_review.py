"""Regression tests for the approved final product review and safe storage."""

from datetime import date, datetime
from pathlib import Path

import pytest

from workspace.advanced_planner import Slot
from workspace.advanced_repository import (
    accept_revision,
    add_fixed_event,
    add_window,
    load_snapshot,
    update_fixed_event,
)
from workspace.categories import (
    DEFAULT_CATEGORIES,
    category_colors,
    create_category,
    list_categories,
)
from workspace.energy_today import energy_proposal
from workspace.home_intelligence import daily_briefing, deadline_runway
from workspace.models import TaskDraft
from workspace.optimizer import proposal_from_slots
from workspace.quick_tasks import create_quick_task
from workspace.recurrence import add_recurring_event
from workspace.study_breaks import get_break_minutes, set_break_minutes

NOW = datetime(2026, 11, 26, 8)
THURSDAY = date(2026, 11, 26)
FRIDAY = date(2026, 11, 27)


def test_shared_saved_category_survives_new_connection(tmp_path):
    db = tmp_path / "categories.db"
    assert DEFAULT_CATEGORIES == (
        "Study",
        "Lecture",
        "Social",
        "Exercise",
        "Personal",
        "Errands",
        "Home",
        "Other",
    )
    category = create_category(db, "Volunteering")
    assert category == "Volunteering"
    color = category_colors(db)[category]
    assert color.startswith("#") and len(color) == 7
    assert color != category_colors(db)["Social"]
    assert create_category(db, " volunteering ") == "Volunteering"
    assert list_categories(db).count(category) == 1
    assert category_colors(db)[category] == color


def test_shared_custom_category_used_by_task_calendar_and_recurrence(tmp_path):
    db = tmp_path / "categories.db"
    create_category(db, "Student club")
    task_id = create_quick_task(db, TaskDraft("Prepare meeting", "Student club"))
    event_id = add_fixed_event(db, "Club gathering", THURSDAY, 18 * 60, 19 * 60, "Student club")
    update_fixed_event(db, event_id, "Club gathering", THURSDAY, 18 * 60, 19 * 60, "Study")
    update_fixed_event(db, event_id, "Club gathering", THURSDAY, 18 * 60, 19 * 60, "Student club")
    snap = load_snapshot(db)
    assert any(event.id == event_id and event.kind == "Student club" for event in snap.events)
    from workspace.repository import list_tasks

    assert any(task.id == task_id and task.category == "Student club" for task in list_tasks(db))
    # The recurring importer and editor share the same persisted category name.
    add_recurring_event(
        db, "Club weekly call", THURSDAY, 12 * 60, 13 * 60, "Student club", "Weekly", FRIDAY
    )
    assert any(event.kind == "Student club" for event in load_snapshot(db).events)


def test_unknown_custom_event_category_is_rejected_without_writes(tmp_path):
    db = tmp_path / "categories.db"
    with pytest.raises(ValueError, match="Save the new category"):
        add_fixed_event(db, "Unknown event", THURSDAY, 700, 730, "Unregistered category")
    assert load_snapshot(db).events == ()


def test_study_break_default_and_persistence(tmp_path):
    db = tmp_path / "study.db"
    assert get_break_minutes(db) == 5
    set_break_minutes(db, 10)
    assert get_break_minutes(db) == 10
    set_break_minutes(db, 0)
    assert get_break_minutes(db) == 0
    with pytest.raises(ValueError):
        set_break_minutes(db, 7)


def test_energy_preserves_booked_minutes_and_other_days(tmp_path):
    db = tmp_path / "energy.db"
    create_quick_task(db, TaskDraft("Statistics", "Study", FRIDAY, 3, 120), schedule=True)
    snap = load_snapshot(db)
    step_id = snap.steps[0].id
    add_window(db, FRIDAY, 9 * 60, 14 * 60)
    snap = load_snapshot(db)
    accept_revision(db, proposal_from_slots(snap, NOW, (Slot(step_id, FRIDAY, 600, 720),)), NOW)
    before = load_snapshot(db)
    proposal = energy_proposal(before, NOW, "Low energy", FRIDAY, break_minutes=5)
    assert sum(s.minutes for s in proposal.slots) == 120
    assert all(s.minutes >= 20 for s in proposal.slots)
    assert load_snapshot(db) == before
    slots = sorted(proposal.slots, key=lambda s: s.start)
    if len(slots) > 1:
        assert all(b.start >= a.end + 5 for a, b in zip(slots, slots[1:]))


def test_runway_shows_only_upcoming_deadlines(tmp_path):
    from datetime import timezone

    from workspace.models import Task

    def task_info(title, due, index):
        return Task(
            index,
            title,
            "Study",
            due,
            2,
            60,
            60,
            "pending",
            datetime(2026, 11, 25, tzinfo=timezone.utc),
            None,
        )

    db = tmp_path / "due.db"
    snapshot = load_snapshot(db)
    tasks = (
        task_info("Overdue", date(2026, 11, 20), 1),
        task_info("Due tomorrow", FRIDAY, 2),
    )
    rows = deadline_runway(tasks, snapshot, NOW)
    assert len(rows) == 1 and rows[0].title == "Due tomorrow"
    assert "overdue" not in daily_briefing(tasks, snapshot, NOW).text.lower()


def test_css_is_inside_style_tag_and_chart_has_sharp_corners():
    from workspace.theme import GLOBAL_CSS

    assert GLOBAL_CSS.strip().startswith("<style>")
    assert GLOBAL_CSS.strip().endswith("</style>")
    assert GLOBAL_CSS.count("</style>") == 1
    assert "border-radius:0!important" in GLOBAL_CSS


def test_removed_entry_points_and_calendar_import_export_order():
    root = Path(__file__).resolve().parents[1]
    board = (root / "workspace/views/task_board.py").read_text(encoding="utf-8")
    calendar = (root / "workspace/views/week.py").read_text(encoding="utf-8")
    assert "render_smart_capture" not in board
    assert "Quick task entry" not in board
    assert not (root / "workspace/smart_capture.py").exists()
    assert "More options" not in calendar
    assert calendar.index('"Export calendar"') < calendar.index("render_calendar_import(")
