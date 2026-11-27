"""Weekly replay with clear planned/completed/missed visual comparison."""

from datetime import datetime, timedelta
from html import escape

import plotly.graph_objects as go
import streamlit as st

from workspace.repository import list_tasks
from workspace.weekly_replay import completed_tasks_in_week, weekly_replay


def _fmt(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h}h {m}m" if h and m else f"{h}h" if h else f"{m}m"


def _comparison_chart(summary):
    labels = [day.day.strftime("%a") for day in summary.days]
    planned = [day.booked_minutes / 60 for day in summary.days]
    completed = [day.finished_minutes / 60 for day in summary.days]
    missed = [day.missed_minutes / 60 for day in summary.days]
    fig = go.Figure()
    for name, values, color in (
        ("Booked", planned, "#B9A7CF"),
        ("Completed", completed, "#91B9A4"),
    ):
        fig.add_bar(
            name=name,
            x=labels,
            y=values,
            marker_color=color,
            marker_line_width=0,
            customdata=[_fmt(int(round(value * 60))) for value in values],
            hovertemplate="%{x} · " + name + ": %{customdata}<extra></extra>",
        )
    fig.update_layout(
        barmode="group",
        height=250,
        margin=dict(l=0, r=0, t=18, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#BAB5C7", size=12),
        legend=dict(orientation="h", y=1.15, x=0),
        xaxis=dict(showgrid=False, title=None),
        yaxis=dict(title="Hours", showgrid=True, gridcolor="#393442", zeroline=False),
    )
    return fig, missed


def render_weekly_replay(snapshot, now: datetime, db_path) -> None:
    with st.expander("Weekly replay · Planned vs completed", expanded=False):
        choice = (
            st.segmented_control(
                "Week",
                ["Last week", "This week"],
                default="Last week",
                key="replay_week_choice",
            )
            or "Last week"
        )
        anchor = now.date() - timedelta(days=7) if choice == "Last week" else now.date()
        summary = weekly_replay(snapshot, anchor)
        st.caption(f"{summary.monday:%d %b} – {summary.sunday:%d %b %Y}")
        tasks_completed = completed_tasks_in_week(
            list_tasks(db_path), summary.monday, summary.sunday
        )
        sessions_done = sum(
            session.status == "done" and summary.monday <= session.day <= summary.sunday
            for session in snapshot.sessions
        )
        first, second, third = st.columns(3)
        first.metric("Tasks completed", tasks_completed)
        second.metric("Study recorded", _fmt(summary.finished_minutes))
        third.metric("Study sessions done", sessions_done)
        if not summary.booked_minutes:
            st.caption("No study sessions recorded or booked for this week.")
            return
        fig, missed = _comparison_chart(summary)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        if any(missed):
            st.caption(
                "Missed: "
                + ", ".join(
                    f"{day.day:%a} {_fmt(day.missed_minutes)}"
                    for day in summary.days
                    if day.missed_minutes
                )
            )
        if summary.subjects:
            st.markdown("**By assignment**")
            for subject in summary.subjects:
                ratio = (
                    min(100, 100 * subject.finished_minutes / subject.booked_minutes)
                    if subject.booked_minutes
                    else 0
                )
                title = escape(subject.name)
                st.markdown(
                    '<div class="pw-replay-item">'
                    f"<span>{title}</span>"
                    f"<small>{_fmt(subject.finished_minutes)} / "
                    f"{_fmt(subject.booked_minutes)}</small></div>"
                    f'<div class="pw-replay-track"><div style="width:{ratio:.1f}%"></div></div>',
                    unsafe_allow_html=True,
                )
