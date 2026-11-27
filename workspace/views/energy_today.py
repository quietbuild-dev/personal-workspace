"""Ephemeral focus mode with read-only preview and explicit atomic acceptance."""

import logging
import sqlite3
from datetime import datetime, timedelta

import streamlit as st

from workspace.advanced_planner import format_time, week_bounds
from workspace.advanced_repository import StaleProposalError, accept_revision
from workspace.energy_today import energy_proposal
from workspace.study_breaks import get_break_minutes


def _time(slot) -> str:
    return f"{format_time(slot.start)}–{format_time(slot.end)}"


def render_energy_today(snapshot, now: datetime, db_path) -> None:
    with st.expander("Today's energy", expanded=False):
        st.caption("Adjust today's study rhythm without adding more work.")
        mode = (
            st.segmented_control(
                "Energy",
                ["Low energy", "Normal", "High energy"],
                default="Normal",
                key="energy_today_mode",
            )
            or "Normal"
        )
        _, sunday = week_bounds(now.date())
        available_days = [
            now.date() + timedelta(days=i) for i in range((sunday - now.date()).days + 1)
        ]
        counts = {
            day: sum(s.status == "planned" and s.day == day for s in snapshot.sessions)
            for day in available_days
        }
        suggested_day = next((day for day in available_days if counts[day]), now.date())
        focus_day = st.selectbox(
            "Day to adjust",
            available_days,
            index=available_days.index(suggested_day),
            format_func=lambda day: (
                f"{day:%a %d %b} · {counts[day]} booked study session(s)"
                if counts[day]
                else f"{day:%a %d %b} · No booked study"
            ),
            key="energy_today_date",
        )
        if not any(counts.values()):
            st.info(
                "No study sessions have been accepted this week. "
                "Use Review a new plan first, then adjust your focus blocks."
            )
        if mode == "Low energy":
            st.caption(
                "Shorter focus blocks (10–25m), 5-minute pauses, "
                "and a longer rest after four when possible."
            )
        elif mode == "High energy":
            st.caption("Longer sessions, with fewer interruptions.")
        else:
            st.caption("Your saved schedule stays as it is.")
        gap = get_break_minutes(db_path)
        if st.button("Preview focus mode", key="energy_today_preview_button"):
            try:
                proposal = energy_proposal(
                    snapshot,
                    datetime.now(),
                    mode,
                    focus_day,
                    break_minutes=gap,
                )
            except ValueError as error:
                st.error(f"No valid proposal: {error}")
                st.session_state.pop("energy_today_preview", None)
            else:
                st.session_state["energy_today_preview"] = (mode, focus_day, gap, proposal)
        preview = st.session_state.get("energy_today_preview")
        if not preview:
            return
        old_mode, old_day, old_gap, proposal = preview
        if (old_mode, old_day, old_gap) != (
            mode,
            focus_day,
            gap,
        ) or proposal.fingerprint != snapshot.fingerprint:
            st.info("Your calendar changed. Preview again before saving.")
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
        original_minutes = sum(s.end - s.start for s in original)
        proposed_minutes = sum(s.minutes for s in focus_slots)
        st.caption(
            f"{original_minutes // 60}h {original_minutes % 60}m saved → "
            f"{proposed_minutes // 60}h {proposed_minutes % 60}m proposed. "
            "The rest of your calendar stays unchanged."
        )
        changed = proposal.added_or_changed + proposal.removed_or_changed
        if not changed:
            if mode == "Low energy":
                st.info(
                    "There isn't enough free time to add breaks safely on this day. "
                    "Your booked study stays unchanged. You can try a different day."
                )
            else:
                st.info(
                    "Normal keeps your saved plan unchanged."
                    if mode == "Normal"
                    else "There are no safe longer focus blocks to apply on this day."
                )
            if st.button("Close preview", key="energy_today_close"):
                st.session_state.pop("energy_today_preview", None)
                st.rerun()
            return
        approve, cancel = st.columns(2, gap="small")
        if approve.button(
            "Apply focus blocks",
            key="energy_today_apply",
            type="primary",
            disabled=not changed,
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
                st.session_state["calendar_message"] = "Focus blocks updated"
                st.rerun()
        if cancel.button("Cancel", key="energy_today_cancel"):
            st.session_state.pop("energy_today_preview", None)
            st.rerun()
