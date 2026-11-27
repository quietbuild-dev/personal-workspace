"""Compact, actionable feedback on the currently saved study plan."""

import streamlit as st

from workspace.home_intelligence import display_duration
from workspace.schedule_lab import schedule_health


def render_plan_doctor(snapshot, now) -> None:
    """One short warning and a direct, reviewed planning action."""
    health = schedule_health(snapshot, now)
    if not health.conflict_messages and not health.unreserved_deadline_minutes:
        return
    with st.container(border=True):
        if health.unreserved_deadline_minutes:
            st.caption(
                f"{display_duration(health.unreserved_deadline_minutes)} "
                "of deadline work still needs planning."
            )
        else:
            st.caption(f"{len(health.conflict_messages)} study sessions need attention.")
        if st.button("Fix my schedule", key="doctor_open_review", type="primary"):
            st.session_state["optimizer_goal"] = "deadlines"
            st.session_state["start_week_plan"] = True
            st.session_state["calendar_review_open"] = True
            st.rerun()
