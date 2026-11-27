"""The approved schedule chooser exposes one selected goal, not Plan A/B."""

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
    ui.button.side_effect = lambda label, **_: label == "Preview schedule"
    with patch.dict(sys.modules, {"streamlit": ui}):
        spec = importlib.util.spec_from_file_location("test_one_goal_ui", FILE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return ui, module


def test_single_goal_can_be_previewed_without_plan_a_b():
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
    suggested = proposal_from_slots(snap, NOW, (Slot(1, DAY, 540, 600),))
    ui, module = _ui()
    with (
        patch.object(
            module, "optimize", return_value=SimpleNamespace(revision=suggested, message="")
        ),
        patch.object(module, "validate_revision"),
    ):
        result, goal = module.choose_goal_preview(snap, NOW, None)
    assert goal == "deadlines"
    assert result.revision == suggested
    ui.radio.assert_not_called()
    assert "Plan A" not in FILE.read_text(encoding="utf-8")


def test_partial_plan_is_preview_not_automatic_approval():
    snap = PlannerSnapshot(
        (StudyStep(1, 1, "Exam", "Study", "timed", 60, 60, False, DAY, 2, False),),
        (),
        (),
        (),
        "current",
    )
    partial = proposal_from_slots(snap, NOW, (Slot(1, DAY, 540, 570),))
    _, module = _ui()
    with (
        patch.object(
            module, "optimize", return_value=SimpleNamespace(revision=partial, message="")
        ),
        patch.object(module, "validate_revision"),
    ):
        result, goal = module.choose_goal_preview(snap, NOW, None)
    assert goal == "deadlines"
    assert result.revision == partial
    assert "accept_revision" not in FILE.read_text(encoding="utf-8")
