"""Calendar-date availability and a transparent, recalculated weekly plan."""

import logging
import sqlite3
from datetime import date, timedelta

import streamlit as st

from workspace.metrics import format_minutes
from workspace.overview import load_overview
from workspace.planner import week_bounds
from workspace.repository import DEFAULT_DB_PATH, save_availability

st.title("Smart Planner")
st.caption("A realistic plan based on your deadlines, priority and time available.")

today = date.today()
monday, sunday = week_bounds(today)
try:
    overview = load_overview(DEFAULT_DB_PATH, today)
except (sqlite3.Error, OSError):
    logging.exception("Could not load planning data")
    st.error("Unable to open workspace data. Check the data folder and try again.")
    st.stop()

notice = st.session_state.pop("availability_notice", None)
if notice:
    st.success(notice)

st.subheader(f"Availability · {monday:%d %b}–{sunday:%d %b %Y}")
st.caption(
    "Enter **remaining** available minutes for today and available minutes for future dates. "
    "Past days cannot be edited here. Missing dates count as zero; entries never repeat weekly."
)

weekdays = [monday + timedelta(days=offset) for offset in range(7)]
with st.form("weekly_availability"):
    entries: dict[date, int] = {}
    for segment in (weekdays[:4], weekdays[4:]):
        columns = st.columns(len(segment))
        for column, day in zip(columns, segment, strict=True):
            with column:
                entries[day] = st.number_input(
                    f"{day:%a %d %b}" + (" · today" if day == today else ""),
                    min_value=0,
                    max_value=1440,
                    value=overview.availability[day],
                    step=15,
                    disabled=day < today,
                    key=f"availability_{day.isoformat()}",
                )
    save = st.form_submit_button("Save availability", type="primary")
if save:
    try:
        save_availability(DEFAULT_DB_PATH, {day: value for day, value in entries.items()
                                             if day >= today})
    except ValueError as error:
        st.error(str(error))
    except (sqlite3.Error, OSError):
        logging.exception("Could not save availability")
        st.error("Availability could not be saved; your previous values are unchanged.")
    else:
        st.session_state["availability_notice"] = "Availability saved. Plan recalculated."
        st.rerun()

st.subheader("Suggested plan · today through Sunday")
st.caption(
    "Deadline first, then higher priority, then task ID. Tasks can be split across days. "
    "This is a deterministic heuristic, not an optimal scheduler. "
    "Planning does not mark work completed or reduce remaining minutes."
)
by_id = {task.id: task for task in overview.tasks}
allocations_by_day = {}
for allocation in overview.plan.allocations:
    allocations_by_day.setdefault(allocation.day, []).append(allocation)

for workload in overview.metrics.workload:
    with st.container(border=True):
        st.markdown(
            f"**{workload.day:%A %d %B}** · "
            f"{format_minutes(workload.planned_minutes)} planned / "
            f"{format_minutes(workload.available_minutes)} available"
        )
        daily = allocations_by_day.get(workload.day, [])
        if daily:
            for allocation in daily:
                task = by_id[allocation.task_id]
                due = f" · due {task.deadline:%d %b}" if task.deadline else ""
                st.write(f"{task.title} — {format_minutes(allocation.minutes)}{due}")
        else:
            st.caption("No work scheduled for this day.")

if overview.plan.unallocated:
    st.subheader("Work that did not fit")
    for reason, heading, explanation in (
        ("overdue", "Overdue — not rescheduled",
         "Update or clear the old deadline to make this work schedulable."),
        ("insufficient_capacity_before_deadline", "Due this week — capacity shortfall",
         "Not enough eligible time before the deadline, even if later days are free."),
        ("outside_current_plan", "Outside this week's plan",
         "Later-due or undated backlog; future deadline feasibility is not assessed."),
    ):
        items = [item for item in overview.plan.unallocated if item.reason == reason]
        if items:
            with st.container(border=True):
                st.markdown(f"**{heading}**")
                st.caption(explanation)
                for item in items:
                    st.write(f"{by_id[item.task_id].title} — {format_minutes(item.minutes)}")
else:
    st.success("All currently open work fits within this week's entered availability.")

if not overview.tasks:
    st.info("Add tasks in Tasks & Projects to generate a personal plan.")
    st.page_link("workspace/views/tasks.py", label="Open Tasks & Projects")
