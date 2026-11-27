"""Calendar: one clear timetable, compact event forms and safe schedule review."""

import logging
import sqlite3
from datetime import date, datetime, timedelta

import streamlit as st

from workspace.advanced_planner import Slot, accepted_conflicts, format_time, week_bounds
from workspace.advanced_repository import (
    StaleProposalError,
    accept_revision,
    delete_fixed_event,
    get_event_notes,
    load_snapshot,
    plan_undo_status,
    record_session,
    save_week_preferences,
    update_fixed_event,
)
from workspace.calendar_export import build_calendar_ics, save_calendar_to_downloads
from workspace.categories import category_colors, create_category, list_categories
from workspace.conflict_analysis import analyze_conflicts
from workspace.deadline_guarantees import check_required_coverage
from workspace.life_planning import undo_last_plan_with_protection as undo_last_plan
from workspace.optimizer import GOALS
from workspace.planning_insights import (
    assess_proposal,
    compare_plans,
    schedule_metrics,
)
from workspace.recurrence import (
    FREQUENCIES,
    add_recurring_event,
    delete_recurring_series,
    series_info,
)
from workspace.repository import DEFAULT_DB_PATH, list_tasks
from workspace.stale_bookings import (
    outdated_planned_sessions,
    outdated_undo_available,
    remove_outdated_bookings,
    undo_outdated_cleanup,
)
from workspace.study_dna import load_study_dna, required_task_ids
from workspace.theme import priority_badge
from workspace.views.calendar_import import render_calendar_import
from workspace.views.energy_today import render_energy_today
from workspace.views.goal_preview import choose_goal_preview
from workspace.views.life_time import render_time_protection
from workspace.views.plan_doctor import render_plan_doctor
from workspace.views.schedule_comparison import (
    before_after_html,
    changed_days,
)
from workspace.views.weekly_calendar import _agenda, calendar_html, study_label

TIME_CHOICES = [f"{h:02d}:{m:02d}" for h in range(24) for m in range(0, 60, 5)] + ["24:00"]


def _as_minute(value: str) -> int:
    h, m = map(int, value.split(":"))
    return 60 * h + m


def _time_index(minute: int) -> int:
    # Five-minute input choices; preserve exact imported times when editing events.
    return min(range(len(TIME_CHOICES)), key=lambda i: abs(_as_minute(TIME_CHOICES[i]) - minute))


def _event_time_choices(*saved_minutes: int) -> list[str]:
    """Keep exact imported times in the edit form, even if not on a five-minute grid."""
    extras = [f"{minute // 60:02d}:{minute % 60:02d}" for minute in saved_minutes]
    return sorted(set(TIME_CHOICES).union(extras), key=_as_minute)


def _save(action, success: str) -> None:
    try:
        action()
    except (StaleProposalError, ValueError) as error:
        st.error(str(error))
    except (sqlite3.Error, OSError):
        logging.exception("Calendar update failed")
        st.error("Couldn't save that change. Your previous calendar remains in place.")
    else:
        st.session_state["calendar_message"] = success
        st.rerun()


def _event_form(snapshot, today: date) -> None:
    with st.popover("+ Add event"):
        repeat = st.selectbox(
            "Repeat",
            FREQUENCIES,
            format_func=lambda option: "Does not repeat" if option == "Never" else option,
            key="new_event_repeat",
        )
        event_categories = list_categories(DEFAULT_DB_PATH)
        kind_choice = st.selectbox(
            "Category",
            [*event_categories, "+ New category"],
            key="calendar_event_category_choice",
        )
        new_kind = (
            st.text_input("New category name", max_chars=40, key="calendar_event_new_category")
            if kind_choice == "+ New category"
            else ""
        )
        with st.form("add_calendar_event", clear_on_submit=True):
            name = st.text_input("Event", placeholder="e.g. Statistics lecture")
            day = st.date_input("Date", value=today, format="DD/MM/YYYY")
            a, b = st.columns(2, gap="small")
            with a:
                start = st.selectbox("From", TIME_CHOICES[:-1], index=_time_index(10 * 60))
            with b:
                end = st.selectbox("To", TIME_CHOICES, index=_time_index(11 * 60))
            notes = st.text_area("Notes (optional)", max_chars=4000, height=85)
            repeat_days = {"Daily": 30, "Weekly": 180, "Monthly": 365, "Yearly": 731}
            until = (
                st.date_input(
                    "Repeat until (inclusive)",
                    value=day + timedelta(days=repeat_days.get(repeat, 0)),
                    min_value=day,
                    max_value=day + timedelta(days=731),
                    format="DD/MM/YYYY",
                    key=f"new_event_repeat_until_{repeat}",
                )
                if repeat != "Never"
                else day
            )
            if st.form_submit_button("Save event", type="primary"):
                _save(
                    lambda: add_recurring_event(
                        DEFAULT_DB_PATH,
                        name,
                        day,
                        _as_minute(start),
                        _as_minute(end),
                        create_category(
                            DEFAULT_DB_PATH,
                            new_kind if kind_choice == "+ New category" else kind_choice,
                        ),
                        repeat,
                        until,
                        notes=notes,
                    ),
                    "Event saved. Any affected study plans can be reviewed below.",
                )


