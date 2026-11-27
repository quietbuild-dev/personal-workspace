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
from workspace.categories import category_colors, create_category
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
from workspace.task_modes import is_simple_task, load_task_modes, save_task_mode
from workspace.task_progress import (
    ProgressPreference,
    load_progress_preferences,
    progress_html,
    save_progress_preference,
    tracking_choice,
)
from workspace.theme import insight_card, priority_badge, stat_card
from workspace.views.home_briefing import render_daily_briefing, render_deadline_runway
from workspace.views.settings import render_form
from workspace.views.weekly_replay import render_weekly_replay
from workspace.workload_summary import workload_breakdown

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
        value = st.text_input(
            "New category",
            placeholder="e.g. Volunteering",
            max_chars=40,
            key=f"{key}_new_category",
        )
        return value.strip()

    return choice


def _save_progress_preference_and_close(task_id: int, mode: str, percent: int) -> None:
    """Persist the display choice and close the editor on both Home and Tasks."""
    save_progress_preference(DEFAULT_DB_PATH, task_id, mode, int(percent))
    for key in (
        "partial_task_id",
        "open_task_details",
        "home_quick_progress",
        "home_details_origin",
        "task_more_details_id",
    ):
        st.session_state.pop(key, None)


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
        tracking = st.radio(
            "Track progress with",
            ["Progress bar", "Subtasks", "Simple to-do"],
            horizontal=True,
            index=0,
            key=f"new_style_{rev}",
        )
        is_todo = tracking == "Simple to-do"
        with st.form(f"new_task_{rev}"):
            title = st.text_input("Task name", placeholder="e.g. Finish economics assignment")
            due = st.date_input(
                "Deadline",
                value=None,
                format="DD/MM/YYYY",
                key=f"new_due_{rev}",
            )
            left, right = st.columns(2, gap="small")
            with left:
                if is_todo:
                    estimate = 15  # Internal placeholder; never shown as task progress.
                else:
                    st.caption("Estimated time")
                    estimate = _duration_input(f"new_{rev}")
            with right:
                priority = st.selectbox("Priority", list(PRIORITIES), index=1)
            if tracking == "Subtasks":
                subtasks = st.text_area(
                    "Subtasks (one per line)",
                    placeholder="Find sources\nWrite first draft\nCheck references",
                    key=f"new_subtasks_{rev}",
                    height=85,
                )
            with st.expander("More details (optional)", expanded=False):
                due_time = st.text_input(
                    "Due time",
                    placeholder="e.g. 11:05",
                    help="24-hour time, including any minute from 00 to 59.",
                    max_chars=5,
                    key=f"new_due_time_{rev}",
                )
                schedule = (
                    False
                    if is_todo
                    else st.checkbox(
                        "Add study time to my calendar",
                        value=True,
                        help="Uncheck for errands or tasks you don't want to schedule.",
                    )
                )
                must_finish = (
                    False
                    if is_todo
                    else st.checkbox(
                        "Must finish by deadline",
                        value=True,
                        help="Leave checked for exams or submissions. Uncheck for optional work.",
                    )
                )
                if tracking != "Subtasks":
                    subtasks = st.text_area(
                        "Subtasks (optional)",
                        placeholder="e.g. Find sources\nWrite first draft\nCheck references",
                        help="These won't change your selected progress method.",
                        key=f"new_subtasks_{rev}",
                        height=85,
                    )
            submitted = st.form_submit_button("Save task", type="primary")
        if submitted:

            def save():
                lines = parse_subtasks(subtasks, required=(tracking == "Subtasks"))
                saved_category = create_category(DEFAULT_DB_PATH, category)
                new_id = create_quick_task(
                    DEFAULT_DB_PATH,
                    TaskDraft(title, saved_category, due, PRIORITIES[priority], estimate),
                    due_minute=parse_due_clock(due_time),
                    schedule=schedule,
                )
                if due is not None:
                    set_required(DEFAULT_DB_PATH, new_id, bool(must_finish))
                save_task_mode(DEFAULT_DB_PATH, new_id, "simple" if is_todo else "progress")
                if not is_todo:
                    save_progress_preference(
                        DEFAULT_DB_PATH,
                        new_id,
                        "checklist" if tracking == "Subtasks" else "manual",
                        0,
                    )
                for line in lines:
                    add_step(DEFAULT_DB_PATH, new_id, line, "checklist")
                st.session_state["newly_added_task"] = new_id if schedule else None
                st.session_state["new_task_version"] = rev + 1
                st.session_state["task_add_open"] = False
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
            from workspace.views.week import TIME_CHOICES, _as_minute, _time_index

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
                new_start = st.selectbox("Start time", TIME_CHOICES[:-1], index=_time_index(9 * 60))
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
        return None
    if profile is not None and profile.focus_window is not None:
        lo, hi = profile.focus_window
        total = sum(item.end - item.start for item in sessions)
        preferred = sum(max(0, min(item.end, hi) - max(item.start, lo)) for item in sessions)
        if total >= 90 and preferred * 3 < total:
            return "Most booked study falls outside your preferred hours."
    by_day = {}
    for item in sessions:
        by_day[item.day] = by_day.get(item.day, 0) + item.end - item.start
    busiest = max(by_day, key=by_day.get)
    if by_day[busiest] >= 240 and by_day[busiest] * 2 > sum(by_day.values()):
        return f"{busiest:%A} has {pretty_duration(by_day[busiest])} of study booked."
    return None


