"""Home: a task list and today's agenda, not an engineering dashboard."""

import logging
import sqlite3
from datetime import date, datetime, timedelta
from html import escape

import streamlit as st

from workspace.advanced_planner import format_time, week_bounds
from workspace.advanced_repository import (
    StaleProposalError,
    accept_revision,
    add_step,
    list_task_due_times,
    set_checklist_done,
)
from workspace.deadline_guarantees import check_required_coverage
from workspace.home_view_logic import completed_today, due_display, focus_tasks
from workspace.manual_planning import move_proposed_block
from workspace.models import TaskDraft
from workspace.overview import load_overview
from workspace.planning_insights import compare_plans
from workspace.quick_tasks import (
    create_quick_task,
    edit_quick_task,
    enable_quick_planning,
    initialize_quick_tasks,
    restore_just_completed_task,
    toggle_quick_task,
)
from workspace.repository import DEFAULT_DB_PATH, delete_task
from workspace.simple_planning import proposal_notice
from workspace.study_dna import (
    load_study_dna,
    required_task_ids,
    set_required,
    task_is_required,
)
from workspace.subtask_input import parse_subtasks
from workspace.task_progress import (
    MODE_LABELS,
    ProgressPreference,
    load_progress_preferences,
    progress_html,
    save_progress_preference,
)
from workspace.theme import insight_card, priority_badge, stat_card
from workspace.views.home_briefing import render_daily_briefing, render_deadline_runway
from workspace.views.settings import render_form
from workspace.views.weekly_replay import render_weekly_replay
from workspace.workload_summary import COLORS, ORDER, workload_breakdown

PRIORITIES = {"Low": 1, "Medium": 2, "High": 3}


def pretty_duration(minutes: int) -> str:
    hours, remaining = divmod(minutes, 60)
    if hours and remaining:
        return f"{hours}h {remaining}m"
    if hours:
        return f"{hours}h"
    return f"{remaining}m"


def parse_due_clock(value: str) -> int | None:
    """Accept empty input or an unambiguous 24-hour HH:MM time."""
    text = value.strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) != 2 or not all(part.isdigit() and len(part) == 2 for part in parts):
        raise ValueError("Enter the deadline time as HH:MM, for example 17:30.")
    hour, minute = (int(part) for part in parts)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Enter a valid time between 00:00 and 23:59.")
    return hour * 60 + minute


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
                    "Deadline",
                    value=None,
                    format="DD/MM/YYYY",
                    key=f"new_due_{rev}",
                )
            with right:
                due_time = st.text_input(
                    "Due time",
                    placeholder="hh:mm",
                    max_chars=5,
                    key=f"new_due_time_{rev}",
                )
            left, right = st.columns(2, gap="small")
            with left:
                st.caption("Estimated time")
                estimate = _duration_input(f"new_{rev}")
            with right:
                priority = st.selectbox("Priority", list(PRIORITIES), index=1)
            schedule = st.checkbox(
                "Add study time to my calendar",
                value=True,
                help="Uncheck for errands or tasks you don't want to schedule.",
            )
            must_finish = st.checkbox(
                "Must finish by deadline",
                value=True,
                help="Leave checked for exams or submissions. Uncheck for optional work.",
            )
            subtasks = st.text_area(
                "Subtasks (optional)",
                placeholder="e.g. Find sources\nWrite first draft\nCheck references",
                help="One item per line. You can add or check them off later.",
                key=f"new_subtasks_{rev}",
                height=85,
            )
            submitted = st.form_submit_button("Save task", type="primary")
        if submitted:

            def save():
                lines = parse_subtasks(subtasks)
                new_id = create_quick_task(
                    DEFAULT_DB_PATH,
                    TaskDraft(title, category, due, PRIORITIES[priority], estimate),
                    due_minute=parse_due_clock(due_time),
                    schedule=schedule,
                )
                if due is not None:
                    set_required(DEFAULT_DB_PATH, new_id, bool(must_finish))
                for line in lines:
                    add_step(DEFAULT_DB_PATH, new_id, line, "checklist")
                st.session_state["newly_added_task"] = new_id if schedule else None
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
            from workspace.advanced_planner import week_bounds as clock
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
        st.subheader("Your day")
        if not agenda:
            st.caption("Nothing scheduled today. Add an event or accept a study suggestion.")
        for start, end, title, kind in sorted(agenda)[:9]:
            st.markdown(f"**{format_time(start)}–{format_time(end)}** · {title}")
            st.caption(kind)
        st.page_link("workspace/views/week.py", label="Open calendar")


