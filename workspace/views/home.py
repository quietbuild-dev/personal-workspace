"""Home: a task list and today's agenda, not an engineering dashboard."""

import logging
import sqlite3
from datetime import date, datetime

import streamlit as st

from workspace.advanced_planner import format_time
from workspace.advanced_repository import (
    StaleProposalError,
    accept_revision,
    add_step,
    list_task_categories,
    list_task_due_times,
    set_checklist_done,
)
from workspace.manual_planning import move_proposed_block
from workspace.models import TaskDraft
from workspace.overview import load_overview
from workspace.planning_insights import compare_plans
from workspace.quick_tasks import (
    create_quick_task,
    edit_quick_task,
    initialize_quick_tasks,
    toggle_quick_task,
)
from workspace.repository import DEFAULT_DB_PATH, delete_task
from workspace.simple_planning import proposal_notice

PRIORITIES = {"Low": 1, "Medium": 2, "High": 3}


def pretty_duration(minutes: int) -> str:
    hours, remaining = divmod(minutes, 60)
    if hours and remaining:
        return f"{hours}h {remaining}m"
    if hours:
        return f"{hours}h"
    return f"{remaining}m"


def due_display(task, due_times, today: date) -> str:
    if task.deadline is None:
        return "No deadline"
    delta = (task.deadline - today).days
    label = (
        "Overdue"
        if delta < 0
        else "Today"
        if delta == 0
        else ("Tomorrow" if delta == 1 else f"{task.deadline:%d/%m/%Y}")
    )
    minute = due_times.get(task.id)
    return f"Due {label}" + (f" at {format_time(minute)}" if minute is not None else "")


def _apply(action, success: str) -> None:
    try:
        action()
    except (ValueError, StaleProposalError) as error:
        st.error(str(error))
    except (sqlite3.Error, OSError):
        logging.exception("Home action failed")
        st.error("Couldn't save that change. Your existing data is unchanged.")
    else:
        st.session_state["home_message"] = success
        st.rerun()


def _category_input(categories: tuple[str, ...], key: str, *, selected="Personal") -> str:
    options = list(categories)
    if selected not in options:
        options.insert(0, selected)
    options.append("+ New category")
    choice = st.selectbox(
        "Category",
        options,
        index=options.index(selected),
        key=f"{key}_category_choice",
    )
    if choice == "+ New category":
        return st.text_input(
            "New category",
            placeholder="e.g. Student association",
            max_chars=40,
            key=f"{key}_new_category",
        )
    return choice


def _duration_input(key: str, *, minutes: int = 60) -> int:
    a, b = st.columns(2, gap="small")
    with a:
        hours = st.number_input(
            "Hours",
            min_value=0,
            max_value=1000,
            value=minutes // 60,
            step=1,
            key=f"{key}_hours",
        )
    with b:
        mins = st.number_input(
            "Minutes",
            min_value=0,
            max_value=59,
            value=minutes % 60,
            step=5,
            key=f"{key}_minutes",
        )
    return int(hours) * 60 + int(mins)


def _new_task(categories: tuple[str, ...]) -> None:
    rev = st.session_state.get("new_task_version", 0)
    with st.container(border=True):
        st.subheader("Add a task")
        category = _category_input(categories, f"new_{rev}")
        with st.form(f"new_task_{rev}"):
            title = st.text_input("Task name", placeholder="e.g. Finish economics assignment")
            left, right = st.columns(2, gap="small")
            with left:
                due = st.date_input(
                    "Deadline (optional)",
                    value=None,
                    format="DD/MM/YYYY",
                    key=f"new_due_{rev}",
                )
            with right:
                due_time = st.time_input(
                    "Due by (optional)",
                    value=None,
                    step=900,
                    key=f"new_due_time_{rev}",
                )
            left, right = st.columns(2, gap="small")
            with left:
                st.caption("Estimated time")
                estimate = _duration_input(f"new_{rev}")
            with right:
                priority = st.selectbox("Priority", list(PRIORITIES), index=1)
            submitted = st.form_submit_button("Save task", type="primary")
        if submitted:

            def save():
                new_id = create_quick_task(
                    DEFAULT_DB_PATH,
                    TaskDraft(title, category, due, PRIORITIES[priority], estimate),
                    due_minute=(due_time.hour * 60 + due_time.minute) if due_time else None,
                )
                st.session_state["newly_added_task"] = new_id
                st.session_state["new_task_version"] = rev + 1
                st.session_state.pop("home_adjusted_proposal", None)

            _apply(save, "Task saved.")


