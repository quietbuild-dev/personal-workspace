"""Explicit, editable confirmation UI for offline natural-language task capture."""

import logging
import sqlite3
from datetime import date

import streamlit as st

from workspace.models import TaskDraft
from workspace.quick_tasks import create_quick_task
from workspace.smart_capture import parse_task_text
from workspace.study_dna import set_required


def render_smart_capture(categories, db_path) -> None:
    with st.expander("Smart capture · Describe a task", expanded=False):
        st.caption(
            "Try: Prepare for my algorithms exam, 6 hours, due December 3, high priority. "
            "Everything is editable before saving. Parsing works offline."
        )
        input_revision = st.session_state.get("capture_input_revision", 0)
        raw = st.text_area(
            "Describe your task",
            placeholder="Algorithms exam, 6 hours, due December 3, high priority",
            height=75,
            key=f"capture_raw_input_{input_revision}",
        )
        if st.button("Fill task details", key="capture_parse"):
            try:
                captured = parse_task_text(raw, date.today(), categories)
            except ValueError as error:
                st.error(str(error))
                st.session_state.pop("capture_parsed", None)
            else:
                st.session_state["capture_parsed"] = captured
                st.session_state["capture_parsed_input"] = raw
                st.session_state["capture_revision"] = (
                    st.session_state.get("capture_revision", 0) + 1
                )
        captured = st.session_state.get("capture_parsed")
        if captured is None:
            return
        if raw != st.session_state.get("capture_parsed_input"):
            st.info("Text changed. Click Fill task details again to refresh the preview.")
            return
        st.markdown("**Review before saving**")
        for note in captured.notes:
            st.info(note)
        revision = st.session_state.get("capture_revision", 0)
        possible = list(dict.fromkeys((*categories, captured.category, "Personal", "University")))
        with st.form(f"capture_confirm_{revision}"):
            title = st.text_input(
                "Task name", value=captured.title, max_chars=120,
                key=f"capture_name_{revision}",
            )
            a, b = st.columns(2, gap="small")
            with a:
                category = st.selectbox(
                    "Category", possible, index=possible.index(captured.category),
                    key=f"capture_category_{revision}",
                )
            with b:
                priority = st.selectbox(
                    "Priority", ["Low", "Medium", "High"], index=captured.priority - 1,
                    key=f"capture_priority_{revision}",
                )
            a, b = st.columns(2, gap="small")
            with a:
                hours = st.number_input(
                    "Estimated hours", min_value=0.02, max_value=2000.0,
                    value=round(captured.estimate_minutes / 60, 2),
                    step=0.25, key=f"capture_hours_{revision}",
                )
            with b:
                has_due = st.checkbox(
                    "Has deadline", value=captured.deadline is not None,
                    key=f"capture_has_due_{revision}",
                )
                due = st.date_input(
                    "Deadline (used if checked)", value=captured.deadline or date.today(),
                    format="DD/MM/YYYY",
                    key=f"capture_due_{revision}",
                )
            schedule = st.checkbox(
                "Add study time to my calendar", value=True,
                key=f"capture_schedule_{revision}",
            )
            must_finish = st.checkbox(
                "Must finish by deadline", value=True,
                key=f"capture_required_{revision}",
            )
            confirmed = st.form_submit_button("Confirm and save task", type="primary")
        if not confirmed:
            st.caption("No task is created until you confirm.")
            return
        try:
            minutes = int(round(float(hours) * 60))
            draft = TaskDraft(
                title,
                category,
                due if has_due else None,
                {"Low": 1, "Medium": 2, "High": 3}[priority],
                minutes,
            )
            task_id = create_quick_task(db_path, draft, schedule=schedule)
        except (ValueError, sqlite3.Error, OSError) as error:
            logging.exception("Could not save smart-captured task")
            st.error(f"Could not create the task: {error}")
            return
        message = "Smart-captured task saved."
        if draft.deadline is not None and not must_finish:
            try:
                set_required(db_path, task_id, False)
            except (ValueError, sqlite3.Error, OSError):
                logging.exception("Could not save the optional task requirement flag")
                message = (
                    "Task saved, but it remains required by default. "
                    "Change its requirement in Tasks."
                )
        st.session_state.pop("capture_parsed", None)
        st.session_state.pop("capture_parsed_input", None)
        st.session_state["capture_input_revision"] = input_revision + 1
        st.session_state["newly_added_task"] = task_id if schedule else None
        st.session_state["home_message"] = message
        st.rerun()