def _priority_badge(priority: int) -> str:
    """Retain the V4 helper while sharing the palette with the calendar."""
    return priority_badge(priority)


def _personalized_nudge(overview, today: date, profile) -> str | None:
    """One short observation based on saved sessions, not invented AI predictions."""
    _, sunday = week_bounds(today)
    sessions = [
        item
        for item in overview.advanced.sessions
        if item.status == "planned" and today <= item.day <= sunday
    ]
    if not sessions:
        return (
            "Your tasks are ready, but this week's calendar has no accepted study blocks. "
            "Plan my week can help you find a starting point."
            if any(t.status == "pending" for t in overview.tasks)
            else None
        )
    if profile is not None and profile.focus_window is not None:
        lo, hi = profile.focus_window
        total = sum(item.end - item.start for item in sessions)
        preferred = sum(max(0, min(item.end, hi) - max(item.start, lo)) for item in sessions)
        if total >= 90 and preferred * 3 < total:
            return (
                "Most upcoming study time falls outside your strongest concentration hours. "
                "A new preview can look for a closer fit around your commitments."
            )
    by_day = {}
    for item in sessions:
        by_day[item.day] = by_day.get(item.day, 0) + item.end - item.start
    busiest = max(by_day, key=by_day.get)
    if by_day[busiest] >= 240 and by_day[busiest] * 2 > sum(by_day.values()):
        return (
            f"{busiest:%A} is doing the heavy lifting: "
            f"{pretty_duration(by_day[busiest])} booked. "
            "The balanced plan could spread that load if other days have room."
        )
    return None


def _weekly_workload(overview, today: date) -> str:
    """Color-coded stacked week: accepted study and fixed calendar obligations."""
    rows = workload_breakdown(overview.advanced, today)
    peak = max(120, *(sum(parts.values()) for parts in rows.values()))
    bars = []
    for day, parts in rows.items():
        study = parts["Study"]
        commitments = sum(minutes for kind, minutes in parts.items() if kind != "Study")
        booked = study + commitments
        segments = []
        for kind in ORDER:
            minutes = parts[kind]
            if minutes:
                height = round(100 * minutes / peak, 2)
                segments.append(
                    '<div class="pw-workbar-segment" tabindex="0" '
                    f'aria-label="{kind} {pretty_duration(minutes)}" '
                    f'style="height:{height}%;background:{COLORS[kind]}">'
                    f'<span class="pw-workbar-tooltip" aria-hidden="true">'
                    f'{kind} {pretty_duration(minutes)}</span>'
                    "</div>"
                )
        # Only literal color constants and integer-derived dimensions enter HTML.
        bars.append(
            '<div class="pw-workday">'
            f'<div class="pw-workbar-track" role="group" aria-label="{day:%A}: '
            f'{study / 60:g} study hours and {commitments / 60:g} other hours">'
            + "".join(segments)
            + "</div>"
            + f'<div class="pw-workday-label">{day:%a}</div>'
            + '<div class="pw-workday-value">'
            + (f"{booked / 60:g}h" if booked else "—")
            + "</div></div>"
        )
    legend = "".join(
        '<span><i style="background:' + COLORS[kind] + '"></i>' + kind + "</span>" for kind in ORDER
    )
    return (
        '<div class="pw-card"><h3>Your week at a glance</h3>'
        '<p class="pw-section-note">Booked hours by category</p>'
        '<div class="pw-legend">' + legend + "</div>"
        '<div class="pw-workload">' + "".join(bars) + "</div>"
        '<p class="pw-section-note">Booked hours, not free time. '
        "Overlapping events may add up.</p></div>"
    )


def _view_task(task_id: int) -> None:
    """Open the exact task in the shared Tasks page (same browser tab)."""
    st.session_state["task_board_selected_task"] = task_id
    st.session_state["open_task_details"] = task_id
    st.switch_page("workspace/views/task_board.py")


