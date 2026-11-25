"""Compact weekly replay card on Home, never confusing booking with completion."""

import sqlite3
from datetime import datetime, timedelta

import streamlit as st

from workspace.replay_audit import approval_counts, enable_plan_history
from workspace.weekly_replay import weekly_replay


def _fmt(minutes: int) -> str:
    return f"{minutes // 60}h {minutes % 60}m" if minutes % 60 else f"{minutes // 60}h"


def _render_approval_history(db_path, anchor):
    counts = approval_counts(db_path, anchor)
    if counts is None:
        st.caption("Historical plan approvals were not tracked before this feature.")
        if st.button("Track future plan changes", key="replay_enable_history"):
            try:
                enable_plan_history(db_path)
            except (sqlite3.Error, OSError) as error:
                st.error(f"Could not enable plan history: {error}")
            else:
                st.rerun()
    else:
        approvals, replans = counts
        st.caption(
            f"{approvals} plan approval(s) this week, including {replans} replacement "
            "plan(s), since tracking was enabled."
        )
    st.caption(
        "Study sessions reflect records currently saved. Previously replaced bookings "
        "cannot be reconstructed retroactively. The approval log only covers changes "
        "after you enable tracking."
    )


def render_weekly_replay(snapshot, now: datetime, db_path) -> None:
    with st.expander("Weekly replay · planned vs recorded", expanded=False):
        choice = st.segmented_control(
            "Week", ["Last week", "This week"],
            default="Last week", key="replay_week_choice",
        ) or "Last week"
        anchor = now.date() - timedelta(days=7) if choice == "Last week" else now.date()
        summary = weekly_replay(snapshot, anchor)
        st.caption(f"{summary.monday:%d %b} – {summary.sunday:%d %b %Y}")
        _render_approval_history(db_path, anchor)
        if not summary.booked_minutes:
            st.caption("No saved study sessions for this week.")
            return
        a, b, c = st.columns(3)
        a.metric("Recorded bookings", _fmt(summary.booked_minutes))
        b.metric("Actually completed", _fmt(summary.finished_minutes))
        c.metric("Missed sessions", _fmt(summary.missed_minutes))
        st.markdown("**Day by day**")
        columns = st.columns(7, gap="small")
        for column, day in zip(columns, summary.days):
            with column:
                st.caption(f"{day.day:%a}")
                st.progress(
                    min(1.0, day.finished_minutes / day.booked_minutes)
                    if day.booked_minutes else 0.0
                )
                st.caption(_fmt(day.finished_minutes))
        if summary.subjects:
            st.markdown("**Where study time went**")
            for subject in summary.subjects[:6]:
                st.caption(
                    f"{subject.name} · {_fmt(subject.finished_minutes)} completed "
                    f"of {_fmt(subject.booked_minutes)} booked"
                )
            if len(summary.subjects) > 6:
                st.caption(f"+{len(summary.subjects) - 6} more tasks")
        if summary.pending_minutes:
            st.caption(
                f"{_fmt(summary.pending_minutes)} is still marked planned "
                "(not assumed completed)."
            )
