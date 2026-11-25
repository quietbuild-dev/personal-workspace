"""Streamlit Smart Planner: accepted hourly calendar plus legacy daily view."""

import streamlit as st

from workspace.repository import DEFAULT_DB_PATH
from workspace.views.daily_planner import render_daily
from workspace.views.weekly_calendar import render_weekly_calendar

st.title("Advanced Planning")
st.caption(
    "Detailed saved timetable and legacy daily-capacity tools. "
    "For day-to-day scheduling and Rescue My Week, use Calendar."
)
render_weekly_calendar(DEFAULT_DB_PATH)
st.divider()
with st.expander("Legacy daily-minute suggestions (not an accepted hourly schedule)"):
    st.caption(
        "Original minute-per-day capacity remains available for existing tasks. "
        "This legacy suggestion is separate from the accepted hourly calendar."
    )
    render_daily(DEFAULT_DB_PATH)