def _weekly_workload(overview, today: date) -> str:
    """Seamless rectangular category stacks with compact readable durations."""
    palette = category_colors(DEFAULT_DB_PATH)
    rows = workload_breakdown(overview.advanced, today, palette)
    ordered = tuple(kind for kind in palette if any(day[kind] for day in rows.values()))
    peak = max(120, *(sum(parts.values()) for parts in rows.values()))
    bars = []
    for day, parts in rows.items():
        booked = sum(parts.values())
        segments = []
        for kind in ordered:
            minutes = parts[kind]
            if minutes:
                height = round(100 * minutes / peak, 2)
                segments.append(
                    '<div class="pw-workbar-segment" tabindex="0" '
                    f'aria-label="{escape(kind)} {pretty_duration(minutes)}" '
                    f'style="height:{height}%;background:{palette[kind]}">'
                    f'<span class="pw-workbar-tooltip" aria-hidden="true">'
                    f"{escape(kind)} {pretty_duration(minutes)}</span></div>"
                )
        bars.append(
            '<div class="pw-workday">'
            f'<div class="pw-workbar-track" role="group" '
            f'aria-label="{day:%A}: {pretty_duration(booked)} booked">'
            + "".join(segments)
            + "</div>"
            + f'<div class="pw-workday-label">{day:%a}</div>'
            + '<div class="pw-workday-value">'
            + (pretty_duration(booked) if booked else "—")
            + "</div></div>"
        )
    legend = "".join(
        '<span><i style="background:' + palette[kind] + '"></i>' + escape(kind) + "</span>"
        for kind in ordered
    )
    return (
        '<div class="pw-card"><h3>Your week at a glance</h3>'
        '<div class="pw-legend">' + legend + "</div>"
        '<div class="pw-workload">' + "".join(bars) + "</div></div>"
    )


def _task_checklist(overview, task, *, key_prefix: str, interactive: bool = True) -> bool:
    """Show stored subtasks at the task, rather than hiding them behind More details.

    Updating a checkbox changes only that checklist step. It never marks the
    parent task complete or changes its remaining study minutes.
    """
    steps = getattr(getattr(overview, "advanced", None), "steps", ())
    items = [step for step in steps if step.task_id == task.id and step.kind == "checklist"]
    if not items:
        return False
    checked_count = sum(bool(item.checked) for item in items)
    st.caption(f"Subtasks · {checked_count}/{len(items)} completed")
    for item in items:
        if interactive and task.status == "pending":
            checked = st.checkbox(
                item.title,
                value=bool(item.checked),
                key=f"{key_prefix}_subtask_{task.id}_{item.id}",
            )
            if checked != bool(item.checked):
                _apply(
                    lambda step_id=item.id, value=checked: set_checklist_done(
                        DEFAULT_DB_PATH, step_id, value
                    ),
                    "Subtask updated.",
                )
        else:
            st.markdown(f"{'✓' if item.checked else '○'} {escape(item.title)}")
    return True


