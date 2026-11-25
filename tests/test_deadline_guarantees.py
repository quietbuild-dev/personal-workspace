"""Incomplete required schedules are never labelled deadline-complete."""

from datetime import datetime, timedelta

from workspace.advanced_planner import PlannerSnapshot, Slot, StudyStep
from workspace.deadline_guarantees import check_required_coverage
from workspace.optimizer import proposal_from_slots

NOW = datetime(2026, 11, 25, 8, 0)
DAY = NOW.date()


def step(i, n, deadline):
    return StudyStep(i, i, f"Course {i}", "Focus time", "timed", n, n, False, deadline, 2, False)


def test_only_required_work_due_this_week_must_be_covered():
    snap = PlannerSnapshot(
        (
            step(1, 60, DAY + timedelta(days=1)),
            step(2, 30, DAY + timedelta(days=2)),
            step(3, 45, DAY + timedelta(days=9)),
        ),
        (),
        (),
        (),
        "x",
    )
    proposal = proposal_from_slots(snap, NOW, (Slot(1, DAY, 540, 600),))
    complete = check_required_coverage(snap, proposal, NOW, frozenset({1}))
    assert complete.complete
    assert complete.required_minutes == 60
    partial = check_required_coverage(snap, proposal, NOW, frozenset({1, 2}))
    assert not partial.complete
    assert partial.outstanding_minutes == 30
    assert partial.tasks_short == ("Course 2",)


def test_empty_required_set_does_not_invent_deadline_risk():
    snap = PlannerSnapshot((step(1, 30, DAY),), (), (), (), "x")
    proposal = proposal_from_slots(snap, NOW, ())
    assert check_required_coverage(snap, proposal, NOW, frozenset()).complete
