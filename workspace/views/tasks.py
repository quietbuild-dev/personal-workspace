"""First vertical slice: validate, save, and list tasks."""

import logging
import sqlite3
from datetime import date

import streamlit as st

from workspace.models import TaskDraft
from workspace.repository import DEFAULT_DB_PATH, create_task, initialize_database, list_tasks

st.title("Tasks & Projects")
st.caption("Keep your commitments in one place.")

try:
    initialize_database()
except (sqlite3.Error, OSError):
    logging.exception("Could not initialize task storage")
    st.error("Could not open task storage. Check that the project's data folder is writable.")
    st.stop()

with st.form("new_task"):
    st.subheader("Add a task")
    title = st.text_input("Title", max_chars=120)
    category = st.text_input("Category", value="Personal", max_chars=40)
    left, right = st.columns(2)
    with left:
        priority = st.selectbox("Priority", ["Low", "Medium", "High"], index=1)
        minutes = st.number_input("Estimated minutes", min_value=1, value=60, step=1)
    with right:
        has_deadline = st.checkbox("This task has a deadline")
        deadline = st.date_input("Deadline date (used only if checked)", value=date.today())
    submitted = st.form_submit_button("Save task", type="primary")

if submitted:
    try:
        draft = TaskDraft(
            title=title,
            category=category,
            deadline=deadline if has_deadline else None,
            priority={"Low": 1, "Medium": 2, "High": 3}[priority],
            estimate_minutes=minutes,
        )
        create_task(DEFAULT_DB_PATH, draft)
    except ValueError as error:
        st.error(str(error))
    except (sqlite3.Error, OSError):
        logging.exception("Could not save task")
        st.error("Your task could not be saved. Your form entries are still here; try again.")
    else:
        st.success("Task saved.")

st.subheader("Your tasks")
try:
    tasks = list_tasks()
except (sqlite3.Error, OSError):
    logging.exception("Could not load tasks")
    st.error("Could not load your tasks. Check the terminal for details.")
    st.stop()

if tasks:
    st.dataframe(
        [
            {
                "Title": task.title,
                "Category": task.category,
                "Priority": {1: "Low", 2: "Medium", 3: "High"}[task.priority],
                "Deadline": task.deadline.isoformat() if task.deadline else "No deadline",
                "Remaining minutes": task.remaining_minutes,
                "Status": task.status.capitalize(),
            }
            for task in tasks
        ],
        hide_index=True,
        use_container_width=True,
    )
else:
    st.info("No tasks yet. Add your first task above.")