def _home_priorities(overview, deadline_times: dict[int, int], today: date) -> None:
    """A day-specific focus list, completed work below, and upcoming deadlines."""
    pending = [task for task in overview.tasks if task.status == "pending"]
    pending.sort(
        key=lambda task: (task.deadline is None, task.deadline or date.max, -task.priority, task.id)
    )
    soon = [
        task
        for task in pending
        if task.deadline is not None and today <= task.deadline <= today + timedelta(days=7)
    ]
    progress_preferences = load_progress_preferences(DEFAULT_DB_PATH)
    checklist_by_task = {}
    timed_by_task = {}
    for step in overview.advanced.steps:
        if step.kind == "checklist":
            checklist_by_task.setdefault(step.task_id, []).append(step)
        elif step.kind == "timed":
            timed_by_task.setdefault(step.task_id, []).append(step)

    left, right = st.columns([1.18, 0.82], gap="large")
    with left:
        with st.container(border=True):
            st.markdown("### Today’s focus")
            st.caption("Due today, overdue, or on today's study schedule")
            focused = focus_tasks(overview, today)
            if not focused:
                st.caption("No unfinished tasks due or scheduled for today.")
            for index, task in enumerate(focused):
                details, action = st.columns([4.4, 1.3], gap="small")
                with details:
                    st.markdown(
                        '<div class="pw-task-head">'
                        f'<div class="pw-task-title">{escape(task.title)}</div>'
                        f"{priority_badge(task.priority)}</div>"
                        '<div class="pw-task-meta">'
                        f"{escape(task.category)} · "
                        f"{escape(due_display(task, deadline_times, today))} · "
                        f"{pretty_duration(task.remaining_minutes)} remaining</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        progress_html(
                            task,
                            checklist_by_task.get(task.id, []),
                            timed_by_task.get(task.id, []),
                            progress_preferences.get(task.id),
                        ),
                        unsafe_allow_html=True,
                    )
                with action:
                    if st.button("View task", key=f"focus_view_{task.id}", width="stretch"):
                        _view_task(task.id)
                if index < len(focused) - 1:
                    st.divider()
        done_today = completed_today(overview, today)
        with st.expander(f"Completed today ({len(done_today)})", expanded=False):
            if done_today:
                for task in done_today:
                    st.markdown(f"✓ {escape(task.title)}")
            else:
                st.caption("Completed tasks will appear here as you finish them.")
    with right:
        due = [
            '<div class="pw-card"><h3>Upcoming deadlines</h3>',
            '<p class="pw-section-note">The next seven days</p>',
        ]
        for task in soon[:3]:
            due.extend(
                [
                    '<div class="pw-task-preview"><div class="pw-task-head">',
                    f'<div class="pw-task-title">{escape(task.title)}</div>',
                    priority_badge(task.priority),
                    '</div><div class="pw-task-meta">',
                    escape(due_display(task, deadline_times, today)),
                    "</div>",
                    progress_html(
                        task,
                        checklist_by_task.get(task.id, []),
                        timed_by_task.get(task.id, []),
                    ),
                    "</div>",
                ]
            )
        if not soon:
            due.append('<p class="pw-section-note">No deadlines in the next seven days.</p>')
        due.append("</div>")
        if len(soon) > 3:
            due.append(f'<p class="pw-section-note">And {len(soon) - 3} more in Tasks.</p>')
        st.markdown("".join(due), unsafe_allow_html=True)


