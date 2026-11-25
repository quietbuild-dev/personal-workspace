"""New optional objective parameters do not bypass independent validation."""

from datetime import datetime

import pytest

from workspace.advanced_planner import PlannerSnapshot, StudyStep, TimeWindow, validate_revision
from workspace.deadline_guarantees import check_required_coverage
from workspace.optimizer import _score, optimize
from workspace.study_dna import StudyDNA

NOW = datetime(2026, 11, 25, 8)
DAY = NOW.date()


def snapshot():
    steps = (
        StudyStep(1, 1, "Mandatory", "Study", "timed", 60, 60, False, DAY, 2, False),
        StudyStep(2, 2, "Optional", "Study", "timed", 60, 60, False, DAY, 3, False),
    )
    return PlannerSnapshot(steps, (TimeWindow(1, DAY, 540, 600),), (), (), "x")


def test_invalid_profile_is_rejected():
    with pytest.raises(ValueError):
        optimize(snapshot(), NOW, dna="bad profile")


def test_coverage_constrained_comparison_keeps_required_work():
    pytest.importorskip("ortools")
    snap = snapshot()
    result = optimize(
        snap,
        NOW,
        goal="throughput",
        compact=True,
        require_task_ids=frozenset({1}),
        dna=StudyDNA("", "midday", "balanced", "batch", "open"),
        time_limit=5,
    )
    validate_revision(snap, result.revision, NOW)
    assert check_required_coverage(snap, result.revision, NOW, frozenset({1})).complete
    assert {s.step_id for s in result.revision.slots} == {1}


def test_score_rewards_preferred_focus_on_throughput_ties():
    from workspace.advanced_planner import Slot
    from workspace.optimizer import proposal_from_slots

    snap = snapshot()
    early = proposal_from_slots(snap, NOW, (Slot(1, DAY, 540, 600),))
    later = proposal_from_slots(snap, NOW, (Slot(1, DAY, 600, 660),))
    segments = [(DAY, 540, 600), (DAY, 600, 660)]
    dna = StudyDNA("", "midday", "balanced", "none", "open")
    assert _score(snap, later, NOW, "throughput", segments, 2, dna=dna) > _score(
        snap, early, NOW, "throughput", segments, 2, dna=dna
    )
