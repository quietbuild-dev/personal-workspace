"""Goal choice and optional comparison; all suggestions remain read-only."""

import streamlit as st

from workspace.advanced_planner import validate_revision
from workspace.deadline_guarantees import check_required_coverage
from workspace.optimizer import GOAL_NOTES, GOALS, optimize
from workspace.planning_insights import schedule_metrics
from workspace.schedule_quality import describe_goal_tradeoff


def choose_goal_preview(snapshot, now, reschedule_id, *, dna=None, must_ids=frozenset()):
    identity = (snapshot.fingerprint, now.date(), reschedule_id, dna, must_ids)
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
        cache[2][selected] = optimize(
            snapshot,
            now,
            goal=selected,
            reschedule_session_id=reschedule_id,
            dna=dna,
            compact=bool(dna and dna.distribution == "batch" and selected == "throughput"),
            require_task_ids=frozenset(),
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
        if result.message == "Best plan found within the search limit.":
            st.caption("Schedule ready to review.")
            with st.expander("Solver details (optional)", expanded=False):
                st.caption(result.message)
        else:
            st.info(result.message)

    with st.expander("Compare other goals (optional)", expanded=False):
        if st.button("Compare all goals", key="compare_goals"):
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
                    )
        compared_goals = {k: v for k, v in cache[2].items() if k in GOALS}
        if len(compared_goals) > 1:
            if selected != "routine" and "routine" in compared_goals:
                chosen_metrics = schedule_metrics(snapshot, result.revision, cache[1])
                routine_metrics = schedule_metrics(snapshot, cache[2]["routine"].revision, cache[1])
                st.caption(describe_goal_tradeoff(chosen_metrics, routine_metrics))
            rows = []
            for goal, alternative in compared_goals.items():
                metrics = schedule_metrics(snapshot, alternative.revision, cache[1])
                rows.append(
                    {
                        "Goal": GOALS[goal],
                        "Due work allocated": f"{metrics['due_coverage_pct']:g}%",
                        "Priority work allocated": f"{metrics['high_priority_coverage_pct']:g}%",
                        "Study days": len({slot.day for slot in alternative.revision.slots}),
                        "Busiest day": f"{metrics['peak_day_minutes'] / 60:g}h",
                        "Existing blocks changed": metrics["moved_or_removed_sessions"],
                    }
                )
            plans = list(compared_goals.values())
            same_slots = all(plan.revision.slots == plans[0].revision.slots for plan in plans[1:])
            if same_slots:
                st.caption(
                    "These goals made the same timetable this week. "
                    "Your available time and deadlines may leave little room for variation."
                )
            elif (
                len({tuple(value for key, value in row.items() if key != "Goal") for row in rows})
                == 1
            ):
                st.caption("The plans differ in timing, even if these totals match.")
            st.dataframe(rows, hide_index=True, width="stretch")
            st.caption(
                "Percentages show time set aside, not assignments finished. "
                "Select a goal above to inspect its calendar."
            )
        else:
            st.caption("Compare the alternative plans only if you want to explore trade-offs.")
    # Both variants must allocate all remaining required timed work due this week.
    # Unlike objective comparisons, this screen never labels a shortfall a complete plan.
    with st.expander("Plan A vs Plan B · Same deadlines, different rhythms", expanded=False):
        st.caption(
            "Both plans aim to fit all required deadline work. "
            "Plan A spreads study out; Plan B tries to keep some days lighter."
        )
        if st.button("Build both plans", key="build_ab_plans"):
            cache[2]["ab_steady"] = optimize(
                snapshot,
                now,
                goal="balance",
                reschedule_session_id=reschedule_id,
                dna=dna,
                require_task_ids=must_ids,
                time_limit=3.0,
            )
            cache[2]["ab_focus"] = optimize(
                snapshot,
                now,
                goal="throughput",
                reschedule_session_id=reschedule_id,
                dna=dna,
                compact=True,
                require_task_ids=must_ids,
                time_limit=3.0,
            )
            st.session_state.pop("calendar_adjusted_proposal", None)
        a, b = cache[2].get("ab_steady"), cache[2].get("ab_focus")
        if a is not None and b is not None:
            usable = True
            rows = []
            for label, candidate in (("Plan A · Steady", a), ("Plan B · Focus days", b)):
                try:
                    validate_revision(snapshot, candidate.revision, now)
                except ValueError:
                    usable = False
                    st.warning("The calendar changed. Rebuild both plans.")
                    break
                coverage = check_required_coverage(snapshot, candidate.revision, now, must_ids)
                metrics = schedule_metrics(snapshot, candidate.revision, now)
                if not coverage.complete:
                    usable = False
                    st.warning(
                        f"{label}: {coverage.outstanding_minutes // 60}h "
                        f"{coverage.outstanding_minutes % 60}m of deadline work "
                        "still needs time. This plan isn't complete yet."
                    )
                rows.append(
                    {
                        "Plan": label,
                        "Required work allocated": (
                            f"{coverage.allocated_minutes}/{coverage.required_minutes} min"
                        ),
                        "Study days": len({s.day for s in candidate.revision.slots}),
                        "Busiest day": f"{metrics['peak_day_minutes'] / 60:g}h",
                        "Blocks changed": metrics["moved_or_removed_sessions"],
                    }
                )
            if usable:
                st.dataframe(rows, hide_index=True, width="stretch")
                if a.revision.slots == b.revision.slots:
                    st.caption("Both objectives produced the same feasible schedule this week.")
                choice = st.radio(
                    "Review a proposed plan",
                    ("Current goal", "Plan A · Steady", "Plan B · Focus days"),
                    key="ab_plan_choice",
                    horizontal=True,
                )
                if choice != "Current goal":
                    selected = "ab_steady" if choice.startswith("Plan A") else "ab_focus"
                    result = cache[2][selected]
                    st.caption("The Before/After review and approval below use this selection.")
            else:
                st.caption(
                    "Try changing availability or reducing optional work, then rebuild. "
                    "A bounded search cannot prove a complete plan is impossible."
                )
    return result, selected
