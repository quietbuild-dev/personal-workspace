"""Home-only layout regression checks: no navigation or data-model changes."""

from contextlib import nullcontext
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from workspace.views import home, home_briefing, weekly_replay

NOW = datetime(2026, 11, 27, 9)


def _fake_ui():
    st = MagicMock()
    st.container.side_effect = lambda **_: nullcontext()
    st.expander.side_effect = lambda *_, **__: nullcontext()
    st.columns.side_effect = lambda n, **_: [st] * (n if isinstance(n, int) else len(n))
    st.session_state = {}
    st.segmented_control.return_value = 7
    st.button.return_value = False
    return st


def test_briefing_stacks_facts_and_omits_duplicate_calendar(monkeypatch):
    st = _fake_ui()
    monkeypatch.setattr(home_briefing, "st", st)
    summary = SimpleNamespace(
        text="Today: 2 lectures, 2h 15m of study planned, 6 other plans."
             "\n\n6 deadlines due by Sunday.",
        agenda=((600, 630, "Must not render", "Lecture"),),
    )
    monkeypatch.setattr(home_briefing, "daily_briefing", lambda *_: summary)
    home_briefing.render_daily_briefing(SimpleNamespace(tasks=(), advanced=None), NOW)
    rendered = "\n".join(str(call.args[0]) for call in st.markdown.call_args_list)
    assert "2 lectures" in rendered
    assert "6 deadlines due by Sunday" in rendered
    assert "Today's calendar" not in rendered
    assert "Must not render" not in rendered
    assert "Today: " not in rendered
    assert st.button.call_args.kwargs["key"] == "daily_briefing_open_calendar"


def test_start_my_day_still_opens_today_day_view(monkeypatch):
    st = _fake_ui()
    st.button.return_value = True
    monkeypatch.setattr(home_briefing, "st", st)
    monkeypatch.setattr(
        home_briefing, "daily_briefing",
        lambda *_: SimpleNamespace(text="Today: One lecture.", agenda=()),
    )
    home_briefing.render_daily_briefing(SimpleNamespace(tasks=(), advanced=None), NOW)
    assert st.session_state["calendar_view"] == "Day"
    assert st.session_state["calendar_browse_date"] == NOW.date()
    st.switch_page.assert_called_once_with("workspace/views/week.py")


def test_deadline_rows_are_left_aligned_actionable_and_expand_inline(monkeypatch):
    st = _fake_ui()
    monkeypatch.setattr(home_briefing, "st", st)
    items = [
        SimpleNamespace(
            task_id=i, title=f"Deadline {i}", days_left=i, deadline=date(2026, 11, 30),
            remaining_minutes=20, done_percent=0, plannable=False,
            capacity_configured=False, needs_slot_minutes=0, open_capacity_minutes=0,
        )
        for i in range(5)
    ]
    monkeypatch.setattr(home_briefing, "deadline_runway", lambda *_a, **_k: items)
    tasks = tuple(SimpleNamespace(id=i) for i in range(5))
    overview = SimpleNamespace(tasks=tasks, advanced=None)
    called = []
    home_briefing.render_deadline_runway(overview, NOW, task_actions=lambda t: called.append(t.id))
    assert called == [0, 1, 2]
    assert not st.expander.called
    assert st.container.call_args.kwargs["key"] == "home_due_next"
    assert any(c.args[0] == "Show 2 more deadlines" for c in st.button.call_args_list)

    st.session_state["home_all_deadlines"] = True
    st.markdown.reset_mock()
    called.clear()
    home_briefing.render_deadline_runway(overview, NOW, task_actions=lambda t: called.append(t.id))
    assert called == [0, 1, 2, 3, 4]
    shown = "\n".join(str(c.args[0]) for c in st.markdown.call_args_list)
    assert "Deadline 4" in shown and "pw-home-due-track" in shown
    assert not st.expander.called


def test_home_action_keys_do_not_collide_with_due_next(monkeypatch):
    st = _fake_ui()
    monkeypatch.setattr(home, "st", st)
    task = SimpleNamespace(id=42)
    home._home_task_actions(task, None)
    home._home_task_actions(task, None, key_prefix="home_due")
    keys = [call.kwargs["key"] for call in st.button.call_args_list]
    assert len(keys) == 6
    assert len(set(keys)) == 6
    assert "home_due_progress_42" in keys
    assert "home_done_42" in keys


def test_replay_renders_all_assignments_without_hidden_caveats(monkeypatch):
    st = _fake_ui()
    monkeypatch.setattr(weekly_replay, "st", st)
    subjects = tuple(
        SimpleNamespace(name=f"Assignment {i}", finished_minutes=30, booked_minutes=60)
        for i in range(6)
    )
    summary = SimpleNamespace(
        monday=date(2026, 11, 23), sunday=date(2026, 11, 29),
        days=(SimpleNamespace(day=date(2026, 11, 27), booked_minutes=60,
                              finished_minutes=30, missed_minutes=0),),
        subjects=subjects, booked_minutes=60, finished_minutes=30, pending_minutes=30,
    )
    monkeypatch.setattr(weekly_replay, "weekly_replay", lambda *_: summary)
    monkeypatch.setattr(weekly_replay, "list_tasks", lambda *_: ())
    monkeypatch.setattr(weekly_replay, "completed_tasks_in_week", lambda *_: 0)
    monkeypatch.setattr(weekly_replay, "_comparison_chart", lambda *_: (object(), [0]))
    weekly_replay.render_weekly_replay(SimpleNamespace(sessions=()), NOW, "dummy.db")
    shown = "\n".join(str(c.args[0]) for c in st.markdown.call_args_list)
    assert all(f"Assignment {i}" in shown for i in range(6))
    assert "still marked planned" not in shown
    assert "plan approvals" not in shown
    assert "Show 2 more assignments" not in shown
    assert st.expander.call_count == 1  # Replay itself, no nested assignment expander.


def test_completed_tasks_expand_without_a_nested_grey_panel(monkeypatch):
    st = _fake_ui()
    st.session_state["home_all_completed"] = True
    st.session_state["home_all_todos"] = True
    monkeypatch.setattr(home, "st", st)
    monkeypatch.setattr(home, "focus_tasks", lambda *_: ())
    done = [SimpleNamespace(id=i, title=f"Finished {i}") for i in range(5)]
    monkeypatch.setattr(home, "completed_today", lambda *_: done)
    todo = [
        SimpleNamespace(id=i, title=f"To-do {i}", category="Personal",
                        status="pending", deadline=None, priority=1)
        for i in range(10, 16)
    ]
    home._home_priorities(
        SimpleNamespace(tasks=todo, advanced=SimpleNamespace(steps=())), {}, NOW.date()
    )
    shown = "\n".join(str(call.args[0]) for call in st.markdown.call_args_list)
    assert "Finished 4" in shown
    assert "### To-do" in shown
    assert not st.expander.called