def _task_rows(
    overview,
    deadline_times: dict[int, int],
    categories: tuple[str, ...],
    *,
    selected_task_id: int | None = None,
) -> None:
    st.subheader("Your tasks")
    progress_preferences = load_progress_preferences(DEFAULT_DB_PATH)
    just_done = st.session_state.get("just_completed_task")
    if just_done:
        task_id, title, previous_remaining = just_done
        current = next((t for t in overview.tasks if t.id == task_id), None)
        if current is not None and current.status == "completed":
            st.success(f"{title} completed.")
            if st.button("Undo completion", key="undo_task_completion"):

                def restore():
                    restore_just_completed_task(DEFAULT_DB_PATH, task_id, previous_remaining)
                    st.session_state.pop("just_completed_task", None)

                _apply(restore, "Task reopened.")
        else:
            st.session_state.pop("just_completed_task", None)
    all_tasks = list(overview.tasks)
    if selected_task_id is not None:
        displayed = [task for task in all_tasks if task.id == selected_task_id]
    else:
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
        with st.container(border=True):
            name, action, partial, details = st.columns([5, 1.1, 1.1, 1.3], gap="small")
            with name:
                st.markdown(
                    f"<strong>{escape(task.title)}</strong> · {_priority_badge(task.priority)}",
                    unsafe_allow_html=True,
                )
                st.caption(
                    f"{task.category} · {due_display(task, deadline_times, date.today())}"
                    f" · {pretty_duration(actually_left)} left"
                )
                checklist_for_task = [
                    step
                    for step in overview.advanced.steps
                    if step.task_id == task.id and step.kind == "checklist"
                ]
                st.markdown(
                    progress_html(
                        task, checklist_for_task, timed, progress_preferences.get(task.id)
                    ),
                    unsafe_allow_html=True,
                )
            with action:
                if st.button(
                    "Done" if task.status == "pending" else "Reopen",
                    key=f"done_{task.id}",
                    width="stretch",
                ):

                    def set_completed(t=task):
                        marking_done = t.status == "pending"
                        toggle_quick_task(DEFAULT_DB_PATH, t.id, marking_done)
                        if marking_done:
                            st.session_state["just_completed_task"] = (
                                t.id,
                                t.title,
                                t.remaining_minutes,
                            )
                        else:
                            st.session_state.pop("just_completed_task", None)

                    _apply(set_completed, "Task updated.")
            with partial:
                if task.status == "pending" and st.button(
                    "Progress",
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
                pref = progress_preferences.get(task.id, ProgressPreference())
                st.markdown("**How should progress be measured?**")
                choices = ["auto", "time", "manual"]
                if checklist_for_task:
                    choices.insert(1, "checklist")
                mode = st.selectbox(
                    "Track using",
                    choices,
                    index=choices.index(pref.mode) if pref.mode in choices else 0,
                    format_func=MODE_LABELS.get,
                    key=f"progress_mode_{task.id}",
                )
                with st.form(f"progress_method_{task.id}"):
                    percent = pref.manual_percent
                    if mode == "manual":
                        percent = st.slider(
                            "How far along are you?",
                            0,
                            100,
                            percent,
                            5,
                            help=(
                                "This changes the progress bar, not the study estimate. "
                                "Mark Done to finish the task."
                            ),
                            key=f"progress_percent_{task.id}",
                        )
                    if st.form_submit_button("Save progress preference"):
                        _apply(
                            lambda: save_progress_preference(
                                DEFAULT_DB_PATH, task.id, mode, int(percent)
                            ),
                            "Progress display updated.",
                        )
                checklist = [
                    step
                    for step in overview.advanced.steps
                    if step.task_id == task.id and step.kind == "checklist"
                ]
                if checklist:
                    st.markdown("**Checklist**")
                    for item in checklist:
                        checked = st.checkbox(
                            item.title,
                            value=item.checked,
                            key=f"partial_check_{item.id}",
                        )
                        if checked != item.checked:
                            _apply(
                                lambda item_id=item.id, value=checked: set_checklist_done(
                                    DEFAULT_DB_PATH,
                                    item_id,
                                    value,
                                ),
                                "Checklist updated.",
                            )
                if checklist and all(item.checked for item in checklist):
                    st.info("All checklist items complete. Mark this task done?")
                    if st.button("Mark task done", key=f"partial_done_{task.id}"):
                        _apply(
                            lambda task_id=task.id: toggle_quick_task(
                                DEFAULT_DB_PATH,
                                task_id,
                                True,
                            ),
                            "Task completed.",
                        )
                with st.expander("Update remaining study time (optional)"):
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
        from workspace.advanced_repository import set_task_dependencies

        others = {t.id: t.title for t in overview.tasks if t.id != task.id}
        parents = [
            e.prerequisite_id for e in overview.advanced.dependencies if e.task_id == task.id
        ]
        with st.expander("Depends on other tasks", expanded=bool(parents)):
            st.caption("Choose tasks to finish first. The planner respects their order.")
            with st.form(f"dependencies_{task.id}"):
                selected_parents = st.multiselect(
                    "Finish these tasks first",
                    list(others),
                    default=parents,
                    format_func=lambda i: others[i],
                    key=f"prerequisites_{task.id}",
                )
                if st.form_submit_button("Save prerequisites"):
                    _apply(
                        lambda: set_task_dependencies(DEFAULT_DB_PATH, task.id, selected_parents),
                        "Prerequisites saved. Review your schedule for changes.",
                    )
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
        all_checked = bool(checklist) and all(item.checked for item in checklist)
        dismissed = st.session_state.get("dismissed_done_prompt", set())
        if task.status == "pending" and all_checked and task.id not in dismissed:
            st.info("All checklist items are done. Mark this task complete?")
            confirm, later = st.columns(2, gap="small")
            if confirm.button("Mark task done", key=f"confirm_check_done_{task.id}"):
                _apply(
                    lambda: toggle_quick_task(DEFAULT_DB_PATH, task.id, True),
                    "Task marked complete.",
                )
            if later.button("Not yet", key=f"later_check_done_{task.id}"):
                st.session_state["dismissed_done_prompt"] = dismissed | {task.id}
                st.rerun()
        if task.status == "pending" and not timed_remaining:
            if st.button("Schedule this task", key=f"schedule_existing_{task.id}"):
                _apply(
                    lambda: enable_quick_planning(DEFAULT_DB_PATH, task.id),
                    "This task can now receive study-time suggestions.",
                )
        if task.status == "pending":
            with st.form(f"new_check_{task.id}", clear_on_submit=True):
                labels = st.text_area(
                    "Add subtasks",
                    placeholder="One per line",
                    height=76,
                    key=f"add_subtasks_{task.id}",
                )
                if st.form_submit_button("Add subtasks"):

                    def save_subtasks():
                        lines = parse_subtasks(labels, required=True)
                        for line in lines:
                            add_step(DEFAULT_DB_PATH, task.id, line, "checklist")

                    _apply(save_subtasks, "Subtasks added.")
        with st.expander("Edit task details", expanded=False):
            rev = st.session_state.get("edit_task_rev", 0)
            category = _category_input(categories, f"edit_{task.id}_{rev}", selected=task.category)
            with st.form(f"edit_task_{task.id}_{rev}"):
                name = st.text_input(
                    "Task name", value=task.title, key=f"edit_name_{task.id}_{rev}"
                )
                left, right = st.columns(2, gap="small")
                with left:
                    due = st.date_input(
                        "Deadline",
                        value=task.deadline,
                        format="DD/MM/YYYY",
                        key=f"edit_due_{task.id}_{rev}",
                    )
                with right:
                    current_due = deadline_times.get(task.id)
                    due_time = st.text_input(
                        "Due time",
                        value=format_time(current_due) if current_due is not None else "",
                        placeholder="hh:mm",
                        max_chars=5,
                        key=f"edit_time_{task.id}_{rev}",
                    )
                left, right = st.columns(2, gap="small")
                with left:
                    priority = st.selectbox(
                        "Priority",
                        list(PRIORITIES),
                        index=task.priority - 1,
                        key=f"edit_priority_{task.id}_{rev}",
                    )
                with right:
                    st.caption("Estimated time")
                    estimate = _duration_input(
                        f"edit_estimate_{task.id}_{rev}",
                        minutes=task.estimate_minutes,
                    )
                    st.caption("Unfinished work")
                    remaining = _duration_input(
                        f"edit_remaining_{task.id}_{rev}",
                        minutes=(
                            sum(timed_remaining) if timed_remaining else task.remaining_minutes
                        ),
                    )
                must_finish = st.checkbox(
                    "Must finish by deadline",
                    value=task_is_required(DEFAULT_DB_PATH, task) or task.deadline is None,
                    help="Required work is protected in Plan A vs Plan B comparisons.",
                )
                if st.form_submit_button("Save changes", type="primary"):

                    def save():
                        edit_quick_task(
                            DEFAULT_DB_PATH,
                            task.id,
                            TaskDraft(name, category, due, PRIORITIES[priority], estimate),
                            remaining,
                            due_minute=parse_due_clock(due_time),
                        )
                        set_required(
                            DEFAULT_DB_PATH, task.id, bool(due is not None and must_finish)
                        )
                        st.session_state["edit_task_rev"] = rev + 1
                        st.session_state.pop("open_task_details", None)
                        st.session_state.pop("partial_task_id", None)

                    _apply(save, "Task saved.")
        with st.expander("Delete task"):
            confirm = st.checkbox("I understand this also deletes scheduled study blocks")
            if st.button("Delete permanently", disabled=not confirm, key=f"delete_{task.id}"):

                def delete():
                    delete_task(DEFAULT_DB_PATH, task.id)
                    st.session_state.pop("open_task_details", None)

                _apply(delete, "Task deleted.")


def _home_planning_insight(overview, now: datetime, required_ids: frozenset[int]) -> None:
    """One visible, data-driven summary; no duplicated radar or hidden warning."""
    snapshot = overview.advanced
    if not (snapshot.budgets or snapshot.windows):
        st.markdown(
            insight_card(
                "Plan your study time",
                "Set study hours in Calendar to get a realistic scheduling suggestion.",
            ),
            unsafe_allow_html=True,
        )
        return

    comparison = compare_plans(snapshot, now)
    coverage = check_required_coverage(snapshot, comparison.preserve.revision, now, required_ids)
    if coverage.outstanding_minutes:
        count = len(coverage.tasks_short)
        title = f"{count} deadline{'s' if count != 1 else ''} need attention"
        names = ", ".join(coverage.tasks_short[:3])
        if count > 3:
            names += f" and {count - 3} more"
        message = (
            f"{pretty_duration(coverage.outstanding_minutes)} of required work still needs "
            f"a study slot before its deadline. Affected: {names}."
        )
        st.markdown(insight_card(title, message), unsafe_allow_html=True)
        st.page_link("workspace/views/week.py", label="Review planning options")
        return

    significant = [
        risk
        for risk in comparison.preserve.risks
        if risk.reason == "overdue" or risk.unscheduled_minutes >= 60
    ]
    if significant:
        first = significant[0]
        st.markdown(
            insight_card(
                "A deadline needs attention",
                f"{first.title} may need a scheduling adjustment. Review the available options.",
            ),
            unsafe_allow_html=True,
        )
        st.page_link("workspace/views/week.py", label="Review planning options")
    elif comparison.preserve.changed:
        st.markdown(
            insight_card(
                "An updated plan is available",
                "You can preview a new arrangement without changing the saved calendar.",
            ),
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            insight_card("Your study plan is on track", "No significant changes needed."),
            unsafe_allow_html=True,
        )


def main() -> None:
    now = datetime.now()
    greeting = (
        "Good morning" if now.hour < 12 else "Good afternoon" if now.hour < 18 else "Good evening"
    )
    try:
        initialize_quick_tasks(DEFAULT_DB_PATH)
        overview = load_overview(DEFAULT_DB_PATH, now.date())
        due_times = list_task_due_times(DEFAULT_DB_PATH)
        profile = load_study_dna(DEFAULT_DB_PATH)
        required_ids = required_task_ids(DEFAULT_DB_PATH, overview.tasks)
    except (ValueError, sqlite3.Error, OSError):
        logging.exception("Could not load Home data")
        st.error("Couldn't load your workspace. Check the database and restart.")
        st.stop()
        return
    personal = f", {escape(profile.name)}" if profile and profile.name else ""
    st.markdown(
        '<div class="pw-hero">'
        f'<div class="pw-eyebrow">{now:%A, %d %B %Y}</div>'
        f"<h1>{greeting}{personal}.</h1>"
        "<p>Your tasks, deadlines and one sensible next step.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    if profile is None and not st.session_state.get("study_dna_later"):
        with st.container(border=True):
            if render_form(DEFAULT_DB_PATH, onboarding=True):
                st.rerun()
            if st.button("Maybe later — show my dashboard", key="study_dna_skip"):
                st.session_state["study_dna_later"] = True
                st.rerun()
    message = st.session_state.pop("home_message", None)
    if message:
        st.success(message)

    pending = [task for task in overview.tasks if task.status == "pending"]
    render_daily_briefing(overview, now)
    upcoming = sum(
        task.deadline is not None and now.date() <= task.deadline <= now.date() + timedelta(days=7)
        for task in pending
    )
    monday, sunday = week_bounds(now.date())
    planned = sum(
        session.end - session.start
        for session in overview.advanced.sessions
        if session.status == "planned" and monday <= session.day <= sunday
    )
    a, b, c = st.columns(3, gap="medium")
    with a:
        st.markdown(
            stat_card("Active tasks", str(len(pending)), "Assignments and to-dos"),
            unsafe_allow_html=True,
        )
    with b:
        st.markdown(
            stat_card("Planned hours", f"{planned / 60:g}h", "Accepted this week"),
            unsafe_allow_html=True,
        )
    with c:
        st.markdown(
            stat_card("Upcoming deadlines", str(upcoming), "Due within seven days"),
            unsafe_allow_html=True,
        )

    # The most actionable planning information belongs above the two-column overview.
    _home_planning_insight(overview, now, required_ids)
    nudge = _personalized_nudge(overview, now.date(), profile)
    if nudge:
        st.caption(nudge)
    _home_priorities(overview, due_times, now.date())
    # Full-width chart avoids a long right-hand column and unused left-hand space.
    st.markdown(_weekly_workload(overview, now.date()), unsafe_allow_html=True)
    render_deadline_runway(overview, now)
    render_weekly_replay(overview.advanced, now, DEFAULT_DB_PATH)


if __name__ == "__main__":
    main()