def _suggestion(overview, now: datetime, newly_added: int | None) -> None:
    if not newly_added:
        return
    task = next((task for task in overview.tasks if task.id == newly_added), None)
    if not task:
        return
    snapshot = overview.advanced
    if not snapshot.windows and not snapshot.budgets:
        st.info(
            f"{task.title} was saved. To get study-time suggestions, set your "
            "preferred study time once in Calendar."
        )
        st.page_link("workspace/views/week.py", label="Set study preferences")
        return
    notice = proposal_notice(snapshot, now)
    custom = st.session_state.get("home_adjusted_proposal")
    revision = custom if custom and custom.fingerprint == snapshot.fingerprint else notice.revision
    proposed = [
        slot
        for slot in revision.slots
        if any(step.id == slot.step_id and step.task_id == newly_added for step in snapshot.steps)
    ]
    if not proposed:
        st.info(
            f"{task.title} was saved, but the planner couldn't find an eligible time "
            "under the current preferences. Try adjusting your Calendar preferences."
        )
        return
    with st.container(border=True):
        st.markdown(f"**Suggested times for {task.title}**")
        for slot in proposed[:4]:
            st.write(f"{slot.day:%a %d %b} · {format_time(slot.start)}–{format_time(slot.end)}")
        if len(proposed) > 4:
            st.caption(f"+{len(proposed) - 4} more suggested blocks")
        if notice.removed_sessions:
            st.caption(
                f"Accepting this proposal would also move/remove "
                f"{notice.removed_sessions} other study block(s). Review the full plan first."
            )
        a, b = st.columns(2, gap="small")
        if a.button("Accept proposed week", type="primary", key="home_accept_suggestion"):

            def accept():
                accept_revision(DEFAULT_DB_PATH, revision, datetime.now())
                st.session_state.pop("newly_added_task", None)
                st.session_state.pop("home_adjusted_proposal", None)

            _apply(accept, "Suggested plan accepted. Your calendar is updated.")
        if b.button("Not now", key="home_dismiss_suggestion"):
            st.session_state.pop("newly_added_task", None)
            st.session_state.pop("home_adjusted_proposal", None)
            st.rerun()
        with st.popover("Change a suggested time"):
            from workspace.advanced_planner import format_time as clock
            from workspace.views.week import TIME_CHOICES, _as_minute

            choices = [
                (i, slot)
                for i, slot in enumerate(revision.slots)
                if any(s.id == slot.step_id and s.task_id == newly_added for s in snapshot.steps)
            ]
            choice = st.selectbox(
                "Study block",
                range(len(choices)),
                format_func=lambda i: (
                    f"{choices[i][1].day:%a %d %b} "
                    f"{clock(choices[i][1].start)}–{clock(choices[i][1].end)}"
                ),
            )
            with st.form("adjust_home_suggestion"):
                new_day = st.date_input(
                    "Move to",
                    value=choices[choice][1].day,
                    min_value=now.date(),
                    max_value=revision.sunday,
                    format="DD/MM/YYYY",
                )
                new_start = st.selectbox("Start time", TIME_CHOICES[:-1], index=18)
                if st.form_submit_button("Preview new time"):
                    try:
                        adjusted = move_proposed_block(
                            snapshot,
                            revision,
                            choices[choice][0],
                            new_day,
                            _as_minute(new_start),
                            datetime.now(),
                        )
                    except ValueError as error:
                        st.error(str(error))
                    else:
                        st.session_state["home_adjusted_proposal"] = adjusted
                        st.rerun()
        st.page_link("workspace/views/week.py", label="Open calendar")
        st.caption("The saved calendar never changes without your approval.")


def _today(overview, now: datetime) -> None:
    steps = {step.id: step for step in overview.advanced.steps}
    agenda = []
    for event in overview.advanced.events:
        if event.day == now.date():
            agenda.append((event.start, event.end, event.title, event.kind))
    for session in overview.advanced.sessions:
        if session.day == now.date() and session.status == "planned":
            step = steps.get(session.step_id)
            if step:
                label = (
                    step.task_title
                    if step.title == "Focus time"
                    else (f"{step.task_title} · {step.title}")
                )
                agenda.append((session.start, session.end, label, "Study"))
    with st.container(border=True):
        st.subheader("Today's schedule")
        if not agenda:
            st.caption("Nothing scheduled today. Add an event or accept a study suggestion.")
        for start, end, title, kind in sorted(agenda)[:9]:
            st.markdown(f"**{format_time(start)}–{format_time(end)}** · {title}")
            st.caption(kind)
        st.page_link("workspace/views/week.py", label="Open calendar")


