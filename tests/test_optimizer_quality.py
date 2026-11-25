"""The optimizer's third objective should prefer nearby, usable blocks on ties."""

from datetime import datetime, timedelta

from workspace.advanced_planner import PlannerSnapshot, SavedSession, Slot, StudyStep
from workspace.optimizer import _score, proposal_from_slots

NOW = datetime(2026, 11, 25, 9)
DAY = NOW.date()
STEP = StudyStep(
    1, 1, "Coursework", "Study", "timed", 60, 60, False, DAY + timedelta(days=2), 2, False
)


def test_routine_tiebreak_prefers_nearby_move():
    snapshot = PlannerSnapshot(
        (STEP,), (), (), (SavedSession(1, 1, DAY, 600, 660, "planned", 0),), "x"
    )
    nearby = proposal_from_slots(snapshot, NOW, (Slot(1, DAY, 630, 690),))
    later = proposal_from_slots(snapshot, NOW, (Slot(1, DAY + timedelta(days=1), 630, 690),))
    segments = [(DAY, 600, 720), (DAY + timedelta(days=1), 600, 720)]
    assert _score(snapshot, nearby, NOW, "routine", segments, 2) > _score(
        snapshot, later, NOW, "routine", segments, 2
    )


def test_throughput_tiebreak_prefers_fewer_tiny_blocks():
    snapshot = PlannerSnapshot((STEP,), (), (), (), "x")
    small = proposal_from_slots(snapshot, NOW, (Slot(1, DAY, 600, 620), Slot(1, DAY, 650, 690)))
    useful = proposal_from_slots(snapshot, NOW, (Slot(1, DAY, 600, 630), Slot(1, DAY, 650, 680)))
    segments = [(DAY, 600, 630), (DAY, 650, 700)]
    assert _score(snapshot, useful, NOW, "throughput", segments, 2) > _score(
        snapshot, small, NOW, "throughput", segments, 2
    )
