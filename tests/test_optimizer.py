"""Solver correctness checked against independent calendar validation."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from workspace.advanced_planner import (
    DayBudget,
    FixedEvent,
    PlannerSnapshot,
    SavedSession,
    StudyStep,
    TimeWindow,
    make_revision,
    validate_revision,
)
from workspace.optimizer import GOALS, optimize

NOW = datetime(2026, 11, 16, 8)
DAY = NOW.date()


def step(i=1, minutes=60, priority=2, deadline=DAY, due=None):
    return StudyStep(
        i, i, f"Task {i}", "Study", "timed", minutes, minutes, False, deadline, priority, False, due
    )


def snapshot(steps=None, windows=None, **kwargs):
    return PlannerSnapshot(
        tuple(steps or [step()]),
        tuple(windows or [TimeWindow(1, DAY, 540, 660)]),
        kwargs.pop("events", ()),
        kwargs.pop("sessions", ()),
        "synthetic",
        **kwargs,
    )


@pytest.mark.parametrize("goal", GOALS)
def test_profiles_are_valid_partial_plans(goal):
    snap = snapshot(
        [step(1, 160), step(2, 90, 3)],
        events=(FixedEvent(1, "Lecture", DAY, 570, 600),),
        budgets=(DayBudget(DAY, 75),),
    )
    result = optimize(snap, NOW, goal=goal)
    assert result.engine == "cp-sat", result.message
    assert result.status == "OPTIMAL"
    validate_revision(snap, result.revision, NOW)
    assert result.revision.planned_minutes == 75
    assert sum(s.minutes for s in result.revision.shortfalls) == 175


def test_exact_deadline_beats_date_only_greedy_sort():
    snap = snapshot([step(1, 60, due=660), step(2, 60, due=600)])
    greedy = make_revision(snap, NOW, preserve_existing=False)
    result = optimize(snap, NOW)
    assert greedy.planned_minutes == 60
    assert result.revision.planned_minutes == 120
    validate_revision(snap, result.revision, NOW)


def test_exact_off_grid_accepted_block_is_retained():
    snap = snapshot(sessions=(SavedSession(1, 1, DAY, 554, 614, "planned", 0),))
    result = optimize(snap, NOW, goal="routine")
    assert result.revision.unchanged == 1
    assert result.revision.slots[0].start == 554


def test_completed_history_blocks_time_and_consumes_budget():
    snap = snapshot(
        budgets=(DayBudget(DAY, 90),), sessions=(SavedSession(1, 1, DAY, 540, 600, "done", 60),)
    )
    result = optimize(snap, NOW)
    assert result.revision.planned_minutes == 30
    assert all(s.end <= 540 or s.start >= 600 for s in result.revision.slots)
    validate_revision(snap, result.revision, NOW)


def test_unavailable_solver_falls_back_without_optimal_claim():
    snap = snapshot()
    with patch("workspace.optimizer._cp_module", side_effect=ImportError):
        result = optimize(snap, NOW)
    assert result.engine == "greedy"
    assert result.status == "UNAVAILABLE"
    validate_revision(snap, result.revision, NOW)


def test_near_zero_time_limit_is_safe():
    snap = snapshot()
    result = optimize(snap, NOW, time_limit=0.000001)
    assert result.status != "OPTIMAL"
    validate_revision(snap, result.revision, NOW)


def test_past_time_and_overdue_work_are_not_scheduled():
    snap = snapshot([step(1, 60, deadline=DAY - timedelta(days=1)), step(2, 91)])
    now = NOW.replace(hour=10, minute=1, second=1)
    result = optimize(snap, now)
    assert result.revision.planned_minutes == 58
    assert all(s.step_id == 2 and s.start >= 602 for s in result.revision.slots)


def test_no_capacity_is_valid_empty_optimum():
    snap = snapshot(budgets=(DayBudget(DAY, 0),))
    result = optimize(snap, NOW)
    assert result.status == "OPTIMAL"
    assert result.revision.slots == ()


def test_invalid_inputs_are_rejected():
    with pytest.raises(ValueError):
        optimize(snapshot(), NOW.replace(tzinfo=timezone.utc))
    with pytest.raises(ValueError):
        optimize(snapshot(), NOW, goal="magic")
    with pytest.raises(ValueError):
        optimize(snapshot([replace(step(), remaining_minutes=61)]), NOW)


def test_reschedule_target_cannot_return_to_its_old_time():
    snap = snapshot(sessions=(SavedSession(1, 1, DAY, 540, 600, "planned", 0),))
    result = optimize(snap, NOW, goal="routine", reschedule_session_id=1)
    assert result.revision.slots[0].start >= 600


def test_deadlines_and_importance_choose_different_work():
    snap = snapshot(
        [step(1, 60, 1), step(2, 60, 3, DAY + timedelta(days=2))], [TimeWindow(1, DAY, 540, 600)]
    )
    deadline = optimize(snap, NOW, goal="deadlines").revision
    important = optimize(snap, NOW, goal="important").revision
    assert {s.step_id for s in deadline.slots} == {1}
    assert {s.step_id for s in important.slots} == {2}
    for proposal in (deadline, important):
        validate_revision(snap, proposal, NOW)


def test_routine_can_trade_throughput_for_preservation():
    snap = snapshot(
        [step(1, 60, due=660), step(2, 60, due=600)],
        sessions=(SavedSession(1, 1, DAY, 540, 600, "planned", 0),),
    )
    routine = optimize(snap, NOW, goal="routine").revision
    throughput = optimize(snap, NOW, goal="throughput").revision
    assert routine.unchanged == 1 and routine.planned_minutes == 60
    assert throughput.unchanged == 0 and throughput.planned_minutes == 120


def test_balance_spreads_equal_total_work():
    from workspace.planning_insights import schedule_metrics

    snap = snapshot(
        [step(1, 120, deadline=DAY + timedelta(days=1))],
        [TimeWindow(1, DAY, 540, 660), TimeWindow(2, DAY + timedelta(days=1), 540, 660)],
    )
    throughput = optimize(snap, NOW, goal="throughput").revision
    balanced = optimize(snap, NOW, goal="balance").revision
    assert throughput.planned_minutes == balanced.planned_minutes == 120
    assert schedule_metrics(snap, throughput, NOW)["peak_day_minutes"] == 120
    assert schedule_metrics(snap, balanced, NOW)["peak_day_minutes"] == 60


@pytest.mark.parametrize("status_name", ["INFEASIBLE", "MODEL_INVALID", "UNKNOWN"])
def test_solver_without_incumbent_returns_labelled_valid_fallback(status_name):
    from ortools.sat.python import cp_model

    snap = snapshot()
    with patch.object(cp_model.CpSolver, "solve", return_value=getattr(cp_model, status_name)):
        result = optimize(snap, NOW)
    assert result.status == status_name
    assert result.engine == "greedy"
    validate_revision(snap, result.revision, NOW)


def test_feasible_solver_result_is_not_called_optimal():
    from ortools.sat.python import cp_model

    solve = cp_model.CpSolver.solve

    def feasible(self, model):
        solve(self, model)
        return cp_model.FEASIBLE

    with patch.object(cp_model.CpSolver, "solve", feasible):
        result = optimize(snapshot(), NOW)
    assert result.status == "FEASIBLE"
    assert result.proven_levels == 0


def test_unknown_secondary_search_keeps_previous_incumbent():
    from ortools.sat.python import cp_model

    solve = cp_model.CpSolver.solve
    calls = 0

    def limited(self, model):
        nonlocal calls
        calls += 1
        return solve(self, model) if calls == 1 else cp_model.UNKNOWN

    with patch.object(cp_model.CpSolver, "solve", limited):
        result = optimize(snapshot(), NOW)
    assert result.status == "FEASIBLE"
    assert result.proven_levels == 1
    assert result.revision.planned_minutes == 60


def test_short_search_never_reduces_throughput_below_its_baseline():
    from scripts.evaluate_optimizer import NOW as BENCH_NOW
    from scripts.evaluate_optimizer import scenarios

    for name, _, snap in scenarios():
        if name not in ("overloaded", "busy_commitments", "fragmented"):
            continue
        baseline = make_revision(snap, BENCH_NOW, preserve_existing=False)
        result = optimize(snap, BENCH_NOW, goal="throughput", time_limit=0.02)
        assert result.revision.planned_minutes >= baseline.planned_minutes


def test_independent_audit_detects_forged_overlaps():
    from scripts.evaluate_optimizer import audit
    from workspace.advanced_planner import Slot
    from workspace.optimizer import proposal_from_slots

    snap = snapshot([step(1), step(2)])
    bad = proposal_from_slots(snap, NOW, [Slot(1, DAY, 540, 600), Slot(2, DAY, 540, 600)])
    assert "overlap" in audit(snap, bad, NOW)
