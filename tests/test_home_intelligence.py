"""Deterministic tests for the two read-only dashboard features."""

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from workspace.advanced_planner import (
    DayBudget,
    FixedEvent,
    PlannerSnapshot,
    SavedSession,
    StudyStep,
    TimeWindow,
)
from workspace.home_intelligence import (
    available_study_minutes,
    daily_briefing,
    deadline_runway,
    display_duration,
)
from workspace.models import Task

NOW = datetime(2026, 11, 25, 9, 0)
TODAY = NOW.date()
TOMORROW = date(2026, 11, 26)
FRIDAY = date(2026, 11, 27)


def task(task_id=1, name="Statistics problem set", due=FRIDAY, remaining=240):
    return Task(
        task_id,
        name,
        "University",
        due,
        3,
        360,
        remaining,
        "pending",
        datetime(2026, 11, 20, tzinfo=timezone.utc),
        None,
    )


def step(task_id=1, remaining=240, deadline_minute=None):
    return StudyStep(
        11,
        task_id,
        "Statistics problem set",
        "Focus time",
        "timed",
        360,
        remaining,
        False,
        FRIDAY,
        3,
        False,
        deadline_minute,
    )


def snapshot(*, steps=(), windows=(), budgets=(), events=(), sessions=()):
    return PlannerSnapshot(
        tuple(steps), tuple(windows), tuple(events), tuple(sessions), "test-fingerprint",
        tuple(budgets),
    )


def test_daily_brief_uses_real_saved_bookings_and_deadline():
    saved = snapshot(
        steps=(step(),),
        events=(
            FixedEvent(1, "Statistics lecture", TODAY, 10 * 60, 11 * 60, "Lecture"),
            FixedEvent(2, "Social plans", TODAY, 18 * 60, 19 * 60, "Social"),
        ),
        sessions=(SavedSession(1, 11, TODAY, 14 * 60, 16 * 60, "planned", 0),),
    )
    result = daily_briefing((task(),), saved, NOW)
    assert "1 lecture" in result.text
    assert "2h of study planned" in result.text
    assert "1 approaching" in result.text
    assert [item[3] for item in result.agenda] == ["Lecture", "Study", "Social"]
    assert "Statistics problem set" in result.upcoming[0]


def test_daily_briefing_no_appointments_has_honest_empty_agenda():
    result = daily_briefing((task(due=date(2027, 1, 1)),), snapshot(), NOW)
    assert result.agenda == ()
    assert "0 lectures" in result.text
    assert "no deadlines" in result.text


def test_runway_progress_is_recorded_work_not_planned_blocks():
    saved = snapshot(
        steps=(step(),),
        windows=(TimeWindow(1, TOMORROW, 8 * 60, 13 * 60),),
        sessions=(SavedSession(1, 11, TOMORROW, 9 * 60, 11 * 60, "planned", 0),),
    )
    item = deadline_runway((task(),), saved, NOW)[0]
    assert item.done_percent == 33  # 2h actually completed, not the 2h future block
    assert item.remaining_minutes == 240
    assert item.reserved_minutes == 120
    assert item.needs_slot_minutes == 120
    assert item.open_capacity_minutes == 180


def test_overlapping_windows_and_fixed_events_are_not_double_counted():
    saved = snapshot(
        windows=(
            TimeWindow(1, TOMORROW, 8 * 60, 12 * 60),
            TimeWindow(2, TOMORROW, 10 * 60, 14 * 60),
        ),
        events=(
            FixedEvent(1, "Lecture", TOMORROW, 9 * 60, 11 * 60, "Lecture"),
            FixedEvent(2, "Meeting", TOMORROW, 10 * 60, 12 * 60, "Personal"),
        ),
    )
    # Union 08:00-14:00 = 6h; events union 09:00-12:00 = 3h.
    assert available_study_minutes(saved, NOW, TOMORROW) == 180


def test_budget_caps_free_capacity_after_done_and_planned_time():
    saved = snapshot(
        budgets=(DayBudget(TOMORROW, 180),),
        sessions=(
            SavedSession(1, 11, TOMORROW, 9 * 60, 10 * 60, "planned", 0),
            SavedSession(2, 11, TOMORROW, 10 * 60, 11 * 60, "done", 30),
        ),
    )
    # 180-min budget - 60 planned - 30 actually done = 90 min.
    assert available_study_minutes(saved, NOW, TOMORROW) == 90


def test_deadline_clock_and_current_clock_limit_same_day_capacity():
    saved = snapshot(windows=(TimeWindow(1, TODAY, 7 * 60, 18 * 60),))
    assert available_study_minutes(saved, NOW, TODAY, 11 * 60) == 120
    assert available_study_minutes(saved, NOW, TODAY, 8 * 60) == 0


def test_no_study_hours_configured_is_not_misrepresented_as_a_guarantee():
    row = deadline_runway((task(),), snapshot(steps=(step(),)), NOW)[0]
    assert not row.capacity_configured
    assert row.open_capacity_minutes == 0
    assert row.needs_slot_minutes == 240


def test_overdue_work_gets_zero_future_capacity():
    row = deadline_runway(
        (task(due=date(2026, 11, 24)),),
        snapshot(windows=(TimeWindow(1, TOMORROW, 8 * 60, 12 * 60),)),
        NOW,
    )[0]
    assert row.days_left == -1
    assert row.open_capacity_minutes == 0


def test_same_shared_capacity_appears_on_multiple_tasks_without_claiming_both_fit():
    saved = snapshot(windows=(TimeWindow(1, TOMORROW, 10 * 60, 12 * 60),))
    rows = deadline_runway((task(1), task(2, "SWE report")), saved, NOW)
    assert len(rows) == 2
    assert rows[0].open_capacity_minutes == rows[1].open_capacity_minutes == 120


def test_legacy_unscheduled_task_is_not_labeled_scheduled_study():
    row = deadline_runway((task(),), snapshot(), NOW)[0]
    assert not row.plannable
    assert row.reserved_minutes == 0


def test_horizon_excludes_far_future_deadlines_and_formats_minutes():
    rows = deadline_runway((task(due=date(2027, 2, 1)),), snapshot(), NOW)
    assert rows == ()
    assert display_duration(90) == "1h 30m"


def test_installer_only_adds_small_calls_and_is_idempotent(tmp_path):
    from scripts.install_home_intelligence import install

    root = Path(tmp_path)
    page = root / "workspace/views/home.py"
    page.parent.mkdir(parents=True)
    page.write_text(
        "from workspace.views.settings import render_form\n"
        "    upcoming = sum(\n"
        "    st.markdown(_weekly_workload(overview, now.date()), unsafe_allow_html=True)\n",
        encoding="utf-8",
    )
    (root / "workspace/home_intelligence.py").touch()
    (root / "workspace/views/home_briefing.py").touch()
    assert install(root) is True
    installed = page.read_text(encoding="utf-8")
    assert installed.count("render_daily_briefing(overview, now)") == 1
    assert installed.count("render_deadline_runway(overview, now)") == 1
    assert install(root) is False
    assert page.read_text(encoding="utf-8") == installed


def test_installer_refuses_unknown_home_without_modification(tmp_path):
    from scripts.install_home_intelligence import install

    root = Path(tmp_path)
    page = root / "workspace/views/home.py"
    page.parent.mkdir(parents=True)
    page.write_text("# unknown version\n", encoding="utf-8")
    (root / "workspace/home_intelligence.py").touch()
    (root / "workspace/views/home_briefing.py").touch()
    with pytest.raises(ValueError, match="Unrecognized Home version"):
        install(root)
    assert page.read_text(encoding="utf-8") == "# unknown version\n"
