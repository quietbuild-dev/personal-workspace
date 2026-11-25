"""A/B UI must not offer an incomplete required plan as a complete alternative."""

import importlib.util
import sys
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from workspace.advanced_planner import PlannerSnapshot, Slot, StudyStep
from workspace.optimizer import proposal_from_slots

NOW = datetime(2026, 11, 25, 8)
DAY = NOW.date()
FILE = Path(__file__).resolve().parents[1] / "workspace/views/goal_preview.py"


def _ui():
    ui = MagicMock()
    ui.session_state = {}
    ui.expander.side_effect = lambda *_, **__: nullcontext()
    ui.selectbox.return_value = "deadlines"
    ui.button.side_effect = lambda label, **_: label in ("Preview schedule", "Build both plans")
    ui.radio.return_value = "Plan B · Focus days"
    with patch.dict(sys.modules, {"streamlit": ui}):
        spec = importlib.util.spec_from_file_location("test_isolated_ab_ui", FILE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return ui, module


def test_two_complete_plans_can_be_chosen_without_saving():
    snap = PlannerSnapshot(
        (
            StudyStep(
                1, 1, "Exam", "Study", "timed", 60, 60, False, DAY + timedelta(days=1), 2, False
            ),
        ),
        (),
        (),
        (),
        "current",
    )
    steady = proposal_from_slots(snap, NOW, (Slot(1, DAY, 540, 600),))
    focused = proposal_from_slots(snap, NOW, (Slot(1, DAY, 600, 660),))
    ui, module = _ui()

    def fake_optimize(_snapshot, _now, *, goal, compact=False, **_kwargs):
        return SimpleNamespace(revision=focused if compact else steady, message="")

    with (
        patch.object(module, "optimize", side_effect=fake_optimize),
        patch.object(module, "validate_revision"),
    ):
        result, goal = module.choose_goal_preview(snap, NOW, None, must_ids=frozenset({1}))
    assert goal == "ab_focus"
    assert result.revision == focused
    ui.dataframe.assert_called()


def test_partial_plan_never_exposed_as_complete_option():
    snap = PlannerSnapshot(
        (StudyStep(1, 1, "Exam", "Study", "timed", 60, 60, False, DAY, 2, False),),
        (),
        (),
        (),
        "current",
    )
    complete = proposal_from_slots(snap, NOW, (Slot(1, DAY, 540, 600),))
    partial = proposal_from_slots(snap, NOW, (Slot(1, DAY, 540, 570),))
    ui, module = _ui()

    def fake_optimize(_snapshot, _now, *, goal, compact=False, **_kwargs):
        return SimpleNamespace(revision=partial if compact else complete, message="")

    with (
        patch.object(module, "optimize", side_effect=fake_optimize),
        patch.object(module, "validate_revision"),
    ):
        result, goal = module.choose_goal_preview(snap, NOW, None, must_ids=frozenset({1}))
    assert goal == "deadlines"
    assert result.revision == complete
    ui.warning.assert_called()
