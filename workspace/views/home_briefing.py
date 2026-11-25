"""Two compact, read-only Home panels: daily briefing and deadline runway."""

from datetime import datetime

import streamlit as st

from workspace.home_intelligence import daily_briefing, deadline_runway, display_duration


def render_daily_briefing(overview, now: datetime) -> None:
    summary = daily_briefing(overview.tasks, overview.advanced, now)
    with st.container(border=True):
        st.markdown("#### Your daily briefing")
        st.write(summary.text)
        opened = bool(st.session_state.get("daily_briefing_open", False))
        if st.button(
            "Close today's agenda" if opened else "Start my day",
            key="daily_briefing_toggle",
            type="secondary" if opened else "primary",
        ):
            opened = not opened
            st.session_state["daily_briefing_open"] = opened
        if opened:
            if summary.agenda:
                st.markdown("**Today's calendar**")
                for start, end, label, kind in summary.agenda[:8]:
                    st.markdown(
                        f"**{start // 60:02d}:{start % 60:02d}–"
                        f"{end // 60:02d}:{end % 60:02d}** · "
                        f"{label} · {kind}"
                    )
                if len(summary.agenda) > 8:
                    st.caption(f"+{len(summary.agenda) - 8} more calendar items")
            else:
                st.caption("No calendar events or study blocks booked for today.")
            if summary.upcoming:
                st.markdown("**Coming up**")
                for title in summary.upcoming:
                    st.caption(title)
            st.page_link("workspace/views/week.py", label="Open today's calendar")


def _runway_row(item) -> None:
    due = (
        f"{abs(item.days_left)}d overdue"
        if item.days_left < 0
        else "Today"
        if item.days_left == 0
        else "Tomorrow"
        if item.days_left == 1
        else f"{item.deadline:%d %b}"
    )
    st.markdown(f"**{item.title}** · {due}")
    st.progress(item.done_percent / 100, text=f"{item.done_percent}% work completed")
    if not item.plannable:
        st.caption(
            f"{display_duration(item.remaining_minutes)} remaining · "
            "Not enrolled in hourly study planning"
        )
        return
    st.caption(
        f"{display_duration(item.remaining_minutes)} remaining · "
        f"{display_duration(item.reserved_minutes)} on calendar · "
        f"{display_duration(item.needs_slot_minutes)} still needs a study slot"
    )
    if item.days_left < 0:
        st.caption("Deadline passed; review this task.")
    elif not item.capacity_configured:
        st.caption("Set study availability in Calendar to estimate free time.")
    else:
        st.caption(
            f"{display_duration(item.open_capacity_minutes)} unbooked study capacity "
            "before this deadline (shared across all tasks)."
        )
        if item.needs_slot_minutes > item.open_capacity_minutes:
            st.warning(
                "Remaining unscheduled work exceeds currently open study capacity. "
                "Review your plan."
            )


def render_deadline_runway(overview, now: datetime) -> None:
    items = deadline_runway(overview.tasks, overview.advanced, now, max_items=8)
    with st.container(border=True):
        st.markdown("#### Deadline runway")
        st.caption("Recorded progress and available study capacity for the next 14 days")
        if not items:
            st.caption("No pending deadlines in the next 14 days.")
            return
        for index, item in enumerate(items[:3]):
            if index:
                st.divider()
            _runway_row(item)
        if len(items) > 3:
            with st.expander(f"See {len(items) - 3} more deadlines", expanded=False):
                for index, item in enumerate(items[3:]):
                    if index:
                        st.divider()
                    _runway_row(item)
        st.caption(
            "Booked study is not completed work. Free capacity is shared by tasks, "
            "so these figures do not guarantee that every deadline is feasible."
        )
        st.page_link("workspace/views/task_board.py", label="View all tasks")