def _task_rows(overview, deadline_times: dict[int, int], categories: tuple[str, ...]) -> None:
    st.subheader("Your tasks")
    all_tasks = list(overview.tasks)
    show_done = st.checkbox("Show completed tasks", value=False, key="home_show_done")
    displayed = [task for task in all_tasks if show_done or task.status != "completed"]
    displayed.sort(
        key=lambda t: (t.status == "completed", t.deadline or date.max, -t.priority, t.id)
    )
    if not displayed:
        st.caption("No tasks here. Add your first one above.")
    for task in displayed:
        timed = [
            step
            for step in overview.advanced.steps
            if step.task_id == task.id and step.kind == "timed"
        ]
        actually_left = (
            sum(step.remaining_minutes for step in timed) if timed else task.remaining_minutes
        )
        with st.container(border=False):
            name, action, partial, details = st.columns([5, 1.1, 1.1, 1.3], gap="small")
            with name:
                st.markdown(f"**{task.title}**")
                st.caption(
                    f"{task.category} · {due_display(task, deadline_times, date.today())}"
                    f" · {pretty_duration(actually_left)} left"
                )
            with action:
                if st.button(
                    "Done" if task.status == "pending" else "Reopen",
                    key=f"done_{task.id}",
                    width="stretch",
                ):
                    _apply(
                        lambda t=task: toggle_quick_task(
                            DEFAULT_DB_PATH, t.id, t.status == "pending"
                        ),
                        "Task progress updated.",
                    )
            with partial:
                if task.status == "pending" and st.button(
                    "Partly",
                    key=f"partial_{task.id}",
                    width="stretch",
                ):
                    st.session_state["partial_task_id"] = (
                        None if st.session_state.get("partial_task_id") == task.id else task.id
                    )
                    st.rerun()
            with details:
                if st.button("Details", key=f"details_{task.id}", width="stretch"):
                    current = st.session_state.get("open_task_details")
                    st.session_state["open_task_details"] = None if current == task.id else task.id
                    st.rerun()
            if st.session_state.get("partial_task_id") == task.id:
                with st.form(f"partial_work_{task.id}"):
                    st.caption("How much of this task is still unfinished?")
                    remaining = _duration_input(
                        f"partial_work_{task.id}", minutes=task.remaining_minutes
                    )
                    if st.form_submit_button("Update remaining work", type="primary"):

                        def save_partial():
                            edit_quick_task(
                                DEFAULT_DB_PATH,
                                task.id,
                                TaskDraft(
                                    task.title,
                                    task.category,
                                    task.deadline,
                                    task.priority,
                                    task.estimate_minutes,
                                ),
                                remaining,
                            )
                            st.session_state.pop("partial_task_id", None)

                        _apply(save_partial, "Progress saved. Your schedule may need review.")
            if st.session_state.get("open_task_details") == task.id:
                _edit_task(overview, categories, deadline_times)
        st.divider()


