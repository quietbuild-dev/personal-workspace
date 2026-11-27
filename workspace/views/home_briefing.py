"""Two compact, read-only Home panels: daily briefing and deadline runway."""

from datetime import datetime
from html import escape

import streamlit as st

from workspace.home_intelligence import daily_briefing, deadline_runway, display_duration
from workspace.task_modes import is_simple_task
from workspace.task_progress import ProgressPreference, progress_details


def render_daily_briefing(overview, now: datetime) -> None:
    summary = daily_briefing(overview.tasks, overview.advanced, now)
    # Only the two useful facts, stacked. No duplicate agenda or deadlines list.
    sentences = summary.text.split("\n\n")
    todays_facts = sentences[0].removeprefix("Today: ")
    with st.container(border=True, key="home_daily_briefing"):
        st.markdown("#### Your daily briefing")
        st.markdown(
            f'<div class="pw-briefing-facts">{escape(todays_facts)}</div>',
            unsafe_allow_html=True,
        )
        if len(sentences) > 1:
            st.markdown(
                f'<div class="pw-briefing-deadlines">{escape(sentences[1])}</div>',
                unsafe_allow_html=True,
            )
        if st.button("Start my day", key="daily_briefing_open_calendar", type="primary"):
            st.session_state["calendar_view"] = "Day"
            st.session_state["calendar_browse_date"] = now.date()
            st.switch_page("workspace/views/week.py")


def _runway_row(
    item,
    task,
    task_actions=None,
    checklist=(),
    preference=None,
    *,
    timed=(),
    simple=False,
) -> None:
    due = (
        "Today"
        if item.days_left == 0
        else "Tomorrow"
        if item.days_left == 1
        else f"{item.deadline:%d %b}"
    )
    label = due if simple else f"{due} · {display_duration(item.remaining_minutes)} left"
    ratio = max(0, min(100, item.done_percent))
    if task is not None and hasattr(task, "status"):
        ratio, _ = progress_details(
            task,
            checklist,
            timed_steps=timed,
            preference=preference,
        )
    progress_markup = (
        ""
        if simple
        else '<div class="pw-home-due-progress">'
        f"<span>{ratio}% complete</span>"
        '<div class="pw-home-due-track">'
        f'<i style="width:{ratio}%"></i></div></div>'
    )
    st.markdown(
        '<div class="pw-home-due-row">'
        '<div class="pw-home-due-line">'
        f"<strong>{escape(item.title)}</strong>"
        f"<span>{escape(label)}</span>"
        "</div>"
        f"{progress_markup}</div>",
        unsafe_allow_html=True,
    )
    if task_actions is not None and task is not None:
        task_actions(task)
    if (
        item.plannable
        and item.capacity_configured
        and (item.needs_slot_minutes > item.open_capacity_minutes)
    ):
        st.caption("More time may be needed before this deadline.")


def render_deadline_runway(
    overview,
    now: datetime,
    *,
    task_actions=None,
    progress_preferences=None,
    task_modes=None,
    priority_labels=None,
) -> None:
    with st.container(border=True, key="home_due_next"):
        st.markdown("#### What's due next")
        horizon = (
            st.segmented_control(
                "Upcoming deadlines",
                [7, 14, 30],
                default=7,
                format_func=lambda days: f"{days} days",
                key="due_next_days",
                label_visibility="collapsed",
            )
            or 7
        )
        items = deadline_runway(
            overview.tasks,
            overview.advanced,
            now,
            days_ahead=horizon,
            max_items=100,
        )
        if not items:
            st.caption(f"No upcoming deadlines in the next {horizon} days.")
            return
        tasks_by_id = {task.id: task for task in overview.tasks}
        steps_by_task = {}
        timed_by_task = {}
        if getattr(overview, "advanced", None) is not None:
            for step in overview.advanced.steps:
                if step.kind == "checklist":
                    steps_by_task.setdefault(step.task_id, []).append(step)
                elif step.kind == "timed":
                    timed_by_task.setdefault(step.task_id, []).append(step)
        prefs = progress_preferences or {}
        expanded = st.session_state.get("home_all_deadlines", False)
        visible = items if expanded else items[:3]
        for item in visible:
            priority_task = tasks_by_id.get(item.task_id)
            if priority_labels and priority_task is not None:
                priority_name = next(
                    (name for name, rank in priority_labels.items()
                     if rank == priority_task.priority),
                    str(priority_task.priority),
                )
                st.caption(f"{priority_name} priority")
            _runway_row(
                item,
                tasks_by_id.get(item.task_id),
                task_actions,
                steps_by_task.get(item.task_id, ()),
                prefs.get(item.task_id, ProgressPreference()),
                timed=timed_by_task.get(item.task_id, ()),
                simple=(
                    tasks_by_id.get(item.task_id) is not None
                    and (
                        (task_modes or {}).get(item.task_id) == "simple"
                        or (
                            overview.advanced is not None
                            and is_simple_task(
                                tasks_by_id[item.task_id],
                                overview.advanced.steps,
                                task_modes or {},
                            )
                        )
                    )
                ),
            )
        if len(items) > 3:
            label = "Show fewer deadlines" if expanded else f"Show {len(items) - 3} more deadlines"
            if st.button(label, key="home_toggle_deadlines"):
                st.session_state["home_all_deadlines"] = not expanded
                st.rerun()
        st.page_link("workspace/views/task_board.py", label="All tasks")
