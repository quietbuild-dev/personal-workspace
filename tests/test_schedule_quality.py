from datetime import date

from workspace.advanced_planner import PlannerSnapshot, RevisionProposal, SavedSession, Slot
from workspace.schedule_quality import describe_goal_tradeoff, shift_distance_minutes

DAY = date(2026, 11, 25)


def test_shift_distance_matches_once_and_counts_days():
    snapshot = PlannerSnapshot((), (), (), (SavedSession(1, 1, DAY, 600, 660, "planned", 0),), "x")
    proposal = RevisionProposal(DAY, DAY, "x", (Slot(1, DAY, 615, 675),), (), 0, 1, 1, 0)
    assert shift_distance_minutes(snapshot, proposal) == 15


def test_tradeoff_is_clear_not_promotional():
    original = {
        "due_coverage_pct": 80,
        "high_priority_coverage_pct": 60,
        "moved_or_removed_sessions": 1,
    }
    alternative = {
        "due_coverage_pct": 90,
        "high_priority_coverage_pct": 75,
        "moved_or_removed_sessions": 3,
    }
    note = describe_goal_tradeoff(alternative, original)
    assert "15 points more priority coverage" in note
    assert "2 more existing blocks changed" in note
    assert "deadline coverage" in note
