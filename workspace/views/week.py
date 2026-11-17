"""Calendar: one clear timetable, compact event forms and safe schedule review."""

import logging
import sqlite3
from datetime import date, datetime, timedelta

import streamlit as st

from workspace.advanced_planner import Slot, accepted_conflicts, format_time, week_bounds
from workspace.advanced_repository import (
    EVENT_KINDS,
    StaleProposalError,
    accept_revision,
    add_fixed_event,
    delete_fixed_event,
    load_snapshot,
    record_session,
    save_week_preferences,
    update_fixed_event,
)
from workspace.manual_planning import move_proposed_block
from workspace.planning_insights import (
    compare_plans,
    explain_comparison,
    scenario_unavailable,
)
from workspace.repository import DEFAULT_DB_PATH, list_tasks
from workspace.views.weekly_calendar import _agenda, calendar_html, study_label

TIME_CHOICES = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)] + ["24:00"]
PERIODS = {
    "Morning (08:00–12:00)": (8 * 60, 12 * 60),
    "Afternoon (12:00–18:00)": (12 * 60, 18 * 60),
    "Evening (18:00–22:00)": (18 * 60, 22 * 60),
    "Flexible (08:00–22:00)": (8 * 60, 22 * 60),
}


def _as_minute(value: str) -> int:
    h, m = map(int, value.split(":"))
    return 60 * h + m


def _time_index(minute: int) -> int:
    # UI works in half hours; saved legacy minutes round for initial selection only.
    return min(range(len(TIME_CHOICES)), key=lambda i: abs(_as_minute(TIME_CHOICES[i]) - minute))


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
        with st.form("add_calendar_event", clear_on_submit=True):
            name = st.text_input("Event", placeholder="e.g. Statistics lecture")
            kind = st.selectbox("Type", EVENT_KINDS)
            day = st.date_input("Date", value=today, format="DD/MM/YYYY")
            a, b = st.columns(2, gap="small")
            with a:
                start = st.selectbox("From", TIME_CHOICES[:-1], index=_time_index(10 * 60))
            with b:
                end = st.selectbox("To", TIME_CHOICES, index=_time_index(11 * 60))
            if st.form_submit_button("Save event", type="primary"):
                _save(
                    lambda: add_fixed_event(
                        DEFAULT_DB_PATH,
                        name,
                        day,
                        _as_minute(start),
                        _as_minute(end),
                        kind,
                    ),
                    "Event saved. Any affected study plans can be reviewed below.",
                )


