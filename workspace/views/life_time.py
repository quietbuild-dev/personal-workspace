"""Small, opt-in calendar panel for protecting personal time."""

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st

from workspace.advanced_planner import format_time, week_bounds
from workspace.advanced_repository import StaleProposalError
from workspace.life_planning import accept_time_protection, preview_time_protection
from workspace.repository import list_tasks
from workspace.study_dna import load_study_dna, required_task_ids
from workspace.views.schedule_comparison import (
    before_after_html,
    changed_days,
    format_slot,
    schedule_changes,
)

_TIMES = tuple(range(0, 1441, 30))


def render_time_protection(snapshot, now: datetime, db_path: Path) -> None:
    """A read-only preview until the user explicitly accepts a valid result."""
    with st.expander("Make room for life · Protect personal time", expanded=False):
        st.caption(
            "Pick a period to keep free of study and other obligations. "
            "The planner can move study blocks, but not fixed lectures or events."
        )
        _, sunday = week_bounds(now.date())
        days = tuple(now.date() + timedelta(days=i) for i in range((sunday - now.date()).days + 1))
        friday = next((day for day in days if day.weekday() == 4), days[0])
        day_index = days.index(friday)
        left, middle, right = st.columns([2, 1.5, 1.5], gap="small")
        with left:
            day = st.selectbox(
                "Day",
                days,
                index=day_index,
                format_func=lambda item: item.strftime("%A, %d %B"),
                key="life_day",
            )
        with middle:
            start = st.selectbox(
                "Free from",
                _TIMES[:-1],
                index=_TIMES.index(17 * 60),
                format_func=format_time,
                key="life_start",
            )
        with right:
            end = st.selectbox(
                "Until",
                _TIMES[1:],
                index=_TIMES[1:].index(22 * 60),
                format_func=format_time,
                key="life_end",
            )
        identity = (snapshot.fingerprint, day, start, end)
        if st.button("Preview free time", key="life_preview_button", type="primary"):
            st.session_state.pop("life_preview", None)
            try:
                profile = load_study_dna(db_path)
                required = required_task_ids(db_path, list_tasks(db_path))
                preview = preview_time_protection(
                    snapshot,
                    now,
                    day,
                    start,
                    end,
                    dna=profile,
                    required_ids=required,
                )
            except ValueError as error:
                st.warning(str(error))
            except (sqlite3.Error, OSError):
                logging.exception("Couldn't preview personal time")
                st.error("Couldn't load the planning information. Nothing was changed.")
            else:
                st.session_state["life_preview"] = (identity, preview)
        cached = st.session_state.get("life_preview")
        if not cached or cached[0] != identity:
            st.caption("Preview first. Nothing is saved until you approve the change.")
            return
        preview = cached[1]
        with st.container(border=True):
            st.markdown(f"**{day:%A, %d %B} · {format_time(start)}–{format_time(end)}**")
            st.caption("Personal time will appear as a pastel Personal block in Calendar.")
            before_set = set(preview.before)
            after_set = set(preview.revision.slots)
            moved = len(before_set - after_set)
            kept = len(before_set & after_set)
            a, b = st.columns(2)
            a.metric("Existing study blocks changed", moved)
            b.metric("Existing blocks kept", kept)
            if preview.feasible:
                st.success("Feasible for this week. " + preview.explanation)
            else:
                st.warning("Can't safely protect this time yet. " + preview.explanation)
            if preview.solver_message:
                st.caption(preview.solver_message)
            steps = {step.id: step for step in snapshot.steps}
            changes = schedule_changes(preview.before, preview.revision.slots, steps)
            if changes:
                st.markdown("**What changes**")
                for name, _, old, new in changes[:5]:
                    st.caption(
                        f"{name}: {', '.join(format_slot(slot) for slot in old) or 'none'} "
                        f"→ {', '.join(format_slot(slot) for slot in new) or 'none'}"
                    )
                if len(changes) > 5:
                    st.caption(f"{len(changes) - 5} more assignments affected.")
            else:
                st.caption("No study blocks need to move to keep this time free.")
            affected = changed_days(preview.before, preview.revision.slots)
            if affected:
                selected = st.selectbox(
                    "Compare day",
                    affected,
                    format_func=lambda item: item.strftime("%A, %d %B"),
                    key="life_compare_day",
                )
                st.markdown(
                    before_after_html(
                        selected,
                        snapshot.events,
                        preview.before,
                        preview.revision.slots,
                        steps,
                    ),
                    unsafe_allow_html=True,
                )
                st.caption(
                    "The before/after views compare study sessions. "
                    "Your new protected Personal event is added only on approval."
                )
            approve, cancel = st.columns(2)
            with approve:
                if st.button(
                    "Protect this time",
                    disabled=not preview.feasible,
                    type="primary",
                    key="life_approve_button",
                ):
                    try:
                        accept_time_protection(db_path, preview, datetime.now())
                    except (ValueError, StaleProposalError) as error:
                        st.error(str(error))
                    except (sqlite3.Error, OSError):
                        logging.exception("Couldn't save protected personal time")
                        st.error("Couldn't save the change. Your calendar was not modified.")
                    else:
                        st.session_state.pop("life_preview", None)
                        st.session_state.pop("goal_previews", None)
                        st.session_state["calendar_message"] = (
                            "Personal time protected and study schedule updated. "
                            "Use Undo at the top of Calendar to reverse both changes."
                        )
                        st.rerun()
            with cancel:
                if st.button("Cancel preview", key="life_cancel_button"):
                    st.session_state.pop("life_preview", None)
                    st.rerun()