def _preferences(snapshot, today: date, sunday: date) -> None:
    """One compact, date-specific study preference; never an availability setup."""
    with st.popover("Study preferences"):
        existing = {item.day: item.minutes for item in snapshot.budgets}
        preferred = {item.day: (item.start, item.end) for item in snapshot.preferences}
        day = st.date_input(
            "Date",
            value=today,
            format="DD/MM/YYYY",
            min_value=today,
            max_value=sunday,
        )
        current = preferred.get(day, (8 * 60, 22 * 60))
        with st.form("focus_preferences"):
            default = existing.get(day, 120)
            hours = st.number_input(
                "Study hours",
                min_value=0.0,
                max_value=14.0,
                value=default / 60,
                step=0.25,
                format="%.2f",
                help="Maximum study time for this day (2.5 means two and a half hours).",
            )
            with st.expander("Preferred start and finish times (optional)"):
                left, right = st.columns(2, gap="small")
                with left:
                    earliest = st.selectbox(
                        "Earliest start",
                        TIME_CHOICES[:-1],
                        index=_time_index(current[0]),
                    )
                with right:
                    latest = st.selectbox(
                        "Latest finish",
                        TIME_CHOICES[1:],
                        index=max(0, _time_index(current[1]) - 1),
                    )
            copy_week = st.checkbox("Use these settings for remaining days this week")
            if st.form_submit_button("Save preference", type="primary"):
                amount = round(float(hours) * 60)
                start, end = _as_minute(earliest), _as_minute(latest)
                if end <= start:
                    st.error("The finish time must be later than the start time.")
                elif amount > 840:
                    st.error("Please set no more than 14 hours per day.")
                else:
                    days = (
                        [day + timedelta(days=i) for i in range((sunday - day).days + 1)]
                        if copy_week
                        else [day]
                    )
                    _save(
                        lambda: save_week_preferences(
                            DEFAULT_DB_PATH,
                            tuple(days),
                            amount,
                            start,
                            end,
                        ),
                        "Study preferences saved. Your calendar has not changed.",
                    )


