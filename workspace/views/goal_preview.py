"""Goal choice and optional comparison; all suggestions remain read-only."""

import streamlit as st

from workspace.advanced_planner import validate_revision
from workspace.optimizer import GOAL_NOTES, GOALS, optimize
from workspace.planning_insights import schedule_metrics
from workspace.repository import DEFAULT_DB_PATH
from workspace.study_breaks import get_break_minutes


def choose_goal_preview(snapshot, now, reschedule_id, *, dna=None, must_ids=frozenset()):
    gap_minutes = get_break_minutes(DEFAULT_DB_PATH)
    identity = (snapshot.fingerprint, now.date(), reschedule_id, dna, must_ids, gap_minutes)
    cache = st.session_state.get("goal_previews")
    if cache is None or cache[0] != identity:
        cache = (identity, now, {})
        st.session_state["goal_previews"] = cache

    default = "deadlines"
    if dna is not None:
        default = {"steady": "balance", "batch": "throughput"}.get(dna.distribution, "deadlines")
    selected = st.selectbox(
        "What matters most this week?",
        list(GOALS),
        index=list(GOALS).index(default),
        format_func=GOALS.get,
        key="optimizer_goal",
    )
    st.caption(GOAL_NOTES[selected])

    # The first preview is deliberate. Afterwards switching goals immediately
    # refreshes the suggestion, using the same snapshot and a cached result.
    refresh = st.button("Preview schedule", key="generate_goal_preview", type="primary")
    # Home and Calendar's one-click entry use the same safe preview path.
    # The navigation flag is consumed once and never approves a plan.
    refresh = refresh or bool(st.session_state.pop("start_week_plan", False))
    if refresh:
        cache = (identity, now, {})
        st.session_state["goal_previews"] = cache
        st.session_state.pop("calendar_adjusted_proposal", None)
    if refresh or (cache[2] and selected not in cache[2]):
        with st.spinner("Finding a schedule…"):
            cache[2][selected] = optimize(
                snapshot,
                now,
                goal=selected,
                reschedule_session_id=reschedule_id,
                dna=dna,
                compact=bool(dna and dna.distribution == "batch" and selected == "throughput"),
                require_task_ids=frozenset(),
                gap_minutes=gap_minutes,
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
        if result.engine == "greedy":
            st.caption("We couldn't find a better arrangement for this goal.")
        else:
            st.caption("Best arrangement found for your selected goal.")

    with st.expander("Compare other goals (optional)", expanded=False):
        if st.button("Compare goals", key="compare_goals"):
            for goal in GOALS:
                if goal not in cache[2]:
                    cache[2][goal] = optimize(
                        snapshot,
                        cache[1],
                        goal=goal,
                        reschedule_session_id=reschedule_id,
                        dna=dna,
                        compact=bool(dna and dna.distribution == "batch" and goal == "throughput"),
                        require_task_ids=frozenset(),
                        gap_minutes=gap_minutes,
                    )
        if len(cache[2]) > 1:
            from html import escape

            rows = []
            for goal, candidate in cache[2].items():
                if goal not in GOALS:
                    continue
                metrics = schedule_metrics(snapshot, candidate.revision, cache[1])
                peak = round(metrics["peak_day_minutes"])
                rows.append(
                    "<tr>"
                    f"<th>{escape(GOALS[goal])}</th>"
                    f"<td>{metrics['due_coverage_pct']:g}%</td>"
                    f"<td>{metrics['high_priority_coverage_pct']:g}%</td>"
                    f"<td>{len({slot.day for slot in candidate.revision.slots})}</td>"
                    f"<td>{peak // 60}h {peak % 60:02d}m</td>"
                    f"<td>{metrics['moved_or_removed_sessions']}</td>"
                    "</tr>"
                )
            st.markdown(
                '<div class="pw-goal-table-scroll"><table class="pw-goal-table">'
                "<thead><tr><th>Goal</th><th>Deadline work scheduled</th>"
                "<th>High-priority work scheduled</th><th>Days with study</th>"
                "<th>Longest study day</th><th>Existing sessions changed</th>"
                "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>",
                unsafe_allow_html=True,
            )
    return result, selected
