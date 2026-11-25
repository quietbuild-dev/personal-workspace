"""Dedicated Tasks page sharing Home's tested task and checklist controls."""

import logging
import sqlite3
from datetime import datetime

import streamlit as st

from workspace.advanced_repository import list_task_categories, list_task_due_times
from workspace.overview import load_overview
from workspace.quick_tasks import initialize_quick_tasks
from workspace.repository import DEFAULT_DB_PATH
from workspace.theme import stat_card
from workspace.views.home import _new_task, _suggestion, _task_rows
from workspace.views.smart_capture import render_smart_capture


def main() -> None:
    now = datetime.now()
    st.markdown(
        '<div class="pw-hero"><div class="pw-eyebrow">Your workspace</div>'
        "<h1>Tasks & assignments</h1>"
        "</div>",
        unsafe_allow_html=True,
    )
    try:
        initialize_quick_tasks(DEFAULT_DB_PATH)
        overview = load_overview(DEFAULT_DB_PATH, now.date())
        categories = list_task_categories(DEFAULT_DB_PATH)
        due_times = list_task_due_times(DEFAULT_DB_PATH)
    except (ValueError, sqlite3.Error, OSError):
        logging.exception("Unable to load the task board")
        st.error("Couldn't load your tasks. Check the database and restart.")
        st.stop()
        return

    active = [task for task in overview.tasks if task.status == "pending"]
    completed = len(overview.tasks) - len(active)
    high = sum(task.priority == 3 for task in active)
    a, b, c = st.columns(3, gap="medium")
    with a:
        st.markdown(
            stat_card("Open tasks", str(len(active)), "Assignments and to-dos"),
            unsafe_allow_html=True,
        )
    with b:
        st.markdown(
            stat_card("High priority", str(high), "Among open tasks"), unsafe_allow_html=True
        )
    with c:
        st.markdown(
            stat_card("Completed", str(completed), "Saved in your workspace"),
            unsafe_allow_html=True,
        )

    message = st.session_state.pop("home_message", None)
    if message:
        st.success(message)
    _suggestion(overview, now, st.session_state.get("newly_added_task"))
    render_smart_capture(categories, DEFAULT_DB_PATH)
    with st.expander("+ Add a task", expanded=False):
        _new_task(categories)
    selected = st.session_state.get("task_board_selected_task")
    if selected is not None:
        if st.button("← Back to all tasks", key="task_board_back"):
            st.session_state.pop("task_board_selected_task", None)
            st.session_state.pop("open_task_details", None)
            st.rerun()
    _task_rows(overview, due_times, categories, selected_task_id=selected)


if __name__ == "__main__":
    main()
