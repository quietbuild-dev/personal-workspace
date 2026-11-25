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
    plan_undo_status,
    record_session,
    save_week_preferences,
    update_fixed_event,
)
from workspace.calendar_export import build_calendar_ics
from workspace.conflict_analysis import analyze_conflicts
from workspace.deadline_guarantees import check_required_coverage
from workspace.life_planning import undo_last_plan_with_protection as undo_last_plan
from workspace.manual_planning import move_proposed_block
from workspace.optimizer import GOALS
from workspace.planning_insights import (
    assess_proposal,
    compare_plans,
    scenario_unavailable,
    schedule_metrics,
)
from workspace.repository import DEFAULT_DB_PATH, list_tasks
from workspace.study_dna import load_study_dna, required_task_ids
from workspace.theme import priority_badge
from workspace.views.goal_preview import choose_goal_preview
from workspace.views.life_time import render_time_protection
from workspace.views.schedule_comparison import (
    before_after_html,
    changed_days,
    format_slot,
    schedule_changes,
)
from workspace.views.weekly_calendar import _agenda, calendar_html, study_label

TIME_CHOICES = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)] + ["24:00"]


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
    if not event:
        st.warning("That event no longer exists.")
        return
    with st.container(border=True):
        st.subheader(event.title)
        st.caption(
            f"{event.kind} · {event.day:%d/%m/%Y} · "
            f"{format_time(event.start)}–{format_time(event.end)}"
        )
        with st.expander("Edit event"):
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


