"""Live dashboard derived from the same saved tasks and planner rules."""

import logging
import sqlite3
from datetime import date

import plotly.graph_objects as go
import streamlit as st

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
columns = st.columns(3)
with columns[0]:
    with st.container(border=True):
        st.metric("Open tasks", metrics.open_tasks)
with columns[1]:
    with st.container(border=True):
        st.metric("Remaining work", format_minutes(metrics.remaining_minutes))
with columns[2]:
    with st.container(border=True):
        progress = (f"{metrics.completion_percentage:.0f}%"
                    if metrics.completion_percentage is not None else "N/A")
        st.metric("Due this week · completed", progress)
        st.caption(f"{metrics.due_week_completed} of {metrics.due_week_total} tasks due Mon–Sun")

left, right = st.columns([1.7, 1], gap="large")
by_id = {task.id: task for task in overview.tasks}
with left:
    with st.container(border=True):
        st.subheader("Today's focus")
        if metrics.today_allocations:
            for allocation in metrics.today_allocations[:3]:
                task = by_id[allocation.task_id]
                st.write(f"**{task.title}** · {format_minutes(allocation.minutes)}")
            if len(metrics.today_allocations) > 3:
                st.caption(f"And {len(metrics.today_allocations) - 3} more tasks today.")
        else:
            st.caption("No work allocated today. Add tasks or availability to build your plan.")
        st.page_link("workspace/views/planner.py", label="See full weekly plan")

    with st.container(border=True):
        st.subheader("Planned vs available time")
        st.caption("Today through Sunday only. Past days are not treated as completed work.")
        x = [workload.day.strftime("%a %d") for workload in metrics.workload]
        fig = go.Figure()
        fig.add_bar(
            name="Available", x=x,
            y=[w.available_minutes for w in metrics.workload],
            marker_color="#43494A",
            hovertemplate="%{x}: %{y} min<extra>Available</extra>",
        )
        fig.add_bar(
            name="Planned", x=x,
            y=[w.planned_minutes for w in metrics.workload],
            marker_color="#A7BBA9",
            hovertemplate="%{x}: %{y} min<extra>Planned</extra>",
        )
        fig.update_layout(
            barmode="group", height=300,
            margin=dict(l=10, r=10, t=14, b=10),
            paper_bgcolor="#191B1F", plot_bgcolor="#191B1F",
            font=dict(color="#D7D9D8"),
            xaxis=dict(showgrid=False, title=None),
            yaxis=dict(title="Minutes", showgrid=True, gridcolor="#34383A", rangemode="tozero"),
            legend=dict(orientation="h", y=1.12, x=0),
        )
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

with right:
    with st.container(border=True):
        st.subheader("Deadlines")
        if metrics.overdue_tasks:
            st.markdown("**Overdue**")
            for task in metrics.overdue_tasks[:4]:
                st.write(f"{task.title} · {task.deadline:%d %b}")
            if len(metrics.overdue_tasks) > 4:
                st.caption(f"+{len(metrics.overdue_tasks) - 4} more overdue")
        if metrics.upcoming_tasks:
            st.markdown("**Upcoming**")
            for task in metrics.upcoming_tasks[:5]:
                st.write(f"{task.title} · {task.deadline:%d %b}")
            if len(metrics.upcoming_tasks) > 5:
                st.caption(f"+{len(metrics.upcoming_tasks) - 5} later deadlines")
        if not metrics.overdue_tasks and not metrics.upcoming_tasks:
            st.caption("No pending tasks have deadlines.")
        st.page_link("workspace/views/tasks.py", label="Manage tasks")

    with st.container(border=True):
        st.subheader("Planning insight")
        st.write(metrics.insight)
        if metrics.deadline_shortfall_minutes:
            st.caption("Shortfalls are calculated before each deadline, not from weekly totals.")
        st.page_link("workspace/views/planner.py", label="Review the plan")
