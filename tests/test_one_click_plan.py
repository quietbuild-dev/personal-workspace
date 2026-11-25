"""Home/Calendar quick entry delegates to the original safe preview workflow."""

import importlib.util
import sys
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def test_one_click_flag_generates_preview_then_disappears():
    ui = MagicMock()
    ui.session_state = {"start_week_plan": True}
    ui.expander.side_effect = lambda *_, **__: nullcontext()
    ui.selectbox.return_value = "deadlines"
    ui.button.return_value = False
    file = Path(__file__).resolve().parents[1] / "workspace/views/goal_preview.py"
    with patch.dict(sys.modules, {"streamlit": ui}):
        spec = importlib.util.spec_from_file_location("isolated_one_click_goal", file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    snap = SimpleNamespace(fingerprint="unchanged")
    now = datetime(2026, 11, 25, 9)
    with (
        patch.object(
            module, "optimize", return_value=SimpleNamespace(revision=object(), message="")
        ) as solver,
        patch.object(module, "validate_revision"),
    ):
        proposal, goal = module.choose_goal_preview(snap, now, None)
        assert proposal is not None and goal == "deadlines"
        assert solver.call_count == 1
        assert "start_week_plan" not in ui.session_state
        module.choose_goal_preview(snap, now, None)
        assert solver.call_count == 1
