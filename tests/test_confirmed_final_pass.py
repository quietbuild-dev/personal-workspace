"""Regression checks for the fourteen explicitly approved final changes."""

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from workspace.advanced_planner import Slot, make_revision, validate_revision
from workspace.advanced_repository import (
    accept_revision,
    add_window,
    load_snapshot,
)
from workspace.energy_today import divide_slot, energy_proposal
from workspace.home_intelligence import daily_briefing
from workspace.life_planning import (
    accept_time_protection,
    preview_time_protection,
    undo_last_plan_with_protection,
)
from workspace.models import TaskDraft
from workspace.optimizer import proposal_from_slots
from workspace.quick_tasks import create_quick_task
from workspace.weekly_replay import completed_tasks_in_week

NOW = datetime(2026, 11, 26, 9)
FRIDAY = date(2026, 11, 27)
SATURDAY = date(2026, 11, 28)


def book(db, sessions):
    before = load_snapshot(db)
    proposal = proposal_from_slots(before, NOW, tuple(sessions))
    validate_revision(before, proposal, NOW)
    accept_revision(db, proposal, NOW)
    return load_snapshot(db)


def new_db(tmp_path):
    db = tmp_path / "scoped-final.db"
    task1 = create_quick_task(db, TaskDraft("Statistics", "University", SATURDAY, 3, 90))
    task2 = create_quick_task(db, TaskDraft("Algorithms", "University", SATURDAY, 2, 60))
    for day in (date(2026, 11, 26), FRIDAY, SATURDAY):
        add_window(db, day, 9 * 60, 20 * 60)
    snap = load_snapshot(db)
    ids = {s.task_id: s.id for s in snap.steps if s.kind == "timed"}
    return db, ids[task1], ids[task2]


def test_energy_cannot_create_extra_work_or_modify_other_days(tmp_path):
    db, stat, algo = new_db(tmp_path)
    snap = book(db, [Slot(stat, FRIDAY, 1020, 1110), Slot(algo, SATURDAY, 600, 660)])
    proposal = energy_proposal(snap, NOW, "Low energy", FRIDAY)
    assert load_snapshot(db) == snap  # preview is read only
    assert sum(s.minutes for s in proposal.slots) == 150
    assert all(s.minutes >= 20 for s in proposal.slots)
    assert {(s.step_id, s.day, s.start, s.end) for s in proposal.slots if s.day == SATURDAY} == {
        (algo, SATURDAY, 600, 660)
    }
    assert {s.step_id for s in proposal.slots} == {stat, algo}
    assert len([s for s in proposal.slots if s.day == FRIDAY]) == 4


def test_energy_refuses_unbooked_work(tmp_path):
    db, _, _ = new_db(tmp_path)
    with pytest.raises(ValueError, match="No booked study"):
        energy_proposal(load_snapshot(db), NOW, "Low energy", FRIDAY)


def test_division_has_no_new_under_twenty_minute_fragments():
    result = divide_slot(Slot(7, FRIDAY, 600, 691), 25)
    assert sum(s.minutes for s in result) == 91
    assert min(s.minutes for s in result) >= 20
    assert max(s.minutes for s in result) <= 25


def test_personal_time_relocates_only_conflicts_with_atomic_undo(tmp_path):
    db, stat, algo = new_db(tmp_path)
    before = book(db, [Slot(stat, FRIDAY, 1020, 1110), Slot(algo, SATURDAY, 600, 660)])
    preview = preview_time_protection(before, NOW, FRIDAY, 1020, 1140)
    assert preview.feasible, preview.explanation
    assert load_snapshot(db) == before
    kept = Slot(algo, SATURDAY, 600, 660)
    assert kept in preview.revision.slots
    moved = [s for s in preview.revision.slots if s.step_id == stat]
    assert sum(s.minutes for s in moved) == 90
    assert all(s.minutes >= 20 for s in moved)
    assert all(not (s.day == FRIDAY and s.start < 1140 and s.end > 1020) for s in moved)
    accept_time_protection(db, preview, NOW)
    assert undo_last_plan_with_protection(db, NOW) >= 1
    assert load_snapshot(db) == before


def test_weekly_replay_counts_real_task_completion_not_booked_study():
    monday, sunday = date(2026, 11, 23), date(2026, 11, 29)
    tasks = [
        SimpleNamespace(status="completed", completed_at=datetime(2026, 11, 26, 16)),
        SimpleNamespace(status="completed", completed_at=datetime(2026, 11, 16, 12)),
        SimpleNamespace(status="pending", completed_at=None),
    ]
    assert completed_tasks_in_week(tasks, monday, sunday) == 1
    assert completed_tasks_in_week(tasks, date(2026, 11, 30), date(2026, 12, 6)) == 0


def test_briefing_handles_zero_study_and_week_boundary():
    task = SimpleNamespace(
        status="pending", deadline=FRIDAY, priority=2, id=1, title="Finish SWE"
    )
    old = SimpleNamespace(
        status="pending", deadline=date(2026, 11, 24), priority=2,
        id=2, title="Overdue task",
    )
    snapshot = SimpleNamespace(events=(), sessions=(), steps=())
    result = daily_briefing((task, old), snapshot, NOW)
    assert "No study planned" not in result.text
    assert "1 deadline due by Sunday" in result.text
    assert "overdue" not in result.text.lower()
    assert "0m" not in result.text


def test_schedule_check_no_longer_mutates_rendered_date_widget():
    source = (Path(__file__).resolve().parents[1] / "workspace/views/plan_doctor.py")
    assert 'st.session_state["calendar_browse_date"] =' not in source.read_text(encoding="utf-8")


def test_general_planner_leaves_tiny_remainder_unbooked(tmp_path):
    db = tmp_path / "tiny.db"
    create_quick_task(db, TaskDraft("Tiny final step", "University", FRIDAY, 2, 15))
    add_window(db, FRIDAY, 9 * 60, 12 * 60)
    snapshot = load_snapshot(db)
    proposal = make_revision(snapshot, NOW)
    assert not proposal.slots
    assert sum(item.minutes for item in proposal.shortfalls) == 15


def test_general_planner_never_adds_a_short_new_session(tmp_path):
    db = tmp_path / "no-fragments.db"
    create_quick_task(db, TaskDraft("Finish notes", "University", FRIDAY, 2, 25))
    add_window(db, FRIDAY, 9 * 60, 9 * 60 + 20)
    snapshot = load_snapshot(db)
    proposal = make_revision(snapshot, NOW)
    assert all(s.minutes >= 20 for s in proposal.slots)
    assert sum(s.minutes for s in proposal.slots) == 20
    assert sum(s.minutes for s in proposal.shortfalls) == 5