def _remember_task_done(task) -> None:
    """Keep the previous remaining estimate available for an immediate Undo."""
    toggle_quick_task(DEFAULT_DB_PATH, task.id, True)
    st.session_state["just_completed_task"] = (task.id, task.title, task.remaining_minutes)
    for key in (
        "open_task_details",
        "task_more_details_id",
        "home_quick_progress",
        "home_details_origin",
        "partial_task_id",
    ):
        st.session_state.pop(key, None)


def _reopen_task(task) -> None:
    """Undo an immediate completion exactly; otherwise offer normal reopening."""
    recent = st.session_state.get("just_completed_task")
    if recent and recent[0] == task.id and recent[2] > 0:
        restore_just_completed_task(DEFAULT_DB_PATH, task.id, recent[2])
    else:
        toggle_quick_task(DEFAULT_DB_PATH, task.id, False)
    if recent and recent[0] == task.id:
        st.session_state.pop("just_completed_task", None)
    for key in ("open_task_details", "task_more_details_id", "home_quick_progress"):
        st.session_state.pop(key, None)


def _view_task(task_id: int) -> None:
    """Open the exact task in the shared Tasks page (same browser tab)."""
    st.session_state["task_board_selected_task"] = task_id
    st.session_state["open_task_details"] = task_id
    st.switch_page("workspace/views/task_board.py")


def _home_task_actions(task, overview, *, key_prefix="home") -> None:
    """Quick actions remain on Home; no trip to the Tasks page required."""
    if overview is not None and st.session_state.get("open_task_details") != task.id:
        items = tuple(
            step
            for step in getattr(getattr(overview, "advanced", None), "steps", ())
            if step.task_id == task.id and step.kind == "checklist"
        )
        if (
            tracking_choice(
                task,
                load_task_modes(DEFAULT_DB_PATH).get(task.id),
                load_progress_preferences(DEFAULT_DB_PATH).get(task.id),
                items,
            )
            == "Subtasks"
        ):
            _task_checklist(overview, task, key_prefix=key_prefix)
    done, progress, details, _space = st.columns([1, 1.25, 1.1, 2.0], gap="small")
    if done.button("Done", key=f"{key_prefix}_done_{task.id}", width="stretch"):
        _apply(lambda: _remember_task_done(task), "Task done")
    items = tuple(
        step
        for step in getattr(getattr(overview, "advanced", None), "steps", ())
        if step.task_id == task.id and step.kind == "checklist"
    )
    user_mode = load_task_modes(DEFAULT_DB_PATH).get(task.id)
    user_pref = load_progress_preferences(DEFAULT_DB_PATH).get(task.id)
    shown_mode = tracking_choice(task, user_mode, user_pref, items)
    if progress.button(
        "Subtasks" if shown_mode == "Subtasks" else "Progress",
        key=f"{key_prefix}_progress_{task.id}",
        width="stretch",
    ):
        already_open = (
            st.session_state.get("open_task_details") == task.id
            and st.session_state.get("home_details_origin") == key_prefix
            and st.session_state.get("home_quick_progress") == task.id
        )
        if already_open:
            st.session_state.pop("open_task_details", None)
            st.session_state.pop("home_quick_progress", None)
            st.session_state.pop("home_details_origin", None)
        else:
            st.session_state["open_task_details"] = task.id
            st.session_state["home_details_origin"] = key_prefix
            st.session_state["home_quick_progress"] = task.id
            st.session_state.pop("task_more_details_id", None)
        st.rerun()
    if details.button("Details", key=f"{key_prefix}_details_{task.id}", width="stretch"):
        already_open = (
            st.session_state.get("open_task_details") == task.id
            and st.session_state.get("home_details_origin") == key_prefix
            and st.session_state.get("home_quick_progress") != task.id
        )
        if already_open:
            st.session_state.pop("open_task_details", None)
            st.session_state.pop("home_details_origin", None)
        else:
            st.session_state["open_task_details"] = task.id
            st.session_state["home_details_origin"] = key_prefix
        st.session_state.pop("home_quick_progress", None)
        st.session_state.pop("task_more_details_id", None)
        st.rerun()
    # Render directly under this task rather than at the end of the whole section.
    if (
        overview is not None
        and st.session_state.get("open_task_details") == task.id
        and st.session_state.get("home_details_origin") == key_prefix
    ):
        _edit_task(
            overview,
            tuple(category_colors(DEFAULT_DB_PATH)),
            list_task_due_times(DEFAULT_DB_PATH),
        )


