"""Live dashboard derived from the same saved tasks and planner rules."""

import logging
import sqlite3
from datetime import date, datetime

import plotly.graph_objects as go
import streamlit as st

from workspace.advanced_planner import (
    accepted_conflicts,
    format_time,
    hourly_workload,
    make_revision,
)
from workspace.metrics import format_minutes
from workspace.overview import load_overview
from workspace.repository import DEFAULT_DB_PATH

st.title("Your week, at a glance")
st.caption("Make room for what matters.")
today = date.today()
try:
    overview = load_overview(DEFAULT_DB_PATH, today)
except (sqlite3.Error, OSError):
    logging.exception("Could not load dashboard data")
    st.error("Unable to load workspace data. Check that the data folder is writable.")
    st.stop()

metrics = overview.metrics
hourly = hourly_workload(overview.advanced, datetime.now())
has_hourly = bool(overview.advanced.windows)
steps_by_id = {step.id: step for step in overview.advanced.steps}
accepted = [session for session in overview.advanced.sessions if session.status == "planned"]
current_conflicts = accepted_conflicts(overview.advanced, datetime.now())
if current_conflicts:
    st.warning(
        f"{len(current_conflicts)} accepted study session(s) conflict with "
        "current availability, commitments, deadlines or elapsed time. "
        "Review changes in Smart Planner."
    )
columns = st.columns(3)
with columns[0]:
    with st.container(border=True):
        st.metric("Open tasks", metrics.open_tasks)
        st.caption("Responsibilities still in progress")
with columns[1]:
    with st.container(border=True):
        st.metric("Remaining work", format_minutes(metrics.remaining_minutes))
        st.caption("Estimated time left across open tasks")
with columns[2]:
    with st.container(border=True):
        progress = (
            f"{metrics.completion_percentage:.0f}%"
            if metrics.completion_percentage is not None
            else "N/A"
        )
        st.metric("Due this week · completed", progress)
        st.caption(f"{metrics.due_week_completed} of {metrics.due_week_total} tasks due Mon–Sun")

left, right = st.columns([1.7, 1], gap="large")
by_id = {task.id: task for task in overview.tasks}
with left:
    with st.container(border=True):
        st.subheader("Today's focus")
        todays_hourly = sorted((s for s in accepted if s.day == today), key=lambda s: s.start)
        for session in todays_hourly[:5]:
            step = steps_by_id.get(session.step_id)
            if step:
                st.write(
                    f"**{format_time(session.start)}–{format_time(session.end)}** "
                    f"· {step.task_title} / {step.title}"
                )
        if metrics.today_allocations:
            st.caption("Legacy daily suggestions (not accepted sessions)")
            for allocation in metrics.today_allocations[:3]:
                task = by_id[allocation.task_id]
                st.write(f"{task.title} · {format_minutes(allocation.minutes)}")
        if not todays_hourly and not metrics.today_allocations:
            upcoming = sorted(
                (s for s in accepted if s.day > today), key=lambda s: (s.day, s.start)
            )
            if upcoming:
                next_session = upcoming[0]
                step = steps_by_id.get(next_session.step_id)
                if step:
                    st.caption("No saved sessions today. Next accepted session:")
                    st.write(
                        f"**{next_session.day:%a %d %b} "
                        f"{format_time(next_session.start)}-{format_time(next_session.end)}** "
                        f"· {step.title}"
                    )
            else:
                st.caption("Nothing scheduled today. Open Smart Planner to plan your next block.")
        st.page_link("workspace/views/planner.py", label="See full weekly plan")

    with st.container(border=True):
        st.subheader("Planned vs available time")
        st.caption(
            "Free study time after fixed commitments vs accepted sessions"
            if has_hourly
            else "Suggested daily time vs availability (legacy tasks)"
        )
        x = [workload.day.strftime("%a %d") for workload in metrics.workload]
        available = [
            hourly[w.day][0] if has_hourly else w.available_minutes for w in metrics.workload
        ]
        planned_minutes = [
            hourly[w.day][1] if has_hourly else w.planned_minutes for w in metrics.workload
        ]
        fig = go.Figure()
        fig.add_bar(
            name="Available",
            x=x,
            y=[amount / 60 for amount in available],
            customdata=[format_minutes(amount) for amount in available],
            marker_color="#454D4F",
            hovertemplate="%{x}<br>%{customdata} available<extra></extra>",
        )
        fig.add_bar(
            name="Planned",
            x=x,
            y=[amount / 60 for amount in planned_minutes],
            customdata=[format_minutes(amount) for amount in planned_minutes],
            marker_color="#A7BBA9",
            hovertemplate="%{x}<br>%{customdata} planned<extra></extra>",
        )
        fig.update_layout(
            barmode="group",
            height=300,
            margin=dict(l=10, r=10, t=14, b=10),
            paper_bgcolor="#191B1F",
            plot_bgcolor="#191B1F",
            font=dict(color="#D7D9D8"),
            xaxis=dict(showgrid=False, title=None),
            yaxis=dict(
                title="Hours",
                ticksuffix="h",
                showgrid=True,
                gridcolor="#34383A",
                rangemode="tozero",
            ),
            legend=dict(orientation="h", y=1.12, x=0),
        )
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

with right:
    with st.container(border=True):
        st.subheader("Deadlines")
        if metrics.overdue_tasks:
            st.markdown("**Overdue**")
            for task in metrics.overdue_tasks[:4]:
                days_late = (today - task.deadline).days
                st.write(f"**{task.title}** · {days_late}d overdue · {task.deadline:%d %b}")
            if len(metrics.overdue_tasks) > 4:
                st.caption(f"+{len(metrics.overdue_tasks) - 4} more overdue")
        if metrics.upcoming_tasks:
            st.markdown("**Upcoming**")
            for task in metrics.upcoming_tasks[:5]:
                days_until = (task.deadline - today).days
                when = (
                    "Today"
                    if days_until == 0
                    else ("Tomorrow" if days_until == 1 else f"In {days_until} days")
                )
                st.write(f"**{task.title}** · {when} · {task.deadline:%d %b}")
            if len(metrics.upcoming_tasks) > 5:
                st.caption(f"+{len(metrics.upcoming_tasks) - 5} later deadlines")
        if not metrics.overdue_tasks and not metrics.upcoming_tasks:
            st.caption("No pending tasks have deadlines.")
        st.page_link("workspace/views/tasks.py", label="Manage tasks")

    with st.container(border=True):
        st.subheader("Planning insight")
        proposal = make_revision(overview.advanced, datetime.now())
        urgent = [s for s in proposal.shortfalls if s.reason == "could_not_fit"]
        overdue = [s for s in proposal.shortfalls if s.reason == "overdue"]
        if urgent:
            st.write(
                f"{format_minutes(sum(item.minutes for item in urgent))} of timed "
                "study work could not fit before deadlines under this heuristic."
            )
        elif overdue:
            st.write(
                f"{format_minutes(sum(item.minutes for item in overdue))} of overdue "
                "timed study work is not scheduled."
            )
        elif has_hourly:
            st.write("Accepted sessions stay in place until you approve a proposed revision.")
        else:
            st.write(metrics.insight)
        if metrics.deadline_shortfall_minutes:
            st.caption("Shortfalls are calculated before each deadline, not from weekly totals.")
        st.page_link("workspace/views/planner.py", label="Review the plan")
