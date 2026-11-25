"""Goal choice and optional comparison; all suggestions remain read-only."""

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

    # The first preview is deliberate. Afterwards switching goals immediately
    # refreshes the suggestion, using the same snapshot and a cached result.
    refresh = st.button("Preview schedule", key="generate_goal_preview", type="primary")
    if refresh:
        cache = (identity, now, {})
        st.session_state["goal_previews"] = cache
        st.session_state.pop("calendar_adjusted_proposal", None)
    if refresh or (cache[2] and selected not in cache[2]):
        cache[2][selected] = optimize(
            snapshot, now, goal=selected, reschedule_session_id=reschedule_id
        )

    result = cache[2].get(selected)
    if result is None:
        st.caption("Choose a goal, then preview a schedule. Your calendar stays unchanged.")
        return None, selected
    try:
        validate_revision(snapshot, result.revision, now)
    except ValueError:
        st.warning("Your calendar has changed. Preview again to see the latest plan.")
        return None, selected
    if result.message:
        st.info(result.message)

    with st.expander("Compare other goals (optional)", expanded=False):
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
                        "Due work allocated": f"{metrics['due_coverage_pct']:g}%",
                        "Priority work allocated": f"{metrics['high_priority_coverage_pct']:g}%",
                        "Existing blocks changed": metrics["moved_or_removed_sessions"],
                    }
                )
            st.dataframe(rows, hide_index=True, use_container_width=True)
            st.caption(
                "Percentages measure reserved study time, not completed assignments. "
                "Choose a goal above to inspect its calendar."
            )
        else:
            st.caption("Compare the alternative plans only if you want to explore trade-offs.")
    return result, selected