def _home_priorities(overview, deadline_times: dict[int, int], today: date) -> None:
    """Today's due/scheduled work alongside unscheduled errands without deadlines."""
    left, right = st.columns([1.1, 0.9], gap="medium")
    with left:
        with st.container(border=True):
            st.markdown("### Today's focus")
            focused = focus_tasks(overview, today)
            if not focused:
                st.caption("Nothing urgent on your list today.")
            for task in focused:
                st.markdown(
                    '<div class="pw-home-task-name" style="margin:10px 0 3px">'
                    f"{escape(task.title)}</div>"
                    '<div class="pw-home-task-meta" style="margin:0 0 5px">'
                    f"{escape(task.category)} · "
                    f"{escape(due_display(task, deadline_times, today))}"
                    "</div>",
                    unsafe_allow_html=True,
                )
                # Today's Focus is deliberately a plain list. Checklist controls
                # live in Tasks; completion appears in Completed Today below.
                st.markdown(
                    '<div style="border-bottom:1px solid #393640;margin:9px 0"></div>',
                    unsafe_allow_html=True,
                )
    with right:
        with st.container(border=True):
            st.markdown("### To-do")
            no_deadline = sorted(
                (
                    task
                    for task in overview.tasks
                    if task.status == "pending" and task.deadline is None
                ),
                key=lambda task: (-task.priority, task.id),
            )
            if not no_deadline:
                st.caption("No open to-dos without deadlines.")
            show_all_todos = st.session_state.get("home_all_todos", False)
            for task in no_deadline if show_all_todos else no_deadline[:5]:
                st.markdown(
                    f'<div class="pw-home-task-name">{escape(task.title)}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div class="pw-home-task-meta">{escape(task.category)}</div>',
                    unsafe_allow_html=True,
                )
                _home_task_actions(task, overview)
            if len(no_deadline) > 5:
                label = (
                    "Show fewer to-dos"
                    if show_all_todos
                    else f"Show {len(no_deadline) - 5} more to-dos"
                )
                if st.button(label, key="home_toggle_todos"):
                    st.session_state["home_all_todos"] = not show_all_todos
                    st.rerun()
    # Task details are rendered inline by _home_task_actions, next to their task.
    done_today = completed_today(overview, today)
    with st.container(border=True):
        st.markdown(f"### Completed today  ·  {len(done_today)}")
        if not done_today:
            st.caption("Finished tasks appear here.")
        else:
            show_all_done = st.session_state.get("home_all_completed", False)
            visible = done_today if show_all_done else done_today[:3]
            for task in visible:
                label, undo = st.columns([8, 1], vertical_alignment="center")
                with label:
                    st.markdown(
                        '<div class="pw-completed-row"><span class="pw-done-tick">✓</span>'
                        f"<span>{escape(task.title)}</span></div>",
                        unsafe_allow_html=True,
                    )
                with undo:
                    recent = st.session_state.get("just_completed_task")
                    immediate = bool(recent and recent[0] == task.id)
                    if st.button(
                        "↶ Undo" if immediate else "↶ Reopen",
                        key=f"home_undo_completed_{task.id}",
                        help="Reopen this task if you marked it done by mistake.",
                    ):
                        _apply(lambda t=task: _reopen_task(t), "Task reopened.")
            if len(done_today) > 3:
                label = (
                    "Show fewer completed tasks"
                    if show_all_done
                    else f"Show {len(done_today) - 3} more"
                )
                if st.button(label, key="home_toggle_completed"):
                    st.session_state["home_all_completed"] = not show_all_done
                    st.rerun()