def _preferences(snapshot, today: date, sunday: date) -> None:
    with st.popover("Study preferences"):
        st.caption(
            "Choose when you'd like to study, not when you're free. "
            "Lectures and events are excluded automatically."
        )
        existing = {item.day: item.minutes for item in snapshot.budgets}
        preferred = {item.day: (item.start, item.end) for item in snapshot.preferences}
        day = st.date_input(
            "Plan for date",
            value=today,
            format="DD/MM/YYYY",
            min_value=today,
            max_value=sunday,
        )
        with st.form("focus_preferences"):
            default = existing.get(day, 120)
            a, b = st.columns(2, gap="small")
            with a:
                hours = st.number_input(
                    "Study hours", min_value=0, max_value=14, value=default // 60
                )
            with b:
                minutes = st.selectbox(
                    "Extra minutes",
                    [0, 15, 30, 45],
                    index=[0, 15, 30, 45].index((default % 60) // 15 * 15),
                )
            current = preferred.get(day)
            options = list(PERIODS)
            default_period = next(
                (label for label, span in PERIODS.items() if span == current), options[3]
            )
            period = st.selectbox(
                "Preferred time of day", options, index=options.index(default_period)
            )
            scope = st.radio(
                "Apply to", ["Just this day", "Remaining days this week"], horizontal=True
            )
            if st.form_submit_button("Save preference", type="primary"):
                amount = hours * 60 + minutes
                if amount > 840:
                    st.error("Study time cannot exceed 14 hours in one day.")
                else:
                    start, end = PERIODS[period]
                    days = (
                        [day]
                        if scope == "Just this day"
                        else [day + timedelta(days=i) for i in range((sunday - day).days + 1)]
                    )
                    _save(
                        lambda: save_week_preferences(
                            DEFAULT_DB_PATH, tuple(days), amount, start, end
                        ),
                        "Study preferences saved. No calendar changes were accepted.",
                    )
        st.caption("Your calendar remains unchanged until you accept a proposed schedule.")


def _selected_event(snapshot, selected_id: int) -> None:
    event = next((item for item in snapshot.events if item.id == selected_id), None)
    if not event:
        st.warning("That event no longer exists.")
        return
    with st.container(border=True):
        st.subheader(event.title)
        st.caption(
            f"{event.kind} · {event.day:%d/%m/%Y} · "
            f"{format_time(event.start)}–{format_time(event.end)}"
        )
        with st.form(f"edit_event_{event.id}"):
            title = st.text_input("Event name", value=event.title)
            kind = st.selectbox(
                "Type",
                EVENT_KINDS,
                index=EVENT_KINDS.index(event.kind) if event.kind in EVENT_KINDS else 1,
            )
            day = st.date_input("Date", value=event.day, format="DD/MM/YYYY")
            a, b = st.columns(2, gap="small")
            with a:
                start = st.selectbox("From", TIME_CHOICES[:-1], index=_time_index(event.start))
            with b:
                end = st.selectbox("To", TIME_CHOICES, index=_time_index(event.end))
            if st.form_submit_button("Update event", type="primary"):
                _save(
                    lambda: update_fixed_event(
                        DEFAULT_DB_PATH,
                        event.id,
                        title,
                        day,
                        _as_minute(start),
                        _as_minute(end),
                        kind,
                    ),
                    "Event updated. Review any changed suggestions.",
                )
        if st.checkbox("Show delete option", key=f"event_delete_confirm_{event.id}"):
            if st.button("Delete event", key=f"event_delete_{event.id}"):

                def delete():
                    delete_fixed_event(DEFAULT_DB_PATH, event.id)
                    st.query_params.clear()

                _save(delete, "Event deleted.")


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
        st.caption(
            f"{session.day:%a %d %b} · {format_time(session.start)}–"
            f"{format_time(session.end)} · {task.category}"
        )
        checklist = [s for s in snapshot.steps if s.task_id == task.id and s.kind == "checklist"]
        if checklist:
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
        st.caption(
            "For a future session, choose Reschedule. "
            "You can record work once it starts, and mark it missed after it ends."
        )
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
                        amount = max_work if status == "Done" else max_work - int(remaining_after)

                        def save_progress():
                            record_session(DEFAULT_DB_PATH, session.id, "done", amount)
                            st.query_params.clear()

                        _save(save_progress, "Progress saved. Review any new suggestion below.")


def _duration(minutes: int) -> str:
    hours, extra = divmod(minutes, 60)
    return f"{hours}h {extra:02d}m" if hours else f"{extra}m"


def _comparison_card(label: str, assessment) -> None:
    with st.container(border=True):
        st.markdown(f"**{label}**")
        st.caption(f"{_duration(assessment.scheduled_minutes)} of work placed")
        st.caption(f"{assessment.moved_or_removed} existing blocks moved/removed")
        if assessment.due_shortfall_minutes:
            st.warning(f"{_duration(assessment.due_shortfall_minutes)} may miss deadlines")
        else:
            st.caption("No deadline shortfall found by this strategy")


def _what_if(snapshot, now: datetime, normal) -> None:
    """Optional, read-only scenario that cannot be accepted by accident."""
    _, sunday = week_bounds(now.date())
    with st.popover("What if I lose study time?"):
        st.caption("Preview an unexpected commitment. Nothing is saved.")
        tomorrow = now.date() + timedelta(days=1)
        initial_day = tomorrow if now.hour >= 22 and tomorrow <= sunday else now.date()
        day = st.date_input(
            "Unavailable on",
            value=initial_day,
            min_value=now.date(),
            max_value=sunday,
            format="DD/MM/YYYY",
            key="scenario_day",
        )
        ranges = {
            "Morning (08:00–12:00)": (480, 720),
            "Afternoon (12:00–18:00)": (720, 1080),
            "Evening (18:00–22:00)": (1080, 1320),
            "Whole day (08:00–22:00)": (480, 1320),
        }
        initial_period = (
            0
            if day > now.date() or now.hour < 12
            else 1
            if now.hour < 18
            else 2
            if now.hour < 22
            else 3
        )
        label = st.selectbox(
            "Time unavailable",
            list(ranges),
            index=initial_period,
            key="scenario_period",
        )
        try:
            simulated = scenario_unavailable(snapshot, now, day, *ranges[label])
            alternative = compare_plans(simulated, now).preserve
        except ValueError as error:
            st.info(str(error))
        else:
            st.markdown("**Without the change → with the change**")
            st.write(
                f"Work placed: {_duration(normal.scheduled_minutes)} → "
                f"{_duration(alternative.scheduled_minutes)}"
            )
            st.write(
                f"At-risk work: {_duration(normal.due_shortfall_minutes)} → "
                f"{_duration(alternative.due_shortfall_minutes)}"
            )
            st.write(
                f"Existing blocks moved/removed: {normal.moved_or_removed} → "
                f"{alternative.moved_or_removed}"
            )
            if alternative.risks:
                for risk in alternative.risks[:4]:
                    st.warning(
                        f"{risk.title}: {_duration(risk.unscheduled_minutes)} "
                        f"couldn't be placed before {risk.deadline:%d/%m}."
                    )
            st.caption(
                "Simulation only. Your saved events, tasks and calendar are unchanged. "
                "A greedy placement warning does not prove no schedule exists."
            )


def _review(snapshot, now: datetime) -> None:
    """Compare alternatives, explain deadline risk, then require explicit acceptance."""
    reschedule_id = st.session_state.get("reschedule_session_id")
    try:
        comparison = compare_plans(snapshot, now, reschedule_session_id=reschedule_id)
    except ValueError:
        st.session_state.pop("reschedule_session_id", None)
        comparison = compare_plans(snapshot, now)

    stable, baseline = comparison.preserve, comparison.rebuild
    if not (
        stable.changed
        or baseline.changed
        or stable.risks
        or baseline.risks
        or stable.outside_week_minutes
        or baseline.outside_week_minutes
    ):
        return

    with st.container(border=True):
        st.markdown("**Rescue my week**")
        st.caption(
            "Compare two scheduling approaches before changing anything. "
            "Both respect saved appointments, preferred hours and deadlines."
        )
        left, right = st.columns(2, gap="small")
        with left:
            _comparison_card("Keep my plans", stable)
        with right:
            _comparison_card("Rebuild my week", baseline)
        st.caption(explain_comparison(comparison))
        selected = st.segmented_control(
            "Plan to review",
            options=["Keep my plans", "Rebuild my week"],
            default="Keep my plans",
            key="calendar_plan_strategy",
        )
        selected = selected or "Keep my plans"
        if st.session_state.get("calendar_adjusted_strategy") != selected:
            st.session_state.pop("calendar_adjusted_proposal", None)
        assessment = stable if selected == "Keep my plans" else baseline
        adjusted = st.session_state.get("calendar_adjusted_proposal")
        proposal = (
            adjusted
            if adjusted and adjusted.fingerprint == snapshot.fingerprint
            else assessment.revision
        )
        # A manually adjusted proposal has a different impact summary.
        if adjusted and proposal is adjusted:
            st.caption(
                f"Manual preview: {proposal.added_or_changed} blocks added/changed; "
                f"{proposal.removed_or_changed} existing blocks moved/removed."
            )

        if assessment.risks:
            for risk in assessment.risks[:4]:
                prefix = "Already overdue" if risk.reason == "overdue" else "Deadline at risk"
                st.warning(
                    f"{prefix}: {risk.title} · {_duration(risk.unscheduled_minutes)} "
                    f"not placed by this strategy · due {risk.deadline:%d/%m}."
                )
            st.caption(
                "Risk means the current greedy strategy couldn't place all work in "
                "eligible hours; it isn't a proof of infeasibility."
            )
        if assessment.outside_week_minutes:
            st.caption(
                f"{_duration(assessment.outside_week_minutes)} of later-deadline "
                "work was left outside the current week, not counted as deadline risk."
            )

        with st.expander("See exactly what would change"):
            steps = {step.id: step for step in snapshot.steps}
            accepted = {
                (s.step_id, s.day, s.start, s.end): s
                for s in snapshot.sessions
                if s.status == "planned" and proposal.monday <= s.day <= proposal.sunday
            }
            proposed = {(s.step_id, s.day, s.start, s.end) for s in proposal.slots}
            for slot in proposal.slots:
                if (slot.step_id, slot.day, slot.start, slot.end) not in accepted:
                    st.write(
                        f"+ {study_label(steps.get(slot.step_id))} · "
                        f"{slot.day:%a %d %b} {format_time(slot.start)}–{format_time(slot.end)}"
                    )
            for key, session in accepted.items():
                if key not in proposed:
                    step = steps.get(session.step_id)
                    st.write(
                        f"− {study_label(step)} · {session.day:%a %d %b} "
                        f"{format_time(session.start)}–{format_time(session.end)}"
                    )
            if not proposal.added_or_changed and not proposal.removed_or_changed:
                st.caption("No study blocks would move.")

        actions, scenario = st.columns([1, 1], gap="small")
        with scenario:
            _what_if(snapshot, now, stable)
        with actions:
            if proposal.slots:
                with st.popover("Adjust a suggested time"):
                    steps = {step.id: step for step in snapshot.steps}
                    pos = st.selectbox(
                        "Study block",
                        range(len(proposal.slots)),
                        format_func=lambda i: (
                            f"{study_label(steps.get(proposal.slots[i].step_id))} · "
                            f"{proposal.slots[i].day:%a %d %b} "
                            f"{format_time(proposal.slots[i].start)}"
                        ),
                    )
                    with st.form("adjust_calendar_suggestion"):
                        target = proposal.slots[pos]
                        move_day = st.date_input(
                            "New date",
                            value=target.day,
                            min_value=now.date(),
                            max_value=proposal.sunday,
                            format="DD/MM/YYYY",
                        )
                        time_choice = st.selectbox(
                            "New start", TIME_CHOICES[:-1], index=_time_index(target.start)
                        )
                        if st.form_submit_button("Preview change"):
                            try:
                                moved = move_proposed_block(
                                    snapshot,
                                    proposal,
                                    pos,
                                    move_day,
                                    _as_minute(time_choice),
                                    datetime.now(),
                                )
                            except ValueError as error:
                                st.error(str(error))
                            else:
                                st.session_state["calendar_adjusted_proposal"] = moved
                                st.session_state["calendar_adjusted_strategy"] = selected
                                st.rerun()

        a, b = st.columns(2, gap="small")
        if a.button(
            "Accept this plan",
            type="primary",
            key="accept_rescue_plan",
            disabled=not (proposal.added_or_changed or proposal.removed_or_changed),
        ):

            def accept():
                accept_revision(DEFAULT_DB_PATH, proposal, datetime.now())
                st.session_state.pop("reschedule_session_id", None)
                st.session_state.pop("calendar_adjusted_proposal", None)
                st.session_state.pop("calendar_adjusted_strategy", None)

            _save(accept, "Plan accepted. Your calendar has been updated.")
        if b.button("Keep current calendar", key="dismiss_rescue_plan"):
            st.session_state.pop("reschedule_session_id", None)
            st.session_state.pop("calendar_adjusted_proposal", None)
            st.session_state.pop("calendar_adjusted_strategy", None)
            st.rerun()
        st.caption("Previews never alter saved work. Approval is always required.")


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
    st.title("Calendar")
    st.caption("Lectures, personal events and planned work in one place")
    try:
        snapshot = load_snapshot(DEFAULT_DB_PATH)
    except (sqlite3.Error, OSError, ValueError):
        logging.exception("Calendar failed to load")
        st.error("Couldn't load your saved calendar.")
        st.stop()
        return
    message = st.session_state.pop("calendar_message", None)
    if message:
        st.success(message)
    issues = accepted_conflicts(snapshot, now)
    if issues:
        st.warning(f"{len(issues)} existing study blocks need review.")
    date_to_view = st.date_input(
        "Browse date",
        value=anchor_date,
        format="DD/MM/YYYY",
        key="calendar_browse_date",
    )
    selected_week_start, selected_week_end = week_bounds(date_to_view)
    plan_day = max(date_to_view, now.date())
    plan_sunday = week_bounds(plan_day)[1]
    left, right = st.columns([1, 1], gap="small")
    with left:
        _event_form(snapshot, date_to_view)
    with right:
        _preferences(snapshot, plan_day, plan_sunday)
    if not snapshot.budgets and not snapshot.windows:
        st.caption("Set a preferred study budget once to receive scheduling suggestions.")
    selected_session = _selected_item_id("session")
    selected_event = _selected_item_id("event")
    if selected_session:
        _selected_session(snapshot, selected_session, now)
    elif selected_event:
        _selected_event(snapshot, selected_event)
    # Keep urgent schedule repairs above the calendar so they are not buried
    # beneath a full-height timetable. Normal weeks remain calendar-first.
    if selected_week_start == monday:
        _review(snapshot, now)
    view = st.segmented_control("View", ["Day", "Week"], default="Day", key="calendar_view")
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
        st.caption("Sage: planned work · Blue: lectures · Violet: social · Green: exercise")
        st.markdown(
            calendar_html(
                snapshot.events,
                slots,
                steps,
                start_day,
                end_day,
                today=now.date(),
                session_links=links,
            ),
            unsafe_allow_html=True,
        )
        st.caption("Select a colored block to view or edit its details.")
    if selected_week_start != monday:
        st.caption("Automatic schedule suggestions currently cover today through Sunday.")
    with st.expander("All events and study sessions"):
        agenda = _agenda(snapshot.events, slots, steps, selected_week_start, selected_week_end)
        if not agenda:
            st.caption("No saved events or study sessions this week.")
        for day, start, end, kind, title in agenda:
            st.caption(
                f"{day:%a %d %b} · {format_time(start)}–{format_time(end)} · {kind} · {title}"
            )


if __name__ == "__main__":
    main()
