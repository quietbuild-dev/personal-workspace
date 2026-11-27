"""Ordinary goal comparison stays flexible; only A/B asks for strict coverage."""

import importlib.util
import sys
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from workspace.advanced_planner import PlannerSnapshot, Slot, StudyStep
from workspace.optimizer import proposal_from_slots

FILE = Path(__file__).resolve().parents[1] / "workspace/views/goal_preview.py"
NOW = datetime(2026, 11, 25, 8)


def test_goal_previews_do_not_require_unachievable_complete_coverage():
    day = NOW.date()
    snapshot = PlannerSnapshot(
        (
            StudyStep(
                1, 1, "Exam", "Focus", "timed", 120, 120, False, day + timedelta(days=1), 3, False
            ),
        ),
        (),
        (),
        (),
        "demo",
    )
    proposal = proposal_from_slots(snapshot, NOW, (Slot(1, day, 540, 600),))
    ui = MagicMock()
    ui.session_state = {}
    ui.expander.side_effect = lambda *_, **__: nullcontext()
    ui.selectbox.return_value = "deadlines"
    ui.button.side_effect = lambda label, **_: label in ("Preview schedule", "Compare goals")
    ui.radio.return_value = "Current goal"
    with patch.dict(sys.modules, {"streamlit": ui}):
        spec = importlib.util.spec_from_file_location("test_goal_constraints", FILE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

    calls = []

    def fake_optimize(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(revision=proposal, message="")

    with (
        patch.object(module, "optimize", side_effect=fake_optimize),
        patch.object(module, "validate_revision"),
    ):
        result, goal = module.choose_goal_preview(snapshot, NOW, None, must_ids=frozenset({1}))
    assert goal == "deadlines"
    assert result.revision == proposal
    assert len(calls) == 5
    assert all(call.get("require_task_ids") == frozenset() for call in calls)
