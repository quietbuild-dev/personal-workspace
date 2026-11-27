"""Final user-approved tracking choices and short, safe Low Energy blocks."""

from datetime import date, datetime

from workspace.advanced_planner import Slot, validate_revision
from workspace.advanced_repository import (
    accept_revision,
    add_fixed_event,
    add_step,
    add_window,
    load_snapshot,
    set_checklist_done,
)
from workspace.categories import (
    DEFAULT_CATEGORIES,
    category_colors,
    create_category,
    list_categories,
)
from workspace.energy_today import divide_slot, energy_proposal
from workspace.models import TaskDraft
from workspace.optimizer import proposal_from_slots
from workspace.quick_tasks import create_quick_task
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

DAY = date(2026, 11, 25)
NOW = datetime(2026, 11, 25, 8)


def test_manual_mode_is_not_overridden_when_subtasks_are_added(tmp_path):
    db = tmp_path / "progress.db"
    task_id = create_quick_task(db, TaskDraft("Manual assignment", "Study", None, 2, 100))
    save_task_mode(db, task_id, "progress")
    save_progress_preference(db, task_id, "manual", 40)
    step_id = add_step(db, task_id, "Optional checklist item", "checklist")
    set_checklist_done(db, step_id, True)
    task = list_tasks(db)[0]
    checks = [step for step in load_snapshot(db).steps if step.kind == "checklist"]
    pref = load_progress_preferences(db)[task_id]
    assert tracking_choice(task, load_task_modes(db)[task_id], pref, checks) == "Progress bar"
    assert progress_details(task, checks, preference=pref) == (40, "My progress estimate")
    assert 'aria-valuenow="40"' in progress_html(task, checks, preference=pref)
    # Adding/changing checklist items does not overwrite the selected percentage.
    set_checklist_done(db, step_id, False)
    assert load_progress_preferences(db)[task_id] == ProgressPreference("manual", 40)


def test_explicit_checklist_and_simple_task_are_distinct(tmp_path):
    db = tmp_path / "methods.db"
    checklist_id = create_quick_task(db, TaskDraft("Checklist project"))
    save_task_mode(db, checklist_id, "progress")
    save_progress_preference(db, checklist_id, "checklist")
    ids = [add_step(db, checklist_id, f"Step {i}", "checklist") for i in range(4)]
    set_checklist_done(db, ids[0], True)
    task = next(t for t in list_tasks(db) if t.id == checklist_id)
    items = [
        s for s in load_snapshot(db).steps if s.task_id == checklist_id and s.kind == "checklist"
    ]
    assert (
        tracking_choice(task, "progress", load_progress_preferences(db)[checklist_id], items)
        == "Subtasks"
    )
    assert progress_details(task, items, preference=ProgressPreference("checklist"))[0] == 25
    simple_id = create_quick_task(db, TaskDraft("Laundry"), schedule=False)
    save_task_mode(db, simple_id, "simple")
    simple = next(t for t in list_tasks(db) if t.id == simple_id)
    assert tracking_choice(simple, load_task_modes(db)[simple_id], None, ()) == "Simple to-do"


def test_categories_show_requested_defaults_without_dropping_old_records(tmp_path):
    db = tmp_path / "category.db"
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
    custom = create_category(db, "Volunteering")
    options = list_categories(db)
    assert options[:8] == DEFAULT_CATEGORIES
    assert options[8:] == (custom,)
    assert "University" not in options and "Work" not in options
    colors = category_colors(db)
    assert "Home" in colors and "University" in colors and "Work" in colors


def test_low_energy_may_split_existing_blocks_into_10_minute_pieces():
    slot = Slot(1, DAY, 540, 568)  # 28 minutes => 14 + 14
    result = divide_slot(slot, 25, minimum=10)
    assert [item.minutes for item in result] == [14, 14]
    assert sum(item.minutes for item in result) == 28
    assert all(item.minutes >= 10 for item in result)
    # The general divider retains the stricter 20-minute rule.
    assert divide_slot(slot, 25) == (slot,)


def test_low_energy_adapts_separate_windows_without_moving_lectures(tmp_path):
    db = tmp_path / "energy.db"
    create_quick_task(db, TaskDraft("Study", "Study", date(2026, 11, 27), 3, 80))
    add_window(db, DAY, 9 * 60, 10 * 60)
    add_window(db, DAY, 14 * 60, 15 * 60)
    add_fixed_event(db, "Lecture", DAY, 11 * 60, 12 * 60, "Lecture")
    snap = load_snapshot(db)
    step_id = snap.steps[0].id
    old = (Slot(step_id, DAY, 540, 580), Slot(step_id, DAY, 840, 880))
    accept_revision(db, proposal_from_slots(snap, NOW, old), NOW)
    snap = load_snapshot(db)
    preview = energy_proposal(snap, NOW, "Low energy", DAY)
    validate_revision(snap, preview, NOW)
    assert sum(slot.minutes for slot in preview.slots) == 80
    assert len(preview.slots) == 4
    assert all(10 <= slot.minutes <= 25 for slot in preview.slots)
    assert preview.added_or_changed > 0
    assert load_snapshot(db) == snap  # preview remains read-only
    accept_revision(db, preview, NOW)
    assert sum(session.end - session.start for session in load_snapshot(db).sessions) == 80


def test_low_energy_no_change_if_breaks_physically_cannot_fit(tmp_path):
    db = tmp_path / "limited.db"
    create_quick_task(db, TaskDraft("Study", "Study", date(2026, 11, 27), 3, 40))
    add_window(db, DAY, 540, 580)
    snap = load_snapshot(db)
    step_id = snap.steps[0].id
    accept_revision(db, proposal_from_slots(snap, NOW, (Slot(step_id, DAY, 540, 580),)), NOW)
    snap = load_snapshot(db)
    result = energy_proposal(snap, NOW, "Low energy", DAY)
    assert result.slots == (Slot(step_id, DAY, 540, 580),)
    assert sum(item.minutes for item in result.slots) == 40


def test_high_energy_can_merge_nearby_sessions_of_same_task(tmp_path):
    db = tmp_path / "high_energy.db"
    create_quick_task(db, TaskDraft("Deep revision", "Study", date(2026, 11, 27), 3, 60))
    add_window(db, DAY, 540, 630)
    snap = load_snapshot(db)
    step = snap.steps[0].id
    original = (Slot(step, DAY, 540, 570), Slot(step, DAY, 575, 605))
    accept_revision(db, proposal_from_slots(snap, NOW, original), NOW)
    snap = load_snapshot(db)
    result = energy_proposal(snap, NOW, "High energy", DAY)
    validate_revision(snap, result, NOW)
    assert result.slots == (Slot(step, DAY, 540, 600),)
    assert result.planned_minutes == 60
    assert load_snapshot(db) == snap
