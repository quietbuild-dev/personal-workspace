"""Ephemeral focus mode with read-only preview and explicit atomic acceptance."""

import logging
import sqlite3
from datetime import datetime

import streamlit as st

from workspace.advanced_planner import format_time, week_bounds
from workspace.advanced_repository import StaleProposalError, accept_revision
from workspace.energy_today import MODE_MINUTES, energy_proposal, focus_suggestions


def _time(slot) -> str:
    return f"{format_time(slot.start)}–{format_time(slot.end)}"


def render_energy_today(snapshot, now: datetime, db_path) -> None:
    with st.expander("How's your energy? · Adjust focus blocks", expanded=False):
        st.caption(
            "A temporary preference for one day. It changes suggested study block lengths "
            "but does not change your long-term settings, tasks, or commitments."
        )
        mode = st.segmented_control(
            "Focus mode", list(MODE_MINUTES), default="Normal", key="energy_today_mode"
        ) or "Normal"
        focus_day = st.date_input(
            "Day to adjust", value=now.date(), min_value=now.date(),
            max_value=week_bounds(now.date())[1], format="DD/MM/YYYY",
            key="energy_today_date",
        )
        if mode == "Low energy":
            st.caption(
                "Short, roughly 25-minute focus blocks; shorter tasks suggested first "
                "after deadlines."
            )
        elif mode == "Deep focus":
            st.caption(
                "Longer, up-to-90-minute focus blocks; longer tasks suggested first "
                "after deadlines."
            )
        else:
            st.caption("Balanced, up-to-50-minute focus blocks.")
        st.caption(
            "Blocks may be consecutive; breaks are not automatically reserved. "
            "Task length is an effort proxy, not a measured difficulty rating."
        )
        if st.button("Preview focus mode", key="energy_today_preview_button"):
            try:
                proposal = energy_proposal(snapshot, datetime.now(), mode, focus_day)
            except ValueError as error:
                st.error(f"No valid proposal: {error}")
                st.session_state.pop("energy_today_preview", None)
            else:
                st.session_state["energy_today_preview"] = (mode, focus_day, proposal)
        preview = st.session_state.get("energy_today_preview")
        if not preview:
            return
        old_mode, old_day, proposal = preview
        if (old_mode, old_day) != (mode, focus_day) or proposal.fingerprint != snapshot.fingerprint:
            st.info("The inputs or calendar changed. Preview again before approving.")
            return
        if proposal.monday != week_bounds(now.date())[0]:
            st.info("A new planning week has begun. Preview again.")
            return
        focus_slots = tuple(slot for slot in proposal.slots if slot.day == focus_day)
        if not focus_slots:
            st.info("There is no available study session on this day to adjust. Try another date.")
            return
        original = tuple(
            s for s in snapshot.sessions if s.status == "planned" and s.day == focus_day
        )
        labels = {step.id: step.task_title for step in snapshot.steps}
        st.markdown("**Proposed focus blocks**")
        a, b = st.columns(2, gap="small")
        with a:
            st.caption("Currently saved")
            if not original:
                st.caption("No accepted blocks")
            for session in original[:8]:
                st.caption(f"{_time(session)} · {labels.get(session.step_id, 'Study')}")
            if len(original) > 8:
                st.caption(f"+{len(original) - 8} more")
        with b:
            st.caption(f"Suggested · {mode}")
            for slot in focus_slots[:8]:
                st.caption(f"{_time(slot)} · {labels.get(slot.step_id, 'Study')}")
            if len(focus_slots) > 8:
                st.caption(f"+{len(focus_slots) - 8} more")
        suggestions = focus_suggestions(snapshot, proposal, mode, focus_day)
        if suggestions:
            st.caption(
                "Suggested starting focus: "
                + " · ".join(step.task_title for step in suggestions[:3])
                + ". This is guidance, not a change to calendar order."
            )
        step_map = {step.id: step for step in snapshot.steps}
        deadline_shortfall = sum(
            item.minutes for item in proposal.shortfalls
            if step_map.get(item.step_id) is not None
            and step_map[item.step_id].deadline is not None
            and step_map[item.step_id].deadline <= proposal.sunday
        )
        if deadline_shortfall:
            st.warning(
                f"Deadline coverage is incomplete ({deadline_shortfall} minutes unscheduled). "
                "Add availability or use the existing plan review before accepting."
            )
        elif proposal.shortfalls:
            st.caption("Some work due after this week will need planning later.")
        changed = proposal.added_or_changed + proposal.removed_or_changed
        if changed:
            st.caption(
                f"Across this week: {proposal.added_or_changed} new/changed blocks; "
                f"{proposal.removed_or_changed} existing blocks change."
            )
        else:
            st.caption("Your accepted plan already matches this preview.")
        approve, cancel = st.columns(2, gap="small")
        if approve.button(
            "Apply focus blocks", key="energy_today_apply", type="primary",
            disabled=bool(deadline_shortfall) or not changed,
        ):
            try:
                accept_revision(db_path, proposal, datetime.now())
            except (StaleProposalError, ValueError) as error:
                st.error(str(error))
            except (sqlite3.Error, OSError):
                logging.exception("Could not apply focus-mode proposal")
                st.error("Could not save the proposal. Your existing calendar is unchanged.")
            else:
                st.session_state.pop("energy_today_preview", None)
                st.session_state["calendar_message"] = (
                    "Focus blocks saved. Use Undo at the top of Calendar "
                    "to restore the prior schedule."
                )
                st.rerun()
        if cancel.button("Discard preview", key="energy_today_cancel"):
            st.session_state.pop("energy_today_preview", None)
            st.rerun()
        st.caption(
            "Preview does not save anything. Apply is the only action that "
            "writes to your calendar."
        )
