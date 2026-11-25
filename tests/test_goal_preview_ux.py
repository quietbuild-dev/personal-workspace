"""Goal selection UX: one initial preview, then switching goals needs no extra click."""

import importlib.util
import sys
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def test_goal_switch_refreshes_preview_without_writing_data():
    ui = MagicMock()
    ui.session_state = {}
    ui.expander.side_effect = lambda *_, **__: nullcontext()
    current = {"goal": "deadlines", "buttons": set()}
    ui.selectbox.side_effect = lambda *_, **__: current["goal"]
    ui.button.side_effect = lambda label, key=None, **_: key in current["buttons"]
    file = Path(__file__).resolve().parents[1] / "workspace/views/goal_preview.py"
    with patch.dict(sys.modules, {"streamlit": ui}):
        spec = importlib.util.spec_from_file_location("isolated_goal_preview_ux_test", file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

    now = datetime(2026, 11, 25, 9)
    snapshot = SimpleNamespace(fingerprint="unchanged")
    with (
        patch.object(
            module,
            "optimize",
            side_effect=lambda *_args, goal, **_kwargs: SimpleNamespace(
                goal=goal, revision=object(), message=""
            ),
        ) as optimizer,
        patch.object(module, "validate_revision"),
        patch.object(
            module,
            "schedule_metrics",
            return_value={
                "due_coverage_pct": 80,
                "high_priority_coverage_pct": 90,
                "moved_or_removed_sessions": 2,
            },
        ),
    ):
        result, goal = module.choose_goal_preview(snapshot, now, None)
        assert result is None and goal == "deadlines"
        assert optimizer.call_count == 0

        current["buttons"] = {"generate_goal_preview"}
        result, goal = module.choose_goal_preview(snapshot, now, None)
        assert result.goal == goal == "deadlines"
        assert optimizer.call_count == 1

        current["buttons"] = set()
        current["goal"] = "routine"
        result, goal = module.choose_goal_preview(snapshot, now, None)
        assert result.goal == goal == "routine"
        assert optimizer.call_count == 2

        module.choose_goal_preview(snapshot, now, None)
        assert optimizer.call_count == 2, "A cached plan must not be recalculated on rerun"
        assert ui.expander.call_count >= 1, "The comparison must be optional"
