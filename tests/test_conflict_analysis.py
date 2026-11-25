from dataclasses import replace

from tests.test_optimizer import DAY, NOW, snapshot, step
from workspace.advanced_planner import DayBudget, DayPreference, FixedEvent, TaskDependency
from workspace.conflict_analysis import analyze_conflicts
from workspace.optimizer import optimize


def test_capacity_is_clipped_to_deadline_events_and_daily_limit():
    snap = snapshot(
        [step(1, 240, due=660)],
        events=(FixedEvent(1, "Class", DAY, 570, 600),),
        budgets=(DayBudget(DAY, 60),),
        preferences=(DayPreference(DAY, 540, 720),),
    )
    proposal = optimize(snap, NOW).revision
    conflict = analyze_conflicts(snap, proposal, NOW)[0]
    assert conflict.capacity_upper_bound == 60
    assert conflict.commitments_removed_minutes == 30
    assert conflict.budget_removed_minutes == 30
    assert "at least 180 min" in conflict.explanation
    assert "at 11:00" in conflict.explanation
    assert "excludes 30 min" in conflict.suggestions[0]


def test_shared_capacity_is_not_described_as_individual_infeasibility():
    snap = snapshot([step(1, 90), step(2, 90)])
    conflicts = analyze_conflicts(snap, optimize(snap, NOW).revision, NOW)
    assert conflicts
    assert all(c.capacity_upper_bound == 120 for c in conflicts)
    assert all("capacity alone is short" not in c.explanation for c in conflicts)


def test_dependency_explanation_mentions_unchecked_work():
    checklist = replace(
        step(3), task_id=1, kind="checklist", remaining_minutes=0, estimate_minutes=0
    )
    snap = snapshot([step(1), step(2), checklist], dependencies=(TaskDependency(2, 1),))
    conflicts = analyze_conflicts(snap, optimize(snap, NOW).revision, NOW)
    child = next(c for c in conflicts if c.task_id == 2)
    assert "unchecked checklist" in child.explanation


def test_extension_suggestion_is_capped_by_spare_budget():
    snap = snapshot(
        [step(1, 180)], budgets=(DayBudget(DAY, 90),), preferences=(DayPreference(DAY, 540, 600),)
    )
    conflict = analyze_conflicts(snap, optimize(snap, NOW).revision, NOW)[0]
    assert conflict.capacity_upper_bound == 60
    assert any("30 additional min" in s for s in conflict.suggestions)
