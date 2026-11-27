"""Protect several personal-time windows with one optimizer preview and one Undo."""

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st

from workspace.advanced_planner import format_time, week_bounds
from workspace.advanced_repository import StaleProposalError
from workspace.life_planning import (
    accept_time_protection,
    preview_time_protection_many,
)
from workspace.repository import list_tasks
from workspace.study_breaks import get_break_minutes
from workspace.study_dna import load_study_dna, required_task_ids
from workspace.views.schedule_comparison import format_slot

_TIMES = tuple(range(0, 1441, 5))


def render_time_protection(snapshot, now: datetime, db_path: Path) -> None:
    """Collect windows, then preview them together; no DB changes until approval."""
    with st.expander("Make room for life", expanded=False):
        _, sunday = week_bounds(now.date())
        days = tuple(now.date() + timedelta(days=i) for i in range((sunday - now.date()).days + 1))
        default_day = next((d for d in days if d.weekday() == 4), days[0])
        a, b, c = st.columns([2, 1.5, 1.5], gap="small")
        with a:
            day = st.selectbox(
                "Day",
                days,
                index=days.index(default_day),
                format_func=lambda d: d.strftime("%a %d %b"),
                key="life_day",
            )
        with b:
            start = st.selectbox(
                "Free from",
                _TIMES[:-1],
                index=_TIMES.index(17 * 60),
                format_func=format_time,
                key="life_start",
            )
        with c:
            end = st.selectbox(
                "Until",
                _TIMES[1:],
                index=_TIMES[1:].index(22 * 60),
                format_func=format_time,
                key="life_end",
            )
        windows = tuple(st.session_state.get("life_windows", ()))
        add, clear = st.columns(2, gap="small")
        with add:
            if st.button("+ Add period", key="life_add_window"):
                if start >= end:
                    st.warning("The end must be after the start.")
                elif len(windows) >= 14:
                    st.warning("You can protect up to 14 periods per plan.")
                elif (day, start, end) in windows:
                    st.info("This period is already included.")
                else:
                    st.session_state["life_windows"] = windows + ((day, start, end),)
                    st.session_state.pop("life_preview", None)
                    st.rerun()
        with clear:
            if st.button("Clear periods", key="life_clear_windows"):
                st.session_state.pop("life_windows", None)
                st.session_state.pop("life_preview", None)
                st.rerun()
        windows = tuple(st.session_state.get("life_windows", ()))
        if windows:
            st.markdown("**Time to protect**")
            for index, (d, a_min, b_min) in enumerate(windows):
                label, remove = st.columns([5, 1], gap="small")
                label.caption(f"{d:%A %d %b} · {format_time(a_min)}–{format_time(b_min)}")
                with remove:
                    if st.button("Remove", key=f"life_remove_{index}"):
                        st.session_state["life_windows"] = tuple(
                            w for i, w in enumerate(windows) if i != index
                        )
                        st.session_state.pop("life_preview", None)
                        st.rerun()
        if st.button("Preview free time", key="life_preview_button", type="primary"):
            st.session_state.pop("life_preview", None)
            if not windows and start >= end:
                st.warning("The finish time must be after the start time.")
            else:
                if not windows:
                    windows = ((day, start, end),)
                    st.session_state["life_windows"] = windows
                try:
                    profile = load_study_dna(db_path)
                    required = required_task_ids(db_path, list_tasks(db_path))
                    preview = preview_time_protection_many(
                        snapshot,
                        now,
                        windows,
                        dna=profile,
                        required_ids=required,
                        gap_minutes=get_break_minutes(db_path),
                    )
                except ValueError as error:
                    st.warning(str(error))
                except (sqlite3.Error, OSError):
                    logging.exception("Couldn't preview personal time")
                    st.error("Couldn't load planning data. No changes were saved.")
                else:
                    st.session_state["life_preview"] = (
                        (snapshot.fingerprint, windows),
                        preview,
                    )
        identity = (snapshot.fingerprint, windows)
        cached = st.session_state.get("life_preview")
        if not cached or cached[0] != identity:
            st.caption("Preview your changes before saving.")
            return
        preview = cached[1]
        with st.container(border=True):
            before_set, after_set = set(preview.before), set(preview.revision.slots)
            moved = tuple(sorted(before_set - after_set, key=lambda item: (item.day, item.start)))
            if preview.feasible:
                st.markdown("**Your protected time is possible.**")
                st.caption(
                    f"{len(windows)} protected period(s) · {len(moved)} study block(s) move."
                )
            else:
                st.warning(preview.explanation)
            labels = {step.id: step.task_title for step in snapshot.steps}
            if moved and preview.feasible:
                st.markdown("**Only these study sessions move:**")
                for old in moved:
                    replacement = sorted(
                        (new for new in after_set - before_set if new.step_id == old.step_id),
                        key=lambda block: (block.day, block.start),
                    )
                    st.caption(
                        f"**{labels.get(old.step_id, 'Study')}**  \n"
                        f"{format_slot(old)} → "
                        + ", ".join(format_slot(part) for part in replacement)
                    )
            elif preview.feasible:
                st.caption("No study sessions need moving.")
            approve, cancel = st.columns(2)
            with approve:
                if st.button(
                    "Save changes",
                    type="primary",
                    disabled=not preview.feasible,
                    key="life_approve_button",
                ):
                    try:
                        accept_time_protection(db_path, preview, datetime.now())
                    except (StaleProposalError, ValueError) as error:
                        st.error(str(error))
                    except (sqlite3.Error, OSError):
                        logging.exception("Couldn't save protected time")
                        st.error("Nothing was saved. Your calendar is unchanged.")
                    else:
                        st.session_state.pop("life_preview", None)
                        st.session_state.pop("life_windows", None)
                        st.session_state.pop("goal_previews", None)
                        st.session_state["calendar_message"] = "Personal time protected"
                        st.rerun()
            with cancel:
                if st.button("Cancel", key="life_cancel_button"):
                    st.session_state.pop("life_preview", None)
                    st.rerun()