def _selected_event(snapshot, selected_id: int) -> None:
    event = next((item for item in snapshot.events if item.id == selected_id), None)
    if event is None:
        st.warning("This event no longer exists.")
        return
    series = series_info(DEFAULT_DB_PATH, event.id)
    with st.container(border=True):
        title_area, close_area = st.columns([5, 1], vertical_alignment="center")
        title_area.markdown(f"### Edit event · {event.title}")
        if close_area.button("Close", key=f"close_event_{event.id}"):
            st.query_params.pop("event", None)
            st.rerun()
        if series:
            st.caption(f"Repeats {series[1].lower()}. Only this occurrence will change.")
        with st.form(f"edit_event_{event.id}"):
            title = st.text_input("Event name", value=event.title)
            event_categories = list_categories(DEFAULT_DB_PATH)
            if event.kind not in event_categories:
                event_categories = (*event_categories, event.kind)
            kind = st.selectbox(
                "Category",
                [*event_categories, "+ New category"],
                index=event_categories.index(event.kind),
            )
            new_kind = (
                st.text_input("New category name", max_chars=40) if kind == "+ New category" else ""
            )
            day = st.date_input("Date", value=event.day, format="DD/MM/YYYY")
            a, b = st.columns(2, gap="small")
            event_choices = _event_time_choices(event.start, event.end)
            with a:
                start = st.selectbox(
                    "From",
                    event_choices[:-1],
                    index=event_choices[:-1].index(
                        f"{event.start // 60:02d}:{event.start % 60:02d}"
                    ),
                )
            with b:
                end = st.selectbox(
                    "To",
                    event_choices,
                    index=event_choices.index(f"{event.end // 60:02d}:{event.end % 60:02d}"),
                )
            notes = st.text_area(
                "Notes (optional)",
                value=get_event_notes(DEFAULT_DB_PATH, event.id),
                height=90,
                max_chars=4000,
            )
            if st.form_submit_button("Save changes", type="primary"):

                def save():
                    update_fixed_event(
                        DEFAULT_DB_PATH,
                        event.id,
                        title,
                        day,
                        _as_minute(start),
                        _as_minute(end),
                        create_category(DEFAULT_DB_PATH, new_kind)
                        if kind == "+ New category"
                        else kind,
                        notes=notes,
                    )
                    st.query_params.pop("event", None)

                _save(save, "Event saved")
        if st.button("Cancel", key=f"cancel_event_{event.id}"):
            st.query_params.pop("event", None)
            st.rerun()
        with st.expander("Delete event"):
            if st.checkbox("I want to delete this event", key=f"confirm_delete_{event.id}"):
                if st.button("Delete event", key=f"event_delete_{event.id}"):

                    def delete():
                        delete_fixed_event(DEFAULT_DB_PATH, event.id)
                        st.query_params.clear()

                    _save(delete, "Event deleted")
                if series and st.button(
                    "Delete entire repeating series", key=f"delete_series_{event.id}"
                ):

                    def delete_series():
                        delete_recurring_series(DEFAULT_DB_PATH, event.id)
                        st.query_params.clear()

                    _save(delete_series, "Repeating series deleted")