def _task_rows(
    overview,
    deadline_times: dict[int, int],
    categories: tuple[str, ...],
    *,
    selected_task_id: int | None = None,
    sort_by: str = "Deadline",
) -> None:
    st.subheader("Your tasks")
    progress_preferences = load_progress_preferences(DEFAULT_DB_PATH)
    task_modes = load_task_modes(DEFAULT_DB_PATH)
    just_done = st.session_state.get("just_completed_task")
    if just_done:
        task_id, title, _previous_remaining = just_done
        current = next((t for t in overview.tasks if t.id == task_id), None)
        if current is not None and current.status == "completed":
            st.caption(f"{title} completed. You can undo this below.")
            if st.button("Undo completion", key="undo_task_completion"):

                def restore():
                    _reopen_task(current)

                _apply(restore, "Task reopened.")
        else:
            st.session_state.pop("just_completed_task", None)
    all_tasks = list(overview.tasks)
    if selected_task_id is not None:
        displayed = [task for task in all_tasks if task.id == selected_task_id]
    else:
        show_done = st.checkbox("Show completed tasks", value=False, key="home_show_done")
        displayed = [task for task in all_tasks if show_done or task.status != "completed"]
    sort_keys = {
        "Deadline": lambda t: (t.deadline or date.max, -t.priority, t.id),
        "Priority": lambda t: (-t.priority, t.deadline or date.max, t.id),
        "Category": lambda t: (t.category.casefold(), t.deadline or date.max, t.id),
    }
    displayed.sort(key=lambda t: (t.status == "completed", *sort_keys[sort_by](t)))
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
                simple = is_simple_task(task, overview.advanced.steps, task_modes)
                due_phrase = due_display(task, deadline_times, date.today())
                task_meta = f"{task.category} · {due_phrase}" + (
                    " · To-do" if simple else f" · {pretty_duration(actually_left)} left"
                )
                if task.deadline and task.deadline < date.today() and task.status == "pending":
                    st.markdown(
                        f'<span class="pw-task-overdue">{escape(task_meta)}</span>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption(task_meta)
                checklist_for_task = [
                    step
                    for step in overview.advanced.steps
                    if step.task_id == task.id and step.kind == "checklist"
                ]
                pref = progress_preferences.get(task.id, ProgressPreference())
                chosen_tracking = tracking_choice(
                    task,
                    task_modes.get(task.id),
                    pref,
                    checklist_for_task,
                )
                if not simple:
                    st.markdown(
                        progress_html(task, checklist_for_task, timed, pref),
                        unsafe_allow_html=True,
                    )
                if (
                    chosen_tracking == "Subtasks"
                    and checklist_for_task
                    and st.session_state.get("open_task_details") != task.id
                ):
                    _task_checklist(overview, task, key_prefix="tasks")
            with action:
                recent = st.session_state.get("just_completed_task")
                button_label = (
                    "Done"
                    if task.status == "pending"
                    else "↶ Undo"
                    if recent and recent[0] == task.id
                    else "↶ Reopen"
                )
                if st.button(
                    button_label,
                    key=f"done_{task.id}",
                    width="stretch",
                    disabled=task.status == "pending"
                    and any(not item.checked for item in checklist_for_task),
                ):
                    if task.status == "pending":
                        _apply(lambda t=task: _remember_task_done(t), "Task done.")
                    else:
                        _apply(lambda t=task: _reopen_task(t), "Task reopened.")
            with partial:
                if (
                    task.status == "pending"
                    and not simple
                    and chosen_tracking != "Subtasks"
                    and st.button(
                        "Progress",
                        key=f"partial_{task.id}",
                        width="stretch",
                    )
                ):
                    st.session_state["partial_task_id"] = (
                        None if st.session_state.get("partial_task_id") == task.id else task.id
                    )
                    st.rerun()
            with details:
                if st.button("Details", key=f"details_{task.id}", width="stretch"):
                    current = st.session_state.get("open_task_details")
                    st.session_state["open_task_details"] = None if current == task.id else task.id
                    st.session_state.pop("task_more_details_id", None)
                    st.session_state.pop("home_quick_progress", None)
                    st.rerun()
            if st.session_state.get("partial_task_id") == task.id and chosen_tracking != "Subtasks":
                pref = progress_preferences.get(task.id, ProgressPreference())
                st.markdown("**Update progress**")
                # Keep the original tracking mode, even if subtasks were added later.
                mode = "manual" if pref.mode in ("manual", "auto") else pref.mode
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
                            lambda: _save_progress_preference_and_close(
                                task.id, mode, int(percent)
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
                                st.session_state.pop("open_task_details", None)
                                st.session_state.pop("home_quick_progress", None)

                            _apply(save_partial, "Remaining work updated.")
            if st.session_state.get("open_task_details") == task.id:
                _edit_task(overview, categories, deadline_times)


def _edit_task(overview, categories, deadline_times) -> None:
    task_id = st.session_state.get("open_task_details")
    task = next((item for item in overview.tasks if item.id == task_id), None)
    if task is None:
        st.session_state.pop("open_task_details", None)
        return
    steps = [item for item in overview.advanced.steps if item.task_id == task_id]
    with st.container(border=True):
        heading, close = st.columns([5, 1], vertical_alignment="center")
        heading.markdown(f"#### {task.title}")
        if close.button("Close", key=f"close_task_summary_{task.id}"):
            st.session_state.pop("open_task_details", None)
            st.session_state.pop("task_board_selected_task", None)
            st.session_state.pop("task_more_details_id", None)
            st.session_state.pop("home_quick_progress", None)
            st.rerun()
        priority_label = next(
            (name for name, rank in PRIORITIES.items() if rank == task.priority),
            "Medium",
        )
        st.caption(
            f"{task.category} · {due_display(task, deadline_times, date.today())} · "
            f"{priority_label} priority"
        )
        checklist = [step for step in steps if step.kind == "checklist"]
        if task.status == "completed":
            st.caption("Completed")
            _task_checklist(overview, task, key_prefix="summary", interactive=False)
            if st.button("↶ Undo completion", key=f"summary_undo_{task.id}"):
                _apply(lambda: _reopen_task(task), "Task reopened.")
        else:
            pref = load_progress_preferences(DEFAULT_DB_PATH).get(task.id, ProgressPreference())
            modes = load_task_modes(DEFAULT_DB_PATH)
            selected = tracking_choice(task, modes.get(task.id), pref, checklist)
            if selected != "Simple to-do":
                st.markdown(
                    progress_html(
                        task,
                        [step for step in steps if step.kind == "checklist"],
                        [step for step in steps if step.kind == "timed"],
                        pref,
                    ),
                    unsafe_allow_html=True,
                )
            if selected == "Subtasks":
                _task_checklist(overview, task, key_prefix="summary")
            if (
                selected == "Progress bar"
                and st.session_state.get("home_quick_progress") == task.id
            ):
                with st.form(f"task_quick_progress_{task.id}"):
                    value = st.slider(
                        "Progress",
                        0,
                        100,
                        pref.manual_percent if pref.mode == "manual" else 0,
                        step=5,
                    )
                    if st.form_submit_button("Save progress", type="primary"):
                        _apply(
                            lambda: _save_progress_preference_and_close(task.id, "manual", value),
                            "Progress saved.",
                        )
            primary, secondary = st.columns([1.2, 1.6], gap="small")
            if primary.button(
                "Mark done",
                key=f"summary_done_{task.id}",
                disabled=bool(checklist) and not all(item.checked for item in checklist),
            ):
                _apply(lambda: _remember_task_done(task), "Task done")
            if selected == "Progress bar" and secondary.button(
                "Update progress", key=f"summary_progress_{task.id}"
            ):
                st.session_state["home_quick_progress"] = task.id
                st.rerun()
        expanded = st.session_state.get("task_more_details_id") == task.id
        if st.button(
            "Hide extra details" if expanded else "More details",
            key=f"task_more_button_{task.id}",
        ):
            if expanded:
                st.session_state.pop("task_more_details_id", None)
            else:
                st.session_state["task_more_details_id"] = task.id
            st.rerun()
    if st.session_state.get("task_more_details_id") == task.id:
        _edit_task_full(overview, categories, deadline_times)


def _edit_task_full(overview, categories, deadline_times) -> None:
    task_id = st.session_state.get("open_task_details")
    task = next((task for task in overview.tasks if task.id == task_id), None)
    if task is None:
        return
    steps = [step for step in overview.advanced.steps if step.task_id == task.id]
    timed_remaining = [step.remaining_minutes for step in steps if step.kind == "timed"]
    checklist = [step for step in steps if step.kind == "checklist"]
    with st.container(border=True):
        st.subheader(task.title)
        task_modes = load_task_modes(DEFAULT_DB_PATH)
        preference = load_progress_preferences(DEFAULT_DB_PATH).get(task.id)
        current_mode = tracking_choice(
            task,
            task_modes.get(task.id),
            preference,
            checklist,
        )
        with st.expander("Progress tracking", expanded=False):
            modes = ["Simple to-do", "Progress bar", "Subtasks"]
            display_mode = st.radio(
                "Track progress with",
                modes,
                index=modes.index(current_mode),
                horizontal=True,
                key=f"task_display_{task.id}",
            )
            if st.button("Save tracking method", key=f"save_task_display_{task.id}"):

                def save_tracking():
                    save_task_mode(
                        DEFAULT_DB_PATH,
                        task.id,
                        "simple" if display_mode == "Simple to-do" else "progress",
                    )
                    if display_mode != "Simple to-do":
                        save_progress_preference(
                            DEFAULT_DB_PATH,
                            task.id,
                            "checklist" if display_mode == "Subtasks" else "manual",
                            preference.manual_percent if preference is not None else 0,
                        )
                    st.session_state.pop("open_task_details", None)
                    st.session_state.pop("task_more_details_id", None)

                _apply(save_tracking, "Progress tracking updated.")
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
        # Manual-tracked tasks may still have checklists; those can be edited
        # without silently switching their saved progress tracking method.
        if current_mode == "Progress bar" and checklist:
            with st.expander("Subtasks (not used for progress)", expanded=False):
                _task_checklist(overview, task, key_prefix="extra")
        # In Subtasks mode, checkboxes are visible in the compact summary.
        all_checked = bool(checklist) and all(item.checked for item in checklist)
        dismissed = st.session_state.get("dismissed_done_prompt", set())
        if task.status == "pending" and all_checked and task.id not in dismissed:
            st.info("All checklist items are done. Mark this task complete?")
            confirm, later = st.columns(2, gap="small")
            if confirm.button("Mark task done", key=f"confirm_check_done_{task.id}"):
                _apply(lambda: _remember_task_done(task), "Task marked complete.")
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
                        placeholder="e.g. 11:05",
                        help="24-hour time, including any minute from 00 to 59.",
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
                    help="Keep this work protected when planning around deadlines.",
                )
                if st.form_submit_button("Save changes", type="primary"):

                    def save():
                        edit_quick_task(
                            DEFAULT_DB_PATH,
                            task.id,
                            TaskDraft(
                                name,
                                create_category(DEFAULT_DB_PATH, category),
                                due,
                                PRIORITIES[priority],
                                estimate,
                            ),
                            remaining,
                            due_minute=parse_due_clock(due_time),
                        )
                        set_required(
                            DEFAULT_DB_PATH, task.id, bool(due is not None and must_finish)
                        )
                        st.session_state["edit_task_rev"] = rev + 1
                        st.session_state.pop("open_task_details", None)
                        st.session_state.pop("task_board_selected_task", None)
                        st.session_state.pop("task_more_details_id", None)
                        st.session_state.pop("partial_task_id", None)

                    _apply(save, "Task saved.")
        with st.expander("Delete task"):
            confirm = st.checkbox("I understand this also deletes scheduled study blocks")
            if st.button("Delete permanently", disabled=not confirm, key=f"delete_{task.id}"):

                def delete():
                    delete_task(DEFAULT_DB_PATH, task.id)
                    st.session_state.pop("open_task_details", None)
                    st.session_state.pop("task_board_selected_task", None)
                    st.session_state.pop("task_more_details_id", None)

                _apply(delete, "Task deleted.")


def _home_planning_insight(overview, now: datetime, required_ids: frozenset[int]) -> None:
    """One short warning about upcoming required work with a direct scheduling action."""
    snapshot = overview.advanced
    if not (snapshot.budgets or snapshot.windows):
        st.caption("Set your study hours in Calendar to get scheduling suggestions.")
        return
    comparison = compare_plans(snapshot, now)
    coverage = check_required_coverage(snapshot, comparison.preserve.revision, now, required_ids)
    upcoming_titles = {
        task.title
        for task in overview.tasks
        if task.status == "pending"
        and task.deadline is not None
        and now.date() <= task.deadline <= week_bounds(now.date())[1]
    }
    affected = [name for name in coverage.tasks_short if name in upcoming_titles]
    if not affected:
        return
    steps = {step.id: step for step in snapshot.steps}
    booked = {}
    for slot in comparison.preserve.revision.slots:
        booked[slot.step_id] = booked.get(slot.step_id, 0) + slot.minutes
    remaining = sum(
        max(0, step.remaining_minutes - booked.get(step.id, 0))
        for step in steps.values()
        if step.task_title in upcoming_titles
        and step.task_title in affected
        and step.kind == "timed"
        and not step.parent_completed
    )
    with st.container(border=True):
        st.markdown(
            f"**{len(affected)} deadline{'s' if len(affected) != 1 else ''} need attention**"
        )
        st.caption(f"{pretty_duration(remaining)} of work still needs planning.")
        if st.button("Fix my schedule", key="home_fix_schedule", type="primary"):
            st.session_state["start_week_plan"] = True
            st.session_state["optimizer_goal"] = "deadlines"
            st.session_state["calendar_review_open"] = True
            st.switch_page("workspace/views/week.py")


def main() -> None:
    now = datetime.now()
    greeting = (
        "Good evening"
        if now.hour < 4 or now.hour >= 18
        else "Good morning"
        if now.hour < 12
        else "Good afternoon"
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
        ""
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
        st.toast(message)

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
    with st.container(key="home_statistics"):
        a, b, c = st.columns(3, gap="medium")
        with a:
            st.markdown(
                stat_card("Active tasks", str(len(pending)), "Assignments and to-dos"),
                unsafe_allow_html=True,
            )
        with b:
            st.markdown(
                stat_card("Planned time", pretty_duration(planned), "Accepted this week"),
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
        st.markdown(insight_card("Study rhythm", nudge), unsafe_allow_html=True)
    _home_priorities(overview, due_times, now.date())
    # Full-width chart avoids a long right-hand column and unused left-hand space.
    st.markdown(_weekly_workload(overview, now.date()), unsafe_allow_html=True)
    render_deadline_runway(
        overview,
        now,
        task_actions=lambda task: _home_task_actions(task, overview, key_prefix="home_due"),
        progress_preferences=load_progress_preferences(DEFAULT_DB_PATH),
    )
    # Deadline, Focus and To-do actions each render their own panel inline.
    render_weekly_replay(overview.advanced, now, DEFAULT_DB_PATH)


if __name__ == "__main__":
    main()
