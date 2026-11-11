"""Task creation, editing, completion, and reopening."""

import logging
import sqlite3
from datetime import date

import streamlit as st

from workspace.models import TaskDraft
from workspace.repository import (
    DEFAULT_DB_PATH,
    create_task,
    initialize_database,
    list_tasks,
    update_task,
)

st.title("Tasks & Projects")
st.caption("Keep your commitments in one place.")

notice = st.session_state.pop("task_notice", None)
if notice:
    st.success(notice)

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
        width="stretch",
    )
else:
    st.info("No tasks yet. Add your first task above.")

if tasks:
    st.subheader("Edit a task")
    by_id = {task.id: task for task in tasks}
    selected_id = st.selectbox(
        "Choose a task",
        options=list(by_id),
        format_func=lambda task_id: f"#{task_id} · {by_id[task_id].title}",
        key="selected_task_id",
    )
    selected = by_id[selected_id]
    # A new form revision reloads saved values after completion or an edit.
    revision = st.session_state.get("task_edit_revision", 0)
    prefix = f"edit_{selected.id}_{revision}"
    with st.form(prefix):
        edit_title = st.text_input("Title", value=selected.title, key=f"{prefix}_title")
        edit_category = st.text_input(
            "Category", value=selected.category, key=f"{prefix}_category"
        )
        left, right = st.columns(2)
        with left:
            edit_priority = st.selectbox(
                "Priority", ["Low", "Medium", "High"], index=selected.priority - 1,
                key=f"{prefix}_priority",
            )
            edit_estimate = st.number_input(
                "Estimated minutes", min_value=1, value=selected.estimate_minutes, step=1,
                key=f"{prefix}_estimate",
            )
            edit_remaining = st.number_input(
                "Remaining minutes", min_value=0, value=selected.remaining_minutes, step=1,
                key=f"{prefix}_remaining",
            )
        with right:
            edit_has_deadline = st.checkbox(
                "This task has a deadline", value=selected.deadline is not None,
                key=f"{prefix}_has_deadline",
            )
            edit_deadline = st.date_input(
                "Deadline date (used only if checked)", value=selected.deadline or date.today(),
                key=f"{prefix}_deadline",
            )
            st.caption(f"Current status: {selected.status.capitalize()}")
        st.caption(
            "Update remaining minutes after working. Zero means completed. "
            "To reopen a completed task, enter positive remaining minutes and save. "
            "Increase the estimate first if more time is needed."
        )
        save_edit = st.form_submit_button("Save changes", type="primary")
        complete = False
        if selected.status == "pending":
            complete = st.form_submit_button("Mark completed")

    if save_edit or complete:
        try:
            edit_draft = TaskDraft(
                title=edit_title,
                category=edit_category,
                deadline=edit_deadline if edit_has_deadline else None,
                priority={"Low": 1, "Medium": 2, "High": 3}[edit_priority],
                estimate_minutes=edit_estimate,
            )
            updated = update_task(
                DEFAULT_DB_PATH, selected.id, edit_draft, 0 if complete else edit_remaining
            )
        except ValueError as error:
            st.error(str(error))
        except (sqlite3.Error, OSError):
            logging.exception("Could not update task")
            st.error("Your changes could not be saved. Your entries are still here; try again.")
        else:
            if updated.status == "completed" and selected.status == "pending":
                message = "Task completed."
            elif updated.status == "pending" and selected.status == "completed":
                message = "Task reopened."
            else:
                message = "Changes saved."
            st.session_state["task_notice"] = message
            st.session_state["task_edit_revision"] = revision + 1
            st.rerun()