def _edit_task(overview, categories, deadline_times) -> None:
    task_id = st.session_state.get("open_task_details")
    task = next((task for task in overview.tasks if task.id == task_id), None)
    if task is None:
        return
    steps = [step for step in overview.advanced.steps if step.task_id == task.id]
    timed_remaining = [step.remaining_minutes for step in steps if step.kind == "timed"]
    checklist = [step for step in steps if step.kind == "checklist"]
    with st.container(border=True):
        st.subheader(task.title)
        if st.button("Close", key="close_task_details"):
            st.session_state["open_task_details"] = None
            st.rerun()
        st.markdown("**Checklist**")
        for step in checklist:
            checked = st.checkbox(
                step.title,
                value=step.checked,
                key=f"check_{step.id}",
                disabled=task.status == "completed",
            )
            if checked != step.checked:
                _apply(
                    lambda s=step, value=checked: set_checklist_done(DEFAULT_DB_PATH, s.id, value),
                    "Checklist updated.",
                )
        if task.status == "pending":
            with st.form(f"new_check_{task.id}", clear_on_submit=True):
                label = st.text_input("New checklist item")
                if st.form_submit_button("Add checklist item"):
                    _apply(
                        lambda: add_step(DEFAULT_DB_PATH, task.id, label, "checklist"),
                        "Checklist item added.",
                    )
        st.markdown("**Edit task**")
        rev = st.session_state.get("edit_task_rev", 0)
        category = _category_input(categories, f"edit_{task.id}_{rev}", selected=task.category)
        with st.form(f"edit_task_{task.id}_{rev}"):
            name = st.text_input("Task name", value=task.title, key=f"edit_name_{rev}")
            left, right = st.columns(2, gap="small")
            with left:
                due = st.date_input(
                    "Deadline (optional)",
                    value=task.deadline,
                    format="DD/MM/YYYY",
                    key=f"edit_due_{rev}",
                )
            with right:
                current_due = deadline_times.get(task.id)
                original_time = (
                    None
                    if current_due is None
                    else datetime.min.replace(
                        hour=current_due // 60, minute=current_due % 60
                    ).time()
                )
                due_time = st.time_input(
                    "Due by (optional)",
                    value=original_time,
                    step=900,
                    key=f"edit_time_{rev}",
                )
            left, right = st.columns(2, gap="small")
            with left:
                priority = st.selectbox(
                    "Priority",
                    list(PRIORITIES),
                    index=task.priority - 1,
                    key=f"edit_priority_{rev}",
                )
            with right:
                st.caption("Estimated time")
                estimate = _duration_input(f"edit_estimate_{rev}", minutes=task.estimate_minutes)
                st.caption("Unfinished work")
                remaining = _duration_input(
                    f"edit_remaining_{rev}",
                    minutes=(sum(timed_remaining) if timed_remaining else task.remaining_minutes),
                )
            if st.form_submit_button("Save changes", type="primary"):

                def save():
                    edit_quick_task(
                        DEFAULT_DB_PATH,
                        task.id,
                        TaskDraft(name, category, due, PRIORITIES[priority], estimate),
                        remaining,
                        due_minute=(due_time.hour * 60 + due_time.minute) if due_time else None,
                    )
                    st.session_state["edit_task_rev"] = rev + 1

                _apply(save, "Task updated. Check any revised calendar suggestions.")
        with st.expander("Delete task"):
            confirm = st.checkbox("I understand this also deletes scheduled study blocks")
            if st.button("Delete permanently", disabled=not confirm, key=f"delete_{task.id}"):

                def delete():
                    delete_task(DEFAULT_DB_PATH, task.id)
                    st.session_state.pop("open_task_details", None)

                _apply(delete, "Task deleted.")


def main() -> None:
    now = datetime.now()
    st.title("Today")
    st.caption(f"{now:%A, %d %B %Y} · Your tasks, events and study plans")
    try:
        initialize_quick_tasks(DEFAULT_DB_PATH)
        overview = load_overview(DEFAULT_DB_PATH, now.date())
        categories = list_task_categories(DEFAULT_DB_PATH)
        due_times = list_task_due_times(DEFAULT_DB_PATH)
    except (ValueError, sqlite3.Error, OSError):
        logging.exception("Could not load Home data")
        st.error("Couldn't load your workspace. Check the database and restart.")
        st.stop()
        return
    message = st.session_state.pop("home_message", None)
    if message:
        st.success(message)
    pending = [task for task in overview.tasks if task.status == "pending"]
    st.caption(
        f"{len(pending)} open tasks · "
        f"{sum(bool(t.deadline and t.deadline <= now.date()) for t in pending)} due or overdue"
    )
    newly_added = st.session_state.get("newly_added_task")
    _suggestion(overview, now, newly_added)
    if not newly_added and (overview.advanced.budgets or overview.advanced.windows):
        insight = compare_plans(overview.advanced, now)
        if insight.preserve.risks:
            top = insight.preserve.risks[0]
            urgency = "Already overdue" if top.reason == "overdue" else "Deadline at risk"
            st.warning(
                f"{urgency}: {top.title} · "
                f"{pretty_duration(top.unscheduled_minutes)} could not be fitted "
                f"before {top.deadline:%d/%m}."
            )
            st.page_link("workspace/views/week.py", label="Compare rescue plans")
        elif insight.preserve.changed:
            st.info("A revised plan is available; your accepted calendar is unchanged.")
            st.page_link("workspace/views/week.py", label="Compare plans")
    left, right = st.columns([1.08, 1], gap="medium")
    with left:
        _today(overview, now)
    with right:
        _new_task(categories)
    _task_rows(overview, due_times, categories)


if __name__ == "__main__":
    main()
