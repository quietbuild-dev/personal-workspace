"""Goal selection and per-session preview cache; never writes calendar data."""

import streamlit as st

from workspace.advanced_planner import validate_revision
from workspace.optimizer import GOAL_NOTES, GOALS, optimize
from workspace.planning_insights import schedule_metrics


def choose_goal_preview(snapshot, now, reschedule_id):
    identity = (snapshot.fingerprint, now.date(), reschedule_id)
    cache = st.session_state.get("goal_previews")
    if cache is None or cache[0] != identity:
        cache = (identity, now, {})
        st.session_state["goal_previews"] = cache
    selected = st.selectbox(
        "What matters most this week?", list(GOALS), format_func=GOALS.get, key="optimizer_goal"
    )
    st.caption(GOAL_NOTES[selected])
    st.caption(
        "Keep my routine replaces ‘Change as little as possible’. "
        "Get as much done as possible replaces ‘Find more time for unfinished work’."
    )
    if st.button("Generate goal preview", key="generate_goal_preview", type="primary"):
        cache = (identity, now, {})
        cache[2][selected] = optimize(
            snapshot, now, goal=selected, reschedule_session_id=reschedule_id
        )
        st.session_state["goal_previews"] = cache
        st.session_state.pop("calendar_adjusted_proposal", None)
    result = cache[2].get(selected)
    if result is None:
        st.caption("Generate a preview for this goal. Your saved calendar stays in place.")
        return None, selected
    try:
        validate_revision(snapshot, result.revision, now)
    except ValueError:
        st.warning("This preview is out of date. Generate a fresh preview before approval.")
        return None, selected
    if result.message:
        st.info(result.message)
    if st.button("Compare all goals", key="compare_goals"):
        for goal in GOALS:
            if goal not in cache[2]:
                cache[2][goal] = optimize(
                    snapshot, cache[1], goal=goal, reschedule_session_id=reschedule_id
                )
    if len(cache[2]) > 1:
        rows = []
        for goal, alternative in cache[2].items():
            metrics = schedule_metrics(snapshot, alternative.revision, cache[1])
            rows.append(
                {
                    "Goal": GOALS[goal],
                    "Study min": metrics["scheduled_minutes"],
                    "Due this week covered %": metrics["due_coverage_pct"],
                    "High priority covered %": metrics["high_priority_coverage_pct"],
                    "Blocks affected": metrics["moved_or_removed_sessions"],
                    "Busiest day min": metrics["peak_day_minutes"],
                    "Study blocks": metrics["session_count"],
                }
            )
        st.dataframe(rows, hide_index=True)
        st.caption(
            "Select another goal above to view its calendar. "
            "Coverage means reserved time, not completed work. Equal results are possible."
        )
    return result, selected