def _selected_session(snapshot, selected_id: int, now: datetime) -> None:
    session = next(
        (s for s in snapshot.sessions if s.id == selected_id and s.status == "planned"),
        None,
    )
    if session is None:
        st.warning("That study session is no longer active. Open Calendar to see the latest plan.")
        return
    step = next((s for s in snapshot.steps if s.id == session.step_id), None)
    if step is None:
        return
    tasks = {task.id: task for task in list_tasks(DEFAULT_DB_PATH)}
    task = tasks.get(step.task_id)
    if task is None:
        return
    with st.container(border=True):
        st.subheader(study_label(step))
        st.markdown(priority_badge(task.priority), unsafe_allow_html=True)
        if task.deadline:
            remaining_days = (task.deadline - now.date()).days
            due_text = (
                "Overdue"
                if remaining_days < 0
                else "Due today"
                if remaining_days == 0
                else f"Due in {remaining_days} day(s)"
            )
            st.caption(due_text)
        st.caption(
            f"{session.day:%a %d %b} · {format_time(session.start)}–"
            f"{format_time(session.end)} · {task.category}"
        )
        checklist = [s for s in snapshot.steps if s.task_id == task.id and s.kind == "checklist"]
        if checklist:
            pending_items = [item.title for item in checklist if not item.checked]
            if pending_items:
                st.markdown(f"**Next:** {pending_items[0]}")
            st.markdown("**Checklist**")
            from workspace.advanced_repository import set_checklist_done

            for item in checklist:
                checked = st.checkbox(
                    item.title, value=item.checked, key=f"session_check_{item.id}"
                )
                if checked != item.checked:
                    _save(
                        lambda step_id=item.id, value=checked: set_checklist_done(
                            DEFAULT_DB_PATH, step_id, value
                        ),
                        "Checklist updated.",
                    )
        with st.expander("Update progress or reschedule"):
            begun = session.day < now.date() or (
                session.day == now.date() and session.start <= now.hour * 60 + now.minute
            )
            ended = session.day < now.date() or (
                session.day == now.date() and session.end <= now.hour * 60 + now.minute
            )
            options = ["Done", "Partially done"] if begun else []
            if ended:
                options.append("Missed")
            options.append("Reschedule")
            if not begun:
                st.caption("This session hasn't started. You can change its time.")
            status = st.selectbox("What happened?", options)
            with st.form(f"session_result_{session.id}"):
                max_work = min(session.end - session.start, step.remaining_minutes)
                remaining_after = None
                if status == "Partially done":
                    st.caption("How much of this session's work is still unfinished?")
                    remaining_after = st.number_input(
                        "Minutes left (estimate)",
                        min_value=1,
                        max_value=max(1, max_work - 1),
                        value=max(1, max_work // 2),
                    )
                if st.form_submit_button(
                    "Review new time" if status == "Reschedule" else "Save progress",
                    type="primary",
                ):
                    if status == "Reschedule":
                        st.session_state["reschedule_session_id"] = session.id
                        st.session_state.pop("calendar_adjusted_proposal", None)
                        st.session_state["show_revision"] = True
                        st.rerun()
                    elif status == "Missed":

                        def mark_missed():
                            record_session(DEFAULT_DB_PATH, session.id, "missed")
                            st.query_params.clear()

                        _save(mark_missed, "Session marked missed. Review a replacement below.")
                    else:
                        if status == "Partially done" and max_work < 2:
                            st.error("This session is too short for partial progress.")
                        else:
                            amount = (
                                max_work if status == "Done" else max_work - int(remaining_after)
                            )

                            def save_progress():
                                record_session(DEFAULT_DB_PATH, session.id, "done", amount)
                                st.query_params.clear()

                            _save(save_progress, "Progress saved. Review any new suggestion below.")


def _duration(minutes: int) -> str:
    hours, extra = divmod(minutes, 60)
    return f"{hours}h {extra:02d}m" if hours else f"{extra}m"


def _risk_note(risk) -> str:
    if risk.reason == "overdue":
        return f"{risk.title} — {_duration(risk.unscheduled_minutes)} unplanned (overdue)"
    return (
        f"{risk.title} — {_duration(risk.unscheduled_minutes)} unplanned "
        f"· due {risk.deadline:%d/%m}"
    )


def _review(snapshot, now: datetime) -> None:
    """Show intelligible alternatives and a read-only before/after calendar."""
    reschedule_id = st.session_state.get("reschedule_session_id")
    try:
        compare_plans(snapshot, now, reschedule_session_id=reschedule_id)
    except ValueError:
        st.session_state.pop("reschedule_session_id", None)
        reschedule_id = None
        compare_plans(snapshot, now)

    if not any(
        s.kind == "timed" and not s.parent_completed and s.remaining_minutes for s in snapshot.steps
    ):
        return

    with st.container(border=True):
        st.markdown("### Plan your week")
        st.caption("Preview your plan before saving it.")
        local_dna = load_study_dna(DEFAULT_DB_PATH)
        required = required_task_ids(DEFAULT_DB_PATH, list_tasks(DEFAULT_DB_PATH))
        result, selected = choose_goal_preview(
            snapshot, now, reschedule_id, dna=local_dna, must_ids=required
        )
        if result is None:
            return
        plan_label = GOALS.get(selected, "Your schedule")
        st.caption(f"{plan_label} · Preview only, nothing saved yet")
        if st.session_state.get("calendar_adjusted_strategy") != selected:
            st.session_state.pop("calendar_adjusted_proposal", None)
        assessment = assess_proposal(snapshot, result.revision)
        adjusted = st.session_state.get("calendar_adjusted_proposal")
        proposal = (
            adjusted
            if adjusted is not None and adjusted.fingerprint == snapshot.fingerprint
            else assessment.revision
        )
        assessment = assess_proposal(snapshot, proposal)
        required_coverage = check_required_coverage(snapshot, proposal, now, required)
        metrics = schedule_metrics(snapshot, proposal, now)
        a, b, c, d = st.columns(4, gap="small")
        a.metric("Deadline work scheduled", f"{metrics['due_coverage_pct']:g}%")
        b.metric("High-priority work scheduled", f"{metrics['high_priority_coverage_pct']:g}%")
        c.metric("Days with study", len({slot.day for slot in proposal.slots}))
        d.metric("Existing sessions changed", proposal.removed_or_changed)
        st.caption(
            f"{proposal.removed_or_changed} existing blocks change · "
            f"{proposal.unchanged} stay as they are."
        )
        steps = {step.id: step for step in snapshot.steps}
        saved = tuple(
            Slot(s.step_id, s.day, s.start, s.end)
            for s in snapshot.sessions
            if s.status == "planned" and proposal.monday <= s.day <= proposal.sunday
        )
        dates = changed_days(saved, proposal.slots)
        if dates:
            st.markdown("#### Before and after")
            day = st.selectbox(
                "Day to compare",
                list(dates),
                format_func=lambda d: d.strftime("%A, %d %B"),
                key="rescue_comparison_day",
            )
            st.markdown(
                before_after_html(day, snapshot.events, saved, proposal.slots, steps),
                unsafe_allow_html=True,
            )
        else:
            st.caption("Your saved study sessions would stay where they are.")

        if not required_coverage.complete:
            st.warning(
                f"{_duration(required_coverage.outstanding_minutes)} of deadline work "
                "still needs a study slot. Try another plan or add available hours."
            )
        if assessment.risks:
            st.markdown("**Work that still needs time**")
            for risk in assessment.risks[:3]:
                st.caption(_risk_note(risk))
            if len(assessment.risks) > 3:
                with st.expander(f"See {len(assessment.risks) - 3} more tasks"):
                    for risk in assessment.risks[3:]:
                        st.caption(_risk_note(risk))
        else:
            st.caption("All work due this week has a suggested study time.")
        if assessment.outside_week_minutes:
            st.caption("Work due after Sunday can be planned in a later week.")
        if proposal.shortfalls and assessment.risks:
            with st.expander("Why is some work left out?", expanded=False):
                conflicts = analyze_conflicts(snapshot, proposal, now)
                for conflict in conflicts[:4]:
                    st.markdown(f"**{conflict.title}**")
                    if conflict.needed_minutes > conflict.capacity_upper_bound:
                        st.caption(
                            f"Only up to {_duration(conflict.capacity_upper_bound)} is "
                            "available before its deadline, even without other tasks."
                        )
                    elif "unchecked checklist" in conflict.explanation:
                        st.caption("Finish the prerequisite checklist first.")
                    elif "before this task starts" in conflict.explanation:
                        st.caption("A prerequisite must be scheduled first.")
                    else:
                        st.caption("Other work competes for the same available hours.")
                if len(conflicts) > 4:
                    st.caption(f"{len(conflicts) - 4} more tasks need study time.")
                st.caption(
                    "Try another goal or update your study preferences. "
                    "A different plan may help, but cannot guarantee every task will fit."
                )

        accept_incomplete = False
        if not required_coverage.complete:
            accept_incomplete = st.checkbox(
                "I understand this plan leaves required work unscheduled",
                value=False,
                key="acknowledge_incomplete_plan",
            )
        accept, dismiss = st.columns(2, gap="small")
        if accept.button(
            "Save this plan",
            type="primary",
            key="accept_rescue_plan",
            disabled=(
                not (proposal.added_or_changed or proposal.removed_or_changed)
                or (not required_coverage.complete and not accept_incomplete)
            ),
        ):

            def save_accepted():
                accept_revision(DEFAULT_DB_PATH, proposal, datetime.now())
                st.session_state.pop("reschedule_session_id", None)
                st.session_state.pop("goal_previews", None)
                st.session_state.pop("calendar_adjusted_proposal", None)
                st.session_state.pop("calendar_adjusted_strategy", None)
                st.session_state.pop("calendar_review_open", None)

            _save(
                save_accepted,
                "Plan saved. Use Undo at the top of Calendar to restore the previous schedule.",
            )
        if dismiss.button("Cancel", key="dismiss_rescue_plan"):
            st.session_state.pop("goal_previews", None)
            st.session_state.pop("reschedule_session_id", None)
            st.session_state.pop("calendar_adjusted_proposal", None)
            st.session_state.pop("calendar_adjusted_strategy", None)
            st.session_state.pop("calendar_review_open", None)
            st.rerun()


def _selected_item_id(key: str) -> int | None:
    value = st.query_params.get(key)
    if not isinstance(value, str) or not value.isdigit():
        return None
    number = int(value)
    return number if number > 0 else None


def main() -> None:
    now = datetime.now()
    monday, sunday = week_bounds(now.date())
    date_param = st.query_params.get("date")
    try:
        anchor_date = date.fromisoformat(date_param) if isinstance(date_param, str) else now.date()
    except ValueError:
        anchor_date = now.date()
    header, undo_area = st.columns([4.5, 1.5], gap="medium", vertical_alignment="center")
    with header:
        st.markdown(
            '<div class="pw-hero"><h1>My Calendar</h1></div>',
            unsafe_allow_html=True,
        )
    try:
        snapshot = load_snapshot(DEFAULT_DB_PATH)
    except (sqlite3.Error, OSError, ValueError):
        logging.exception("Calendar failed to load")
        st.error("Couldn't load your saved calendar.")
        st.stop()
        return
    message = st.session_state.pop("calendar_message", None)
    if message:
        st.toast(message)
    outdated = outdated_planned_sessions(snapshot, now)
    if outdated:
        st.warning(
            f"{len(outdated)} study booking(s) belong to completed or removed tasks. "
            "These bookings cannot be moved into another plan."
        )
        labels = {step.id: step.task_title for step in snapshot.steps}
        for session in outdated:
            st.caption(
                f"{session.day:%a %d %b} · "
                f"{format_time(session.start)}–{format_time(session.end)} · "
                f"{labels.get(session.step_id, 'Removed task')}"
            )
        if st.button("Remove outdated bookings", key="calendar_remove_outdated"):
            _save(
                lambda: remove_outdated_bookings(
                    DEFAULT_DB_PATH,
                    datetime.now(),
                    snapshot.fingerprint,
                    tuple(session.id for session in outdated),
                ),
                "Outdated study bookings removed. Undo is available below.",
            )
    if outdated_undo_available(DEFAULT_DB_PATH):
        if st.button("Undo removed bookings", key="calendar_undo_outdated"):
            _save(
                lambda: undo_outdated_cleanup(DEFAULT_DB_PATH),
                "Outdated study bookings restored.",
            )
    undo_state = plan_undo_status(DEFAULT_DB_PATH)
    if undo_state == "ready":
        with undo_area:
            if st.button("↶ Undo last plan", key="undo_last_plan"):
                _save(
                    lambda: undo_last_plan(DEFAULT_DB_PATH, datetime.now()),
                    "Previous study schedule restored.",
                )
    issues = accepted_conflicts(snapshot, now)
    if issues:
        st.info(f"{len(issues)} study blocks may need a new time.")
    view = (
        st.segmented_control(
            "View",
            ["Day", "Week"],
            default="Day",
            key="calendar_view",
        )
        or "Day"
    )
    increment = 1 if view == "Day" else 7
    if st.session_state.get("_nav_query_date") != date_param:
        st.session_state["calendar_browse_date"] = anchor_date
        st.session_state["_nav_query_date"] = date_param

    def shift_date(days: int) -> None:
        current = st.session_state.get("calendar_browse_date", anchor_date)
        st.session_state["calendar_browse_date"] = current + timedelta(days=days)

    def jump_to_today() -> None:
        st.session_state["calendar_browse_date"] = now.date()

    date_to_view = st.session_state.get("calendar_browse_date", anchor_date)
    if view == "Day":
        title = f"{date_to_view:%A, %d %B %Y}"
    else:
        start, finish = week_bounds(date_to_view)
        title = f"{start:%d %b} – {finish:%d %b %Y}"
    # One centered navigation axis, with "Today" serving as a real shortcut.
    _, nav_middle, _ = st.columns([1, 3.0, 1])
    with nav_middle:
        _, today_button, _ = st.columns([2, 1.1, 2], gap="small")
        with today_button:
            st.button(
                "Today",
                key="calendar_jump_today",
                on_click=jump_to_today,
                type="tertiary",
                width="stretch",
            )
        left, chooser, right = st.columns([1, 4, 1], vertical_alignment="center")
        with left:
            st.button(
                "←",
                key="calendar_previous",
                help="Previous day or week",
                on_click=shift_date,
                args=(-increment,),
                width="stretch",
            )
        with chooser:
            with st.popover(title, use_container_width=True):
                chosen = st.date_input(
                    "Go to date",
                    value=date_to_view,
                    format="DD/MM/YYYY",
                    key="calendar_go_to_date",
                )
                if st.button("Go to date", key="calendar_confirm_date"):
                    st.session_state["calendar_browse_date"] = chosen
                    st.rerun()
        with right:
            st.button(
                "→",
                key="calendar_following",
                help="Next day or week",
                on_click=shift_date,
                args=(increment,),
                width="stretch",
            )
    selected_week_start, selected_week_end = week_bounds(date_to_view)

    # Related actions are visible individually, without a large nested expander.
    def start_plan():
        st.session_state["calendar_review_open"] = True
        st.session_state["start_week_plan"] = False
        st.session_state.pop("goal_previews", None)
        st.session_state.pop("calendar_adjusted_proposal", None)

    _, actions, _ = st.columns([1, 3.0, 1])
    with actions:
        add_area, study_area, plan_area = st.columns(3, gap="small")
        with add_area:
            _event_form(snapshot, date_to_view)
        with study_area:
            prefer_day = max(date_to_view, now.date())
            _preferences(snapshot, prefer_day, week_bounds(prefer_day)[1])
        with plan_area:
            st.button(
                "Plan my week",
                key="calendar_plan_week",
                type="primary",
                on_click=start_plan,
            )
    selected_session = _selected_item_id("session")
    selected_event = _selected_item_id("event")
    if selected_session:
        _selected_session(snapshot, selected_session, now)
    elif selected_event:
        _selected_event(snapshot, selected_event)
    if selected_week_start == monday:
        render_plan_doctor(snapshot, now)
        if st.session_state.get("start_week_plan"):
            st.session_state["calendar_review_open"] = True
        if st.session_state.get("calendar_review_open"):
            _review(snapshot, now)
    if view == "Week":
        start_day, end_day = selected_week_start, selected_week_end
    else:
        start_day = end_day = date_to_view
    steps = {step.id: step for step in snapshot.steps}
    sessions = [
        session
        for session in snapshot.sessions
        if session.status == "planned" and selected_week_start <= session.day <= selected_week_end
    ]
    slots = [Slot(s.step_id, s.day, s.start, s.end) for s in sessions]
    links = {(s.step_id, s.day, s.start, s.end): s.id for s in sessions}
    with st.container(border=True):
        st.markdown(
            '<div class="pw-legend">'
            '<span><i style="background:#BAA9D0"></i>Study</span>'
            '<span><i style="background:#8FAACB"></i>Lectures</span>'
            '<span><i style="background:#D99EBB"></i>Social</span>'
            '<span><i style="background:#8AB9A6"></i>Exercise</span>'
            '<span><i style="background:#C8A99D"></i>Personal</span>'
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            calendar_html(
                snapshot.events,
                slots,
                steps,
                start_day,
                end_day,
                today=now.date(),
                session_links=links,
                category_colors=category_colors(DEFAULT_DB_PATH),
            ),
            unsafe_allow_html=True,
        )
    if selected_week_start == monday:
        render_energy_today(snapshot, now, DEFAULT_DB_PATH)
        render_time_protection(snapshot, now, DEFAULT_DB_PATH)
    if selected_week_start != monday:
        st.caption("Automatic schedule suggestions currently cover today through Sunday.")
    with st.expander("Agenda by day", expanded=False):
        agenda = _agenda(snapshot.events, slots, steps, selected_week_start, selected_week_end)
        if not agenda:
            st.caption("Nothing scheduled in this week.")
        for day in sorted({row[0] for row in agenda}):
            st.markdown(
                f'<div class="pw-agenda-day-heading">{day:%A, %d %B}</div>',
                unsafe_allow_html=True,
            )
            day_rows = [row for row in agenda if row[0] == day]
            for group, types in (
                ("Study", {"Study"}),
                ("Lectures", {"Lecture"}),
                (
                    "Plans and appointments",
                    {"Appointment", "Personal", "Social", "Exercise", "Other"},
                ),
            ):
                rows = [row for row in day_rows if row[3] in types]
                if rows:
                    st.caption(group)
                    for _, start, end, kind, title in rows:
                        from html import escape

                        palette = category_colors(DEFAULT_DB_PATH)
                        color = palette.get(kind, "#B5B3C9")
                        st.markdown(
                            f'<div class="pw-agenda-row" style="--category-color:{color}">'
                            f'<div class="pw-agenda-title">{escape(title)}</div>'
                            f'<div class="pw-agenda-time">{format_time(start)}–'
                            f"{format_time(end)} · {escape(kind)}</div></div>",
                            unsafe_allow_html=True,
                        )

    st.markdown("### Calendar tools")
    with st.expander("Export calendar", expanded=False, icon=":material/download:"):
        calendar_file = build_calendar_ics(
            snapshot,
            start_day=selected_week_start,
            end_day=selected_week_end,
        )
        st.download_button(
            "Download this week (.ics)",
            data=calendar_file,
            file_name=f"personal-workspace-{selected_week_start.isoformat()}.ics",
            mime="text/calendar",
            key="download_week_ics",
        )
        st.caption("Browser downloads go wherever your browser saves files.")
        if st.button("Save a copy to Downloads", key="save_week_ics_locally"):
            try:
                saved_path = save_calendar_to_downloads(calendar_file, selected_week_start)
            except OSError as error:
                st.error(f"Could not save the calendar file: {error}")
            else:
                st.success(f"Saved to: {saved_path}")
    render_calendar_import(snapshot, DEFAULT_DB_PATH)


if __name__ == "__main__":
    main()
