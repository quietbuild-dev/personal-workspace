"""Task creation, filtering, fast status actions, editing and confirmed deletion."""

import logging
import sqlite3
from datetime import date

import streamlit as st

from workspace.metrics import format_minutes
from workspace.models import TaskDraft
from workspace.repository import (
    DEFAULT_DB_PATH,
    create_task,
    delete_task,
    initialize_database,
    list_tasks,
    set_task_completion,
    update_task,
)

st.title("Tasks & Projects")
st.caption("Keep your commitments in one place.")

notice = st.session_state.pop("task_notice", None)
if notice:
    st.success(notice)

try:
    initialize_database(DEFAULT_DB_PATH)
except (sqlite3.Error, OSError):
    logging.exception("Could not initialize task storage")
    st.error("Could not open task storage. Check that the project's data folder is writable.")
    st.stop()

# Change widget keys only after a successful save. Invalid entries stay on screen.
new_revision = st.session_state.get("new_task_revision", 0)
new_prefix = f"new_{new_revision}"
with st.form(f"new_task_{new_revision}", clear_on_submit=False):
    st.subheader("Quick add")
    main_fields = st.columns([2.6, 1.4, 1], gap="small")
    with main_fields[0]:
        title = st.text_input(
            "Title",
            max_chars=120,
            placeholder="e.g. Prepare economics practice questions",
            key=f"{new_prefix}_title",
        )
    with main_fields[1]:
        category = st.text_input(
            "Category / course",
            value="Personal",
            max_chars=40,
            key=f"{new_prefix}_category",
        )
    with main_fields[2]:
        minutes = st.number_input(
            "Estimated min",
            min_value=1,
            value=60,
            step=1,
            key=f"{new_prefix}_minutes",
        )
    with st.expander("Optional: priority and deadline"):
        left, right = st.columns(2)
        with left:
            priority = st.selectbox(
                "Priority",
                ["Low", "Medium", "High"],
                index=1,
                key=f"{new_prefix}_priority",
            )
        with right:
            has_deadline = st.checkbox("This task has a deadline", key=f"{new_prefix}_has_deadline")
            deadline = st.date_input(
                "Deadline date (used if checked)",
                value=date.today(),
                key=f"{new_prefix}_deadline",
            )
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
        st.session_state["task_notice"] = "Task saved. The form is ready for another task."
        st.session_state["new_task_revision"] = new_revision + 1
        st.rerun()

st.subheader("Your tasks")
try:
    tasks = list_tasks(DEFAULT_DB_PATH)
except (sqlite3.Error, OSError):
    logging.exception("Could not load tasks")
    st.error("Could not load your tasks. Check the terminal for details.")
    st.stop()

visible_tasks = []
if tasks:
    filter_left, filter_right = st.columns(2)
    with filter_left:
        status_filter = st.selectbox("Status", ["All", "Open", "Completed"])
    with filter_right:
        categories = ["All categories"] + sorted({task.category for task in tasks})
        category_filter = st.selectbox("Category filter", categories)
    visible_tasks = [
        task
        for task in tasks
        if (
            status_filter == "All"
            or task.status == ("pending" if status_filter == "Open" else "completed")
        )
        and (category_filter == "All categories" or task.category == category_filter)
    ]
    if not visible_tasks:
        st.info("No tasks match your filters. Change a filter to view other tasks.")
    else:
        st.caption(
            "Complete or reopen directly here. Reopening restores the full estimated time; "
            "use Edit a task to adjust the actual remaining minutes."
        )
        for task in visible_tasks:
            with st.container(border=True):
                details, status_col, action_col = st.columns([4.3, 1.2, 1.2], gap="small")
                with details:
                    st.markdown(f"**{task.title}**")
                    due = f"Due {task.deadline:%d %b %Y}" if task.deadline else "No deadline"
                    priority_label = {1: "Low", 2: "Medium", 3: "High"}[task.priority]
                    st.caption(f"{task.category} · {priority_label} priority · {due}")
                with status_col:
                    st.markdown("**Done**" if task.status == "completed" else "**Open**")
                    st.caption(format_minutes(task.remaining_minutes) + " left")
                with action_col:
                    completing = task.status == "pending"
                    clicked = st.button(
                        "Complete" if completing else "Reopen",
                        key=f"quick_{'complete' if completing else 'reopen'}_{task.id}",
                        width="stretch",
                    )
                    if clicked:
                        try:
                            set_task_completion(DEFAULT_DB_PATH, task.id, completed=completing)
                        except ValueError as error:
                            st.error(str(error))
                        except (sqlite3.Error, OSError):
                            logging.exception("Could not update task completion")
                            st.error("Could not update this task. Try again.")
                        else:
                            st.session_state["task_notice"] = (
                                "Task completed."
                                if completing
                                else "Task reopened with its full estimated time."
                            )
                            st.session_state["task_edit_revision"] = (
                                st.session_state.get("task_edit_revision", 0) + 1
                            )
                            st.rerun()