def _what_if(snapshot, now: datetime, normal) -> None:
    """Read-only scenario: never present a simulation as an accept-able plan."""
    _, sunday = week_bounds(now.date())
    with st.popover("What if I lose study time?"):
        st.caption("Quick estimate using the original keep-existing heuristic.")
        day = st.date_input(
            "Which day?",
            value=now.date(),
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
        label = st.selectbox("Time unavailable", list(ranges), key="scenario_period")
        try:
            simulated = scenario_unavailable(snapshot, now, day, *ranges[label])
            alternative = compare_plans(simulated, now).preserve
        except ValueError as error:
            st.info(str(error))
            return
        added_shortfall = alternative.due_shortfall_minutes - normal.due_shortfall_minutes
        if added_shortfall > 0:
            message = (
                f"Losing this time could leave {_duration(added_shortfall)} more "
                "work without a study slot before its deadline."
            )
            if added_shortfall >= 60:
                st.error(message)
            else:
                st.info(message)
        elif added_shortfall < 0:
            st.info("The revised plan found time for more deadline work in this simulation.")
        else:
            st.info("No additional deadline problems found in this simulation.")
        if alternative.risks:
            with st.expander("Affected assignments"):
                for risk in alternative.risks[:8]:
                    st.write(_risk_note(risk))
        st.caption("Preview only. Nothing in your calendar has changed.")


def _review(snapshot, now: datetime) -> None:
    """Show intelligible alternatives and a read-only before/after calendar."""
    reschedule_id = st.session_state.get("reschedule_session_id")
    try:
        comparison = compare_plans(snapshot, now, reschedule_session_id=reschedule_id)
    except ValueError:
        st.session_state.pop("reschedule_session_id", None)
        reschedule_id = None
        comparison = compare_plans(snapshot, now)

    stable = comparison.preserve
    if not any(
        s.kind == "timed" and not s.parent_completed and s.remaining_minutes for s in snapshot.steps
    ):
        return

    with st.container(border=True):
        st.markdown("### Rescue my week · Choose your plan")
        st.caption("See how your week could look. Only approval saves the changes.")
        local_dna = load_study_dna(DEFAULT_DB_PATH)
        required = required_task_ids(DEFAULT_DB_PATH, list_tasks(DEFAULT_DB_PATH))
        result, selected = choose_goal_preview(
            snapshot, now, reschedule_id, dna=local_dna, must_ids=required
        )
        if result is None:
            return
        plan_label = {
            "ab_steady": "Plan A · Steady pace",
            "ab_focus": "Plan B · Focus days",
        }.get(selected, GOALS.get(selected, "Your schedule"))
        st.markdown(f"**Previewing: {plan_label}** · Not saved yet")
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
        changed_count = proposal.removed_or_changed + proposal.added_or_changed
        metrics = schedule_metrics(snapshot, proposal, now)
        a, b, c = st.columns(3, gap="small")
        a.metric("Study time in this plan", _duration(proposal.planned_minutes))
        b.metric("Due this week covered", f"{metrics['due_coverage_pct']:g}%")
        c.metric("High priority covered", f"{metrics['high_priority_coverage_pct']:g}%")
        st.caption(
            f"{proposal.removed_or_changed} existing blocks changed · "
            f"{proposal.unchanged} kept. Percentages mean time allocated, not work completed."
        )
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

        steps = {step.id: step for step in snapshot.steps}
        saved = tuple(
            Slot(s.step_id, s.day, s.start, s.end)
            for s in snapshot.sessions
            if s.status == "planned" and proposal.monday <= s.day <= proposal.sunday
        )
        with st.container():
            st.markdown("#### Before and after")
            dates = changed_days(saved, proposal.slots)
            if dates:
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
                st.markdown(
                    '<div class="pw-legend">'
                    '<span><i style="background:#9889A9"></i>Previous time</span>'
                    '<span><i style="background:#D6B8F1"></i>Suggested time</span>'
                    '<span><i style="background:#625C6B"></i>Preserved</span>'
                    "</div>",
                    unsafe_allow_html=True,
                )
                # Before/After is the primary explanation. A short summary
                # remains optional so screen readers can access the changes.
                groups = schedule_changes(saved, proposal.slots, steps)
                if groups:
                    with st.expander("Accessible change summary"):
                        for name, _step_id, removed, added in groups[:10]:
                            st.markdown(f"**{name}**")
                            old_times = ", ".join(format_slot(s) for s in removed)
                            new_times = ", ".join(format_slot(s) for s in added)
                            st.caption(f"Previous: {old_times or 'None'}")
                            st.caption(f"Suggested: {new_times or 'None'}")
            elif changed_count == 0:
                st.caption("Your saved study times would stay where they are.")

        with st.expander("More options (optional)", expanded=False):
            _what_if(snapshot, now, stable)
            if proposal.slots:
                with st.popover("Move a suggested study block"):
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
        accept_incomplete = False
        if not required_coverage.complete:
            accept_incomplete = st.checkbox(
                "I understand this plan leaves required work unscheduled",
                value=False,
                key="acknowledge_incomplete_plan",
            )
        accept, dismiss = st.columns(2, gap="small")
        if accept.button(
            "Approve changes",
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

            _save(
                save_accepted,
                "Plan saved. Use Undo at the top of Calendar to restore the previous schedule.",
            )
        if dismiss.button("Cancel preview", key="dismiss_rescue_plan"):
            st.session_state.pop("goal_previews", None)
            st.session_state.pop("reschedule_session_id", None)
            st.session_state.pop("calendar_adjusted_proposal", None)
            st.session_state.pop("calendar_adjusted_strategy", None)
            st.rerun()
        with st.expander("How scheduling works (optional)", expanded=False):
            st.caption(
                "The planner fits study blocks around fixed events and your study limits. "
                "Plans are suggestions until you approve them; reserving time does not "
                "mark a task done. Undo is available after approval."
            )


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
            '<div class="pw-hero">'
            "<h1>My Calendar</h1>"
            "<p>Lectures, plans, and study time together. Review changes on your terms.</p>"
            "</div>",
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
        st.success(message)
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

    nav_left, nav_date, nav_right, nav_today = st.columns([1, 3, 1, 1.3])
    with nav_left:
        st.button(
            "←",
            key="calendar_previous",
            help="Previous day or week",
            on_click=shift_date,
            args=(-increment,),
        )
    with nav_date:
        date_to_view = st.date_input(
            "Date",
            value=anchor_date,
            format="DD/MM/YYYY",
            label_visibility="collapsed",
            key="calendar_browse_date",
        )
    with nav_right:
        st.button(
            "→",
            key="calendar_following",
            help="Next day or week",
            on_click=shift_date,
            args=(increment,),
        )
    with nav_today:
        st.button("Today", key="calendar_today", on_click=jump_to_today)
    selected_week_start, selected_week_end = week_bounds(date_to_view)

    # Related actions are visible individually, without a large nested expander.
    def start_plan():
        st.session_state["start_week_plan"] = True
        st.session_state["calendar_browse_date"] = now.date()

    add_area, study_area, export_area, plan_area = st.columns([1.2, 1.4, 1.5, 1.6], gap="small")
    with add_area:
        _event_form(snapshot, date_to_view)
    with study_area:
        prefer_day = max(date_to_view, now.date())
        _preferences(snapshot, prefer_day, week_bounds(prefer_day)[1])
    with export_area:
        with st.popover("Export calendar"):
            st.caption(
                "Import this file into Google Calendar or Apple Calendar. "
                "This is a one-time download, not live sync."
            )
            st.download_button(
                "Download week (.ics)",
                data=build_calendar_ics(
                    snapshot, start_day=selected_week_start, end_day=selected_week_end
                ),
                file_name=f"personal-workspace-{selected_week_start.isoformat()}.ics",
                mime="text/calendar",
                key="download_week_ics",
            )
    with plan_area:
        st.button(
            "Plan my week",
            key="calendar_plan_week",
            type="primary",
            on_click=start_plan,
        )
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
        render_time_protection(snapshot, now, DEFAULT_DB_PATH)
        with st.expander(
            "Review a new plan",
            expanded=bool(issues) or bool(st.session_state.get("start_week_plan")),
        ):
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
            ),
            unsafe_allow_html=True,
        )
        st.caption("Select a colored block to view or edit its details.")
    if selected_week_start != monday:
        st.caption("Automatic schedule suggestions currently cover today through Sunday.")
    with st.expander("Agenda by day", expanded=False):
        agenda = _agenda(snapshot.events, slots, steps, selected_week_start, selected_week_end)
        if not agenda:
            st.caption("Nothing scheduled in this week.")
        for day in sorted({row[0] for row in agenda}):
            st.markdown(f"**{day:%A, %d %B}**")
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
                        st.markdown(
                            f"{format_time(start)}–{format_time(end)} · **{title}** · {kind}"
                        )


if __name__ == "__main__":
    main()
