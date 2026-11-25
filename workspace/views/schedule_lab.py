"""Calendar Schedule Lab: diagnostic checks, read-only what-if, grounded explanations."""

import sqlite3
from datetime import datetime

import streamlit as st

from workspace.advanced_planner import format_time, week_bounds
from workspace.repository import list_tasks
from workspace.schedule_lab import (
    explanation_factors,
    moved_session_summary,
    schedule_health,
    stress_test,
)
from workspace.study_dna import load_study_dna, required_task_ids

TIME_OPTIONS = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)] + ["24:00"]


def _minute(label: str) -> int:
    hour, minute = label.split(":")
    return 60 * int(hour) + int(minute)


def _slot_label(slot, labels):
    return (
        f"{slot.day:%a %d %b} · {format_time(slot.start)}–{format_time(slot.end)} · "
        f"{labels.get(slot.step_id, 'Study')}"
    )


def _render_health(snapshot, now):
    report = schedule_health(snapshot, now)
    if report.conflict_messages:
        st.warning(f"{len(report.conflict_messages)} accepted blocks need review.")
        for issue in report.conflict_messages[:3]:
            st.caption(issue)
    else:
        st.caption("No fixed-commitment conflicts detected in accepted study blocks.")
    if report.unreserved_deadline_minutes:
        amount = report.unreserved_deadline_minutes
        st.warning(
            f"{amount // 60}h {amount % 60}m of remaining deadline work "
            "has no future study reservation this week."
        )
    elif report.active_deadline_steps:
        st.caption("All remaining work due this week currently has a reserved block.")
    else:
        st.caption("No active timed study steps are due this week.")
    if report.insufficient_breaks:
        st.info(
            f"{report.insufficient_breaks} pair(s) of study blocks leave less "
            "than a 10-minute gap. Consider adding a break manually."
        )
    st.caption(
        "Reservations are not completed work; this check does not prove that "
        "all deadlines can be met or insert breaks automatically."
    )


def _render_what_if(snapshot, now, db_path, labels):
    _, sunday = week_bounds(now.date())
    day = st.date_input(
        "Day affected", min_value=now.date(), max_value=sunday,
        value=now.date(), format="DD/MM/YYYY", key="lab_whatif_date",
    )
    a, b = st.columns(2, gap="small")
    with a:
        start_label = st.selectbox(
            "Unavailable from", TIME_OPTIONS[:-1], index=30, key="lab_whatif_from",
        )
    with b:
        end_label = st.selectbox(
            "Until", TIME_OPTIONS[1:], index=35, key="lab_whatif_until",
        )
    start, end = _minute(start_label), _minute(end_label)
    inputs = (snapshot.fingerprint, day, start, end, now.date())
    if st.button("Stress-test my plan", key="lab_run_whatif"):
        try:
            dna = load_study_dna(db_path)
            must = required_task_ids(db_path, list_tasks(db_path))
            preview = stress_test(
                snapshot, datetime.now(), day, start, end,
                dna=dna, required_ids=must,
            )
        except (ValueError, sqlite3.Error, OSError) as error:
            st.error(str(error))
            st.session_state.pop("lab_stress_preview", None)
        else:
            st.session_state["lab_stress_preview"] = (inputs, preview)
    saved = st.session_state.get("lab_stress_preview")
    if saved:
        saved_inputs, preview = saved
        if saved_inputs != inputs:
            st.info("Inputs or saved calendar changed. Run the stress test again.")
        else:
            if preview.feasible:
                st.success("Deadline-preserving alternative found for this scenario.")
            else:
                st.warning("The scenario does not preserve all required deadline coverage.")
            st.caption(preview.explanation)
            if preview.solver_message:
                st.caption(preview.solver_message)
            removed, added = moved_session_summary(preview)
            left, right = st.columns(2, gap="small")
            with left:
                st.markdown(f"**Existing blocks affected ({len(removed)})**")
                for slot in removed[:8]:
                    st.caption(_slot_label(slot, labels))
                if len(removed) > 8:
                    st.caption(f"+{len(removed) - 8} more")
            with right:
                st.markdown(f"**Proposed blocks ({len(added)})**")
                for slot in added[:8]:
                    st.caption(_slot_label(slot, labels))
                if len(added) > 8:
                    st.caption(f"+{len(added) - 8} more")
            st.caption(
                "Simulation only. To actually protect a time window, "
                "use Make Room for Life and approve its separate fresh preview."
            )


def _render_why(snapshot, now, labels):
    planned = sorted(
        (s for s in snapshot.sessions if s.status == "planned"),
        key=lambda s: (s.day, s.start, s.id),
    )
    if not planned:
        st.caption("Accept a study plan first to inspect its sessions.")
    else:
        choices = {s.id: s for s in planned}
        selected = st.selectbox(
            "Accepted study session", list(choices),
            format_func=lambda i: _slot_label(choices[i], labels),
            key="lab_explain_session",
        )
        for reason in explanation_factors(snapshot, choices[selected], now):
            st.caption("• " + reason)
        st.caption(
            "These are verified scheduling inputs—not a claim that the solver "
            "chose this exact time for one specific reason."
        )


def render_schedule_lab(snapshot, now: datetime, db_path) -> None:
    with st.expander("Schedule Lab · stress test and explain decisions", expanded=False):
        st.caption(
            "Investigate your schedule before changing it. Simulations are read-only; "
            "no event or study session is saved from this panel."
        )
        section = st.segmented_control(
            "Explore", ["Plan health", "What if I lose time?", "Why this session?"],
            default="Plan health", key="lab_section",
        ) or "Plan health"
        labels = {step.id: step.task_title for step in snapshot.steps}
        if section == "Plan health":
            _render_health(snapshot, now)
        elif section == "What if I lose time?":
            _render_what_if(snapshot, now, db_path, labels)
        else:
            _render_why(snapshot, now, labels)