else:
    st.info("No tasks yet. Add your first task above.")

if visible_tasks:
    st.subheader("Edit a task")
    by_id = {task.id: task for task in visible_tasks}
    if st.session_state.get("selected_task_id") not in by_id:
        st.session_state.pop("selected_task_id", None)
    selected_id = st.selectbox(
        "Choose a task",
        options=list(by_id),
        format_func=lambda task_id: f"#{task_id} · {by_id[task_id].title}",
        key="selected_task_id",
    )
    selected = by_id[selected_id]
    revision = st.session_state.get("task_edit_revision", 0)
    prefix = f"edit_{selected.id}_{revision}"
    with st.form(prefix):
        edit_title = st.text_input("Title", value=selected.title, key=f"{prefix}_title")
        edit_category = st.text_input("Category", value=selected.category, key=f"{prefix}_category")
        left, right = st.columns(2)
        with left:
            edit_priority = st.selectbox(
                "Priority",
                ["Low", "Medium", "High"],
                index=selected.priority - 1,
                key=f"{prefix}_priority",
            )
            edit_estimate = st.number_input(
                "Estimated minutes",
                min_value=1,
                value=selected.estimate_minutes,
                step=1,
                key=f"{prefix}_estimate",
            )
            edit_remaining = st.number_input(
                "Remaining minutes",
                min_value=0,
                value=selected.remaining_minutes,
                step=1,
                key=f"{prefix}_remaining",
            )
        with right:
            edit_has_deadline = st.checkbox(
                "This task has a deadline",
                value=selected.deadline is not None,
                key=f"{prefix}_has_deadline",
            )
            edit_deadline = st.date_input(
                "Deadline date (used only if checked)",
                value=selected.deadline or date.today(),
                key=f"{prefix}_deadline",
            )
            st.caption(f"Current status: {selected.status.capitalize()}")
        st.caption(
            "Update remaining minutes after working. Zero means completed. "
            "To reopen a completed task with a custom duration, enter positive remaining "
            "minutes and save. Increase the estimate first if more time is needed."
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

    st.divider()
    with st.container(border=True):
        st.subheader("Delete task")
        st.caption(
            "Deletion is permanent. It also removes this task from the next plan "
            "and all dashboard totals; it does not affect other tasks."
        )
        confirmation_key = f"delete_confirm_{selected.id}"
        if st.session_state.get("last_selected_for_delete") != selected.id:
            st.session_state[confirmation_key] = False
            st.session_state["last_selected_for_delete"] = selected.id
        confirmed = st.checkbox(
            f"I confirm permanent deletion of ‘{selected.title}’ (#{selected.id}).",
            key=confirmation_key,
        )
        if st.button("Delete task permanently", disabled=not confirmed):
            try:
                delete_task(DEFAULT_DB_PATH, selected.id)
            except ValueError as error:
                st.error(str(error))
            except (sqlite3.Error, OSError):
                logging.exception("Could not delete task")
                st.error("Deletion failed; your task was not intentionally removed.")
            else:
                st.session_state["task_notice"] = "Task deleted."
                st.session_state.pop("selected_task_id", None)
                st.session_state.pop("last_selected_for_delete", None)
                st.rerun()

    st.divider()
    st.subheader("Break this task into study and life steps")
    st.caption(
        "Checklist steps track small actions; timed steps are scheduled individually in the "
        "hourly calendar. Timed work is measured separately from the original parent estimate."
    )
    try:
        from workspace.advanced_repository import (
            add_step,
            delete_step,
            load_snapshot,
            rename_step,
            set_checklist_done,
            set_timed_remaining,
        )

        detailed = load_snapshot(DEFAULT_DB_PATH)
    except (sqlite3.Error, OSError):
        logging.exception("Could not load subtasks")
        st.error("Could not load this task's detailed steps.")
    else:
        task_steps = [step for step in detailed.steps if step.task_id == selected.id]
        if selected.status == "pending":
            with st.form(f"new_step_{selected.id}", clear_on_submit=True):
                title_step = st.text_input("Step title", max_chars=120)
                kind_label = st.selectbox("Type", ["Timed study / work", "Simple checklist"])
                step_minutes = st.number_input(
                    "Estimated minutes (timed steps only)", min_value=1, value=45, step=15
                )
                step_save = st.form_submit_button("Add step")
            if step_save:
                try:
                    add_step(
                        DEFAULT_DB_PATH,
                        selected.id,
                        title_step,
                        "timed" if kind_label == "Timed study / work" else "checklist",
                        int(step_minutes) if kind_label == "Timed study / work" else 0,
                    )
                except ValueError as error:
                    st.error(str(error))
                except (sqlite3.Error, OSError):
                    logging.exception("Could not add study step")
                    st.error("Step could not be saved.")
                else:
                    st.session_state["task_notice"] = "Step added. Review the hourly planner."
                    st.rerun()
        else:
            st.caption("Reopen this task to add more steps.")

        if task_steps:
            st.markdown("**Saved steps**")
            for step in task_steps:
                with st.container(border=True):
                    if step.kind == "checklist":
                        cols = st.columns([5, 1.5])
                        with cols[0]:
                            st.write(f"{'Completed' if step.checked else 'To do'} · {step.title}")
                        with cols[1]:
                            if st.button(
                                "Undo" if step.checked else "Check off",
                                key=f"toggle_checklist_{step.id}",
                            ):
                                try:
                                    set_checklist_done(DEFAULT_DB_PATH, step.id, not step.checked)
                                except (ValueError, sqlite3.Error, OSError) as error:
                                    st.error(str(error))
                                else:
                                    st.session_state["task_notice"] = "Checklist updated."
                                    st.rerun()
                    else:
                        left, remaining_col, save_col = st.columns([4, 1.6, 1.3])
                        with left:
                            st.write(f"**{step.title}**")
                            st.caption(
                                f"Timed step · {step.remaining_minutes} of "
                                f"{step.estimate_minutes} min remaining"
                            )
                        with remaining_col:
                            new_remain = st.number_input(
                                "Minutes left",
                                min_value=0,
                                max_value=step.estimate_minutes,
                                value=step.remaining_minutes,
                                step=1,
                                key=f"step_remaining_{step.id}",
                            )
                        with save_col:
                            if st.button(
                                "Save time",
                                key=f"save_step_{step.id}",
                                disabled=new_remain == step.remaining_minutes,
                            ):
                                try:
                                    set_timed_remaining(DEFAULT_DB_PATH, step.id, int(new_remain))
                                except (ValueError, sqlite3.Error, OSError) as error:
                                    st.error(str(error))
                                else:
                                    st.session_state["task_notice"] = (
                                        "Step work updated. Any affected saved sessions "
                                        "need review."
                                    )
                                    st.rerun()
                with st.expander(f"Edit or delete step #{step.id}"):
                    with st.form(f"rename_step_{step.id}"):
                        new_step_title = st.text_input(
                            "Rename step", value=step.title, key=f"rename_title_{step.id}"
                        )
                        rename_save = st.form_submit_button("Save step title")
                    if rename_save:
                        try:
                            rename_step(DEFAULT_DB_PATH, step.id, new_step_title)
                        except (ValueError, sqlite3.Error, OSError) as error:
                            st.error(str(error))
                        else:
                            st.session_state["task_notice"] = "Step renamed."
                            st.rerun()
                    confirm_delete_step = st.checkbox(
                        "Permanently remove this step and its calendar sessions",
                        key=f"confirm_step_delete_{step.id}",
                    )
                    if st.button(
                        "Delete step",
                        key=f"delete_step_{step.id}",
                        disabled=not confirm_delete_step,
                    ):
                        try:
                            delete_step(DEFAULT_DB_PATH, step.id)
                        except (ValueError, sqlite3.Error, OSError) as error:
                            st.error(str(error))
                        else:
                            st.session_state["task_notice"] = "Step and its sessions deleted."
                            st.rerun()
            completed_steps = sum(
                (step.checked if step.kind == "checklist" else step.remaining_minutes == 0)
                for step in task_steps
            )
            st.caption(
                f"{completed_steps} of {len(task_steps)} detailed steps completed. "
                "Complete the parent task separately after its steps are finished."
            )
        else:
            st.caption("No steps yet. A parent can contain both checklist and timed steps.")
