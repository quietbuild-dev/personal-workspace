"""The workload chart must include accepted sessions and other calendar events."""

from datetime import date
from types import SimpleNamespace

from workspace.workload_summary import COLORS, workload_breakdown


def test_week_has_study_and_distinct_fixed_events():
    thu = date(2026, 11, 26)
    snapshot = SimpleNamespace(
        sessions=[
            SimpleNamespace(day=thu, status="planned", start=600, end=720),
            SimpleNamespace(day=thu, status="done", start=800, end=860),
        ],
        events=[
            SimpleNamespace(day=thu, kind="Lecture", start=480, end=540),
            SimpleNamespace(day=thu, kind="Exercise", start=1080, end=1140),
            SimpleNamespace(day=thu, kind="Appointment", start=900, end=930),
        ],
    )
    result = workload_breakdown(snapshot, thu)
    assert result[thu] == {"Study": 120, "Lecture": 60, "Social": 0, "Exercise": 60, "Personal": 30}
    assert COLORS["Study"] == "#BAA9D0"
    assert COLORS["Exercise"] == "#8AB9A6"
    assert len(result) == 7
