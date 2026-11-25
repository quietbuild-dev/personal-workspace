"""Streamlit controls for a saved hourly calendar and reviewable revisions."""

import logging
import sqlite3
from datetime import datetime, time, timedelta
from html import escape
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from workspace.advanced_planner import (
    Slot,
    accepted_conflicts,
    format_time,
    make_revision,
    week_bounds,
)
from workspace.advanced_repository import (
    StaleProposalError,
    accept_revision,
    add_fixed_event,
    add_window,
    delete_fixed_event,
    delete_window,
    load_snapshot,
    record_session,
)
from workspace.theme import CALENDAR_CSS


def _minute(value: time) -> int:
    return value.hour * 60 + value.minute


def _calendar_bounds(events, slots, windows, monday, sunday):
    """Show a useful range around saved events, never cutting off early/late work."""
    intervals = [
        (item.start, item.end)
        for item in (*events, *slots, *windows)
        if monday <= item.day <= sunday
    ]
    if not intervals:
        return 8 * 60, 20 * 60
    earliest = min(start for start, _ in intervals)
    latest = max(end for _, end in intervals)
    lower = max(0, min(8 * 60, (earliest // 60 - 1) * 60))
    upper = min(24 * 60, max(20 * 60, ((latest + 59) // 60 + 1) * 60))
    return lower, upper


def _short_label(title: str, max_length: int = 18) -> str:
    """Labels stay inside a day column; full descriptions remain in the tooltip/agenda."""
    return title if len(title) <= max_length else title[: max_length - 1].rstrip() + "..."


def _chart(events, slots, steps, monday, sunday, *, title, windows=()):
    """Seven-column weekly time grid: days across, clock times vertically."""
    days = [monday + timedelta(days=i) for i in range(7)]
    position = {day: i for i, day in enumerate(days)}
    lower, upper = _calendar_bounds(events, slots, windows, monday, sunday)
    fig = go.Figure()

    # Availability is a faint background and never masquerades as an accepted session.
    for window in windows:
        if window.day not in position:
            continue
        x = position[window.day]
        fig.add_shape(
            type="rect",
            x0=x - 0.47,
            x1=x + 0.47,
            y0=window.start,
            y1=window.end,
            line=dict(width=0),
            fillcolor="rgba(186,169,208,0.09)",
            layer="below",
        )

    def add_block(day, start, end, label, kind, *, color, line, foreground):
        x = position.get(day)
        if x is None:
            return
        # A filled polygon provides a hover target over the entire event, not only its centre.
        fig.add_trace(
            go.Scatter(
                x=[x - 0.44, x + 0.44, x + 0.44, x - 0.44, x - 0.44],
                y=[start, start, end, end, start],
                mode="lines",
                fill="toself",
                hoveron="fills",
                fillcolor=color,
                line=dict(color=line, width=1),
                name=kind,
                legendgroup=kind,
                showlegend=not any(trace.legendgroup == kind for trace in fig.data),
                hovertemplate=(
                    f"<b>{escape(label)}</b><br>{day:%a %d %b} "
                    f"{format_time(start)}-{format_time(end)}<extra>{kind}</extra>"
                ),
            )
        )
        length = end - start
        if length >= 40:
            display = escape(_short_label(label, 16))
            # A clock label is clearer than rotated text; omit it for narrow sessions.
            if length >= 55:
                display += f"<br>{format_time(start)}-{format_time(end)}"
            fig.add_annotation(
                x=x,
                y=(start + end) / 2,
                text=display,
                showarrow=False,
                align="center",
                font=dict(size=10, color=foreground),
                xanchor="center",
                yanchor="middle",
                bgcolor="rgba(0,0,0,0)",
            )

    for event in sorted(events, key=lambda item: (item.day, item.start, item.title)):
        add_block(
            event.day,
            event.start,
            event.end,
            event.title,
            "Fixed commitment",
            color="#4A5667",
            line="#98A6BD",
            foreground="#F2F4FA",
        )
    for slot in sorted(slots, key=lambda item: (item.day, item.start, item.step_id)):
        step = steps.get(slot.step_id)
        label = step.title if step else "Deleted study step"
        add_block(
            slot.day,
            slot.start,
            slot.end,
            label,
            "Study session",
            color="#655875",
            line="#DDC5F0",
            foreground="#FBF7FF",
        )

    ticks = list(range((lower + 59) // 60 * 60, upper + 1, 60))
    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        height=650,
        margin=dict(l=70, r=18, t=85, b=18),
        paper_bgcolor="#14141A",
        plot_bgcolor="#14141A",
        font=dict(color="#F1EEF5"),
        xaxis=dict(
            range=[-0.55, 6.55],
            tickmode="array",
            tickvals=list(range(7)),
            ticktext=[day.strftime("%a %d") for day in days],
            side="top",
            showgrid=True,
            gridcolor="#393640",
            zeroline=False,
            fixedrange=True,
        ),
        yaxis=dict(
            range=[upper, lower],
            tickmode="array",
            tickvals=ticks,
            ticktext=[format_time(minute) for minute in ticks],
            showgrid=True,
            gridcolor="#393640",
            zeroline=False,
            fixedrange=True,
        ),
        legend=dict(orientation="h", y=1.18, x=0),
        hovermode="closest",
        dragmode=False,
    )
    return fig


def study_label(step) -> str:
    """Never show the internal automatic step label in the calendar."""
    if step is None:
        return "Study"
    parent = getattr(step, "task_title", None)
    if not parent:
        return step.title
    if step.title == "Focus time":
        return parent
    return f"{parent} / {step.title}"


def calendar_html(
    events,
    slots,
    steps,
    first_day,
    last_day,
    *,
    today=None,
    session_links=None,
) -> str:
    """Accessible, aligned CSS calendar for the everyday Day/Week screen.

    Pure rendering: never changes the database or accepts a proposal.
    Every row uses the same pixel-per-minute scale, including the time gutter.
    """
    from html import escape as html_escape

    if last_day < first_day or (last_day - first_day).days > 6:
        raise ValueError("Choose a day or a single calendar week.")
    days = [first_day + timedelta(days=i) for i in range((last_day - first_day).days + 1)]
    lower, upper = _calendar_bounds(events, slots, (), first_day, last_day)
    px_per_minute = 0.85
    total_height = int((upper - lower) * px_per_minute)
    day_count = len(days)
    minimum_width = 375 if day_count == 1 else 880
    markup = [
        """<style>
    .wp-scroll {overflow-x:auto; border:1px solid #343c3b; border-radius:12px;
        background:#171b1c; margin:10px 0 14px;}
    .wp-calendar {display:grid; grid-template-columns:62px repeat(var(--days),minmax(0,1fr));
        min-width:var(--calendar-min); font-family:inherit; color:#dee4df;}
    .wp-day-name {height:45px; display:flex; align-items:center; justify-content:center;
        font-size:12px; font-weight:650; border-left:1px solid #303a38;
        border-bottom:1px solid #343c3b; color:#b8c6bb;}
    .wp-gutter {height:45px; border-bottom:1px solid #343c3b;}
    .wp-clock {position:relative; color:#9ba8a3; font-size:11px;}
    .wp-clock-label {position:absolute; right:9px; transform:translateY(-50%);}
    .wp-day-column {position:relative; border-left:1px solid #303a38;
        background-image:linear-gradient(to bottom,#303a38 1px,transparent 1px);
        background-size:100% 51px; background-repeat:repeat-y;}
    .wp-scroll .wp-calendar .wp-block {position:absolute; left:4px; right:4px; overflow:hidden;
    border-radius:6px;
        text-decoration:none!important; display:block; cursor:pointer;
        padding:5px 6px; font-size:12px; line-height:1.25; box-sizing:border-box;
        border-left:3px solid; overflow-wrap:anywhere;}
    .wp-study {background:#9eb5a1; color:#19231c; border-color:#c6d5c9;}
    .wp-fixed {background:#4c5e68; color:#f1f5f6; border-color:#94a7b0;}
    .wp-lecture {background:#50637a; color:#f6f8fb; border-color:#91b0d1;}
    .wp-social {background:#744F65; color:#fff5f9; border-color:#D99EBB;}
    .wp-exercise {background:#465e58; color:#e3f9ed; border-color:#7db49a;}
    .wp-personal {background:#6b5d53; color:#fff6eb; border-color:#bd9f7e;}
    .wp-appointment {background:#4c5e68; color:#f1f5f6; border-color:#94a7b0;}
    .wp-other {background:#555b61; color:#f1f5f6; border-color:#929da6;}
    .wp-block:hover {filter:brightness(1.12); outline:1px solid #d7e1da;}
    .wp-scroll .wp-calendar a.wp-block:link,.wp-scroll .wp-calendar a.wp-block:visited,
    .wp-scroll .wp-calendar a.wp-block:hover {text-decoration:none!important;
    color:inherit!important;}
    .wp-scroll .wp-calendar .wp-study,.wp-scroll .wp-calendar a.wp-study:link,
    .wp-scroll .wp-calendar a.wp-study:visited {color:#19231c!important;}
    .wp-scroll .wp-calendar .wp-lecture,.wp-scroll .wp-calendar a.wp-lecture:link,
    .wp-scroll .wp-calendar a.wp-lecture:visited {color:#f6f8fb!important;}
    .wp-scroll .wp-calendar .wp-social,.wp-scroll .wp-calendar a.wp-social:link,
    .wp-scroll .wp-calendar a.wp-social:visited {color:#fff5f9!important;}
    .wp-scroll .wp-calendar .wp-block-title,.wp-scroll .wp-calendar .wp-block-clock {
        color:inherit!important;text-decoration:none!important;}
    .wp-block-title {font-weight:650; display:-webkit-box; -webkit-line-clamp:2;
        -webkit-box-orient:vertical; overflow:hidden;}
    .wp-block-clock {font-size:10px; opacity:.82; margin-top:2px;}
    .wp-priority {display:inline-block;font-weight:750;font-size:10px;
        border-radius:12px;padding:1px 5px;margin:2px 0;
        border:1px solid;letter-spacing:.01em;}
    .wp-high {color:#752D31;background:#FFE9E8;border-color:#DF8788;}
    .wp-medium {color:#65502D;background:#F5EEDB;border-color:#D4BC85;}
    .wp-low {color:#334B3D;background:#E2ECE5;border-color:#9AAC9F;}
    .wp-next {font-size:10px;opacity:.90;white-space:nowrap;
        overflow:hidden;text-overflow:ellipsis;}
    .wp-today {color:#d9efdc; background:#27332e;}
    </style>""",
        CALENDAR_CSS,
    ]
    markup.append(
        f'<div class="wp-scroll"><div class="wp-calendar" '
        f'style="--days:{day_count};--calendar-min:{minimum_width}px">'
    )
    markup.append('<div class="wp-gutter"></div>')
    for day in days:
        today_style = " wp-today" if day == today else ""
        markup.append(f'<div class="wp-day-name{today_style}">{day:%a %d %b}</div>')
    markup.append(f'<div class="wp-clock" style="height:{total_height}px">')
    for minute in range(((lower + 59) // 60) * 60, upper, 60):
        top = (minute - lower) * px_per_minute
        markup.append(
            f'<div class="wp-clock-label" style="top:{top:.1f}px">{format_time(minute)}</div>'
        )
    markup.append("</div>")
    pending_checklists = {}
    for step in steps.values():
        if getattr(step, "kind", None) == "checklist" and not step.checked:
            pending_checklists.setdefault(step.task_id, []).append(step.title)
    for day in days:
        markup.append(f'<div class="wp-day-column" style="height:{total_height}px">')
        blocks = [
            (
                e.start,
                e.end,
                e.title,
                getattr(e, "kind", "Appointment").lower(),
                f"event={e.id}&date={e.day.isoformat()}" if getattr(e, "id", None) else None,
            )
            for e in events
            if e.day == day
        ] + [
            (
                slot.start,
                slot.end,
                study_label(steps.get(slot.step_id)),
                "study",
                f"session={session_links[(slot.step_id, slot.day, slot.start, slot.end)]}"
                f"&date={slot.day.isoformat()}"
                if session_links and (slot.step_id, slot.day, slot.start, slot.end) in session_links
                else None,
            )
            for slot in slots
            if slot.day == day
        ]
        for start, end, name, kind, target in sorted(blocks, key=lambda b: (b[0], b[1], b[2])):
            # Share horizontal space when a saved study block conflicts with an event.
            # Both remain selectable instead of hiding one another.
            conflict = any(
                other_start < end
                and start < other_end
                and (other_kind == "study") != (kind == "study")
                for other_start, other_end, _, other_kind, _ in blocks
            )
            lane_style = (
                "left:50%;" if conflict and kind == "study" else ("right:50%;" if conflict else "")
            )
            top = (start - lower) * px_per_minute
            height = max(8, (end - start) * px_per_minute)
            safe_title = html_escape(name, quote=True)
            related_step = None
            if kind == "study":
                related_step = next(
                    (
                        steps.get(slot.step_id)
                        for slot in slots
                        if slot.day == day
                        and slot.start == start
                        and slot.end == end
                        and study_label(steps.get(slot.step_id)) == name
                    ),
                    None,
                )
            next_item = (
                pending_checklists.get(getattr(related_step, "task_id", None), [None])[0]
                if related_step
                else None
            )
            due = getattr(related_step, "deadline", None) if related_step else None
            due_note = f" | Due {due:%d/%m}" if due else ""
            tooltip = html_escape(
                f"{name} | {day:%a %d %b} | {format_time(start)}–{format_time(end)}"
                + due_note
                + (f" | Next: {next_item}" if next_item else ""),
                quote=True,
            )
            tag = "a" if target else "div"
            link = f' href="?{target}" target="_self"' if target else ""
            markup.append(
                f'<{tag} class="wp-block wp-{kind}" title="{tooltip}"{link} '
                f'style="top:{top:.1f}px;height:{height:.1f}px;{lane_style}">'
                f'<div class="wp-block-title">{safe_title}</div>'
            )
            if related_step and height >= 35:
                priority = {3: "high", 2: "medium", 1: "low"}.get(
                    getattr(related_step, "priority", 1),
                    "low",
                )
                markup.append(
                    f'<span class="wp-priority wp-{priority}">{priority.capitalize()}</span>'
                )
            if next_item and height >= 74:
                markup.append(f'<div class="wp-next">Next: {html_escape(next_item)}</div>')
            if height >= 45:
                markup.append(
                    f'<div class="wp-block-clock">{format_time(start)}–{format_time(end)}</div>'
                )
            markup.append(f"</{tag}>")
        markup.append("</div>")
    markup.append("</div></div>")
    return "".join(markup)


def _agenda(events, slots, steps, monday, sunday):
    """Accessible text companion to the time grid; sorted independently of rendering."""
    entries = []
    for event in events:
        if monday <= event.day <= sunday:
            entries.append(
                (
                    event.day,
                    event.start,
                    event.end,
                    getattr(event, "kind", "Appointment"),
                    event.title,
                )
            )
    for slot in slots:
        if monday <= slot.day <= sunday:
            step = steps.get(slot.step_id)
            label = study_label(step)
            entries.append((slot.day, slot.start, slot.end, "Study", label))
    return tuple(sorted(entries, key=lambda row: (row[0], row[1], row[3], row[4])))


def _save_or_report(action):
    try:
        message = action()
    except (ValueError, sqlite3.Error, OSError) as exc:
        if not isinstance(exc, ValueError):
            logging.exception("Could not update the weekly planner")
            st.error("Could not save planner data. See the terminal for details.")
        else:
            st.error(str(exc))
        return
    st.session_state["calendar_notice"] = message or "Saved."
    st.session_state.pop("calendar_proposal", None)
    st.rerun()


def render_weekly_calendar(db_path: Path) -> None:
    st.subheader("Hourly weekly calendar")
    st.caption(
        "Only accepted study sessions are saved. Preview, compare, then accept or reject "
        "a revision. Fixed lectures and appointments are never moved."
    )
    try:
        snapshot = load_snapshot(db_path)
    except (sqlite3.Error, OSError, ValueError):
        logging.exception("Cannot load advanced planning data")
        st.error("Unable to load the hourly calendar from SQLite.")
        st.stop()
        return
    notice = st.session_state.pop("calendar_notice", None)
    if notice:
        st.success(notice)
    now = datetime.now()
    today = now.date()
    monday, sunday = week_bounds(today)
    steps = {item.id: item for item in snapshot.steps}
    planned = [
        session
        for session in snapshot.sessions
        if session.status == "planned" and monday <= session.day <= sunday
    ]
    conflicts = accepted_conflicts(snapshot, now)
    if conflicts:
        st.error(
            f"{len(conflicts)} accepted session(s) need review. The saved timetable has "
            "not been changed automatically."
        )
        for issue in conflicts[:5]:
            st.caption(issue)

    calendar_tab, setup_tab, review_tab = st.tabs(
        ["Accepted calendar", "Time windows & commitments", "Preview a new plan"]
    )

    with calendar_tab:
        slots = [Slot(s.step_id, s.day, s.start, s.end) for s in planned]
        st.plotly_chart(
            _chart(
                snapshot.events,
                slots,
                steps,
                monday,
                sunday,
                title="Saved weekly timetable",
                windows=snapshot.windows,
            ),
            width="stretch",
            config={"displayModeBar": False},
        )
        st.caption(
            "Days run Monday-Sunday; time runs downward. Sage = saved study sessions; "
            "slate = fixed commitments; faint sage = available windows. "
            "Scheduled time is not automatically completed work."
        )
        with st.expander("Full weekly agenda (times and complete titles)"):
            entries = _agenda(snapshot.events, slots, steps, monday, sunday)
            if not entries:
                st.caption("No accepted sessions or commitments this week.")
            for day, start, end, kind, label in entries:
                st.write(
                    f"**{day:%a %d %b} · {format_time(start)}-{format_time(end)}** "
                    f"· {kind} · {label}"
                )
        if planned:
            st.markdown("**Record progress or a missed session**")
            for session in sorted(planned, key=lambda s: (s.day, s.start)):
                step = steps.get(session.step_id)
                if step is None:
                    continue
                with st.container(border=True):
                    detail, amount_col, action_col = st.columns([4, 1.3, 2.5])
                    with detail:
                        st.markdown(f"**{step.task_title} · {step.title}**")
                        st.caption(
                            f"{session.day:%a %d %b} · "
                            f"{format_time(session.start)}–{format_time(session.end)} · "
                            f"{step.remaining_minutes} min remain"
                        )
                    with amount_col:
                        amount = st.number_input(
                            "Minutes worked",
                            min_value=1,
                            max_value=max(1, step.remaining_minutes),
                            value=min(session.end - session.start, max(1, step.remaining_minutes)),
                            key=f"actual_{session.id}",
                        )
                    with action_col:
                        started = session.day < today or (
                            session.day == today and session.start <= now.hour * 60 + now.minute
                        )
                        ended = session.day < today or (
                            session.day == today and session.end <= now.hour * 60 + now.minute
                        )
                        done_col, missed_col = st.columns(2)
                        with done_col:
                            if st.button(
                                "Log work",
                                key=f"done_session_{session.id}",
                                disabled=not started or step.remaining_minutes == 0,
                            ):
                                _save_or_report(
                                    lambda: (
                                        record_session(db_path, session.id, "done", amount),
                                        f"Logged {amount} minutes. "
                                        "Review a new plan for unfinished work.",
                                    )[1]
                                )
                        with missed_col:
                            if st.button(
                                "Missed", key=f"miss_session_{session.id}", disabled=not ended
                            ):
                                _save_or_report(
                                    lambda: (
                                        record_session(db_path, session.id, "missed"),
                                        "Session marked missed. "
                                        "Preview a plan for unfinished work.",
                                    )[1]
                                )
        else:
            st.info(
                "No accepted study sessions this week. Add windows and timed steps, "
                "then preview a plan."
            )

    with setup_tab:
        st.caption(
            "Add one or more real calendar-date windows for study. Lectures, appointments, "
            "and other fixed commitments block those windows automatically."
        )
        with st.form("add_hour_window", clear_on_submit=True):
            st.markdown("**Add available time**")
            w_day = st.date_input(
                "Available date", value=today, min_value=today, key="hour_window_day"
            )
            w_cols = st.columns(2)
            with w_cols[0]:
                w_start = st.time_input("Available from", value=time(9, 0), step=900)
            with w_cols[1]:
                w_end = st.time_input("Available until", value=time(12, 0), step=900)
            w_save = st.form_submit_button("Add time window")
        if w_save:
            _save_or_report(
                lambda: (
                    add_window(db_path, w_day, _minute(w_start), _minute(w_end)),
                    "Time window saved.",
                )[1]
            )

        with st.form("add_fixed_event", clear_on_submit=True):
            st.markdown("**Add a fixed lecture or commitment**")
            e_title = st.text_input("Commitment name", max_chars=120)
            e_day = st.date_input("Commitment date", value=today, key="fixed_event_day")
            e_cols = st.columns(2)
            with e_cols[0]:
                e_start = st.time_input("Commitment starts", value=time(10, 0), step=900)
            with e_cols[1]:
                e_end = st.time_input("Commitment ends", value=time(11, 0), step=900)
            e_save = st.form_submit_button("Add fixed commitment")
        if e_save:
            _save_or_report(
                lambda: (
                    add_fixed_event(db_path, e_title, e_day, _minute(e_start), _minute(e_end)),
                    "Commitment saved. Any conflicting accepted sessions are now flagged.",
                )[1]
            )

        with st.expander("Manage this week's saved windows and commitments"):
            for window in snapshot.windows:
                if monday <= window.day <= sunday:
                    left, right = st.columns([4, 1])
                    with left:
                        st.write(
                            f"Available · {window.day:%a %d %b} "
                            f"{format_time(window.start)}–{format_time(window.end)}"
                        )
                    with right:
                        if st.button("Remove", key=f"remove_window_{window.id}"):
                            _save_or_report(
                                lambda win=window: (
                                    delete_window(db_path, win.id),
                                    "Time window removed.",
                                )[1]
                            )
            for event in snapshot.events:
                if monday <= event.day <= sunday:
                    left, right = st.columns([4, 1])
                    with left:
                        st.write(
                            f"{event.title} · {event.day:%a %d %b} "
                            f"{format_time(event.start)}–{format_time(event.end)}"
                        )
                    with right:
                        if st.button("Remove", key=f"remove_event_{event.id}"):
                            _save_or_report(
                                lambda ev=event: (
                                    delete_fixed_event(db_path, ev.id),
                                    "Commitment removed.",
                                )[1]
                            )

    with review_tab:
        timed = [
            step
            for step in snapshot.steps
            if step.kind == "timed" and not step.parent_completed and step.remaining_minutes
        ]
        if not timed:
            st.info(
                "Add timed steps beneath an open task in Tasks & Projects to generate a timetable."
            )
        existing = st.session_state.get("calendar_proposal")
        if st.button("Preview a new plan", type="primary", disabled=not timed):
            proposal_now = datetime.now()
            proposal = make_revision(snapshot, proposal_now, preserve_existing=True)
            baseline = make_revision(snapshot, proposal_now, preserve_existing=False)
            st.session_state["calendar_proposal"] = (proposal, baseline)
            existing = (proposal, baseline)
        if existing:
            proposal, baseline = existing
            if proposal.fingerprint != snapshot.fingerprint:
                st.warning("Tasks or commitments changed after preview. Generate a fresh proposal.")
            st.markdown("**Proposed schedule — not yet saved**")
            st.plotly_chart(
                _chart(
                    snapshot.events,
                    proposal.slots,
                    steps,
                    proposal.monday,
                    proposal.sunday,
                    title="Proposed week",
                    windows=snapshot.windows,
                ),
                width="stretch",
                config={"displayModeBar": False},
            )
            m1, m2, m3 = st.columns(3)
            m1.metric("Work allocated", f"{proposal.planned_minutes} min")
            m2.metric("Unchanged sessions", proposal.unchanged)
            m3.metric("Moved / removed sessions", proposal.removed_or_changed)
            st.caption(
                f"Minimal-change heuristic: {proposal.removed_or_changed} previous sessions "
                f"changed, {proposal.added_or_changed} added/changed. "
                f"Full-reschedule baseline changes {baseline.removed_or_changed} previous sessions "
                f"and allocates {baseline.planned_minutes} minutes. "
                "Both approaches are greedy, not optimality guarantees."
            )
            old_keys = {(s.step_id, s.day, s.start, s.end) for s in planned}
            proposed_keys = {(s.step_id, s.day, s.start, s.end) for s in proposal.slots}
            for session in planned:
                old_key = (session.step_id, session.day, session.start, session.end)
                if old_key not in proposed_keys:
                    previous_step = steps.get(session.step_id)
                    if previous_step:
                        st.write(
                            f"Moved / removed from accepted plan · "
                            f"**{previous_step.task_title} / {previous_step.title}** · "
                            f"{session.day:%a %d %b} "
                            f"{format_time(session.start)}–{format_time(session.end)}"
                        )
            for slot in proposal.slots:
                step = steps.get(slot.step_id)
                if step is None:
                    continue
                label = (
                    "Unchanged"
                    if (slot.step_id, slot.day, slot.start, slot.end) in old_keys
                    else "New / rescheduled"
                )
                st.write(
                    f"{label} · **{step.task_title} / {step.title}** · "
                    f"{slot.day:%a %d %b} {format_time(slot.start)}–{format_time(slot.end)}"
                )
            if proposal.shortfalls:
                st.markdown("**Work the heuristic could not fit**")
                for item in proposal.shortfalls:
                    step = steps[item.step_id]
                    desc = {
                        "overdue": "overdue — not scheduled after deadline",
                        "could_not_fit": "could not fit before the deadline",
                        "outside_week": "outside this week's planning horizon",
                    }[item.reason]
                    due = step.deadline.strftime("%d %b") if step.deadline else "no deadline"
                    st.warning(
                        f"{step.task_title} / {step.title}: {item.minutes} min · "
                        f"due {due} · {desc}."
                    )
            else:
                st.success("All timed work in this proposal is accounted for this week.")
            accept_col, reject_col = st.columns(2)
            with accept_col:
                if st.button(
                    "Accept proposed schedule",
                    type="primary",
                    disabled=proposal.fingerprint != snapshot.fingerprint,
                ):
                    try:
                        saved_count = accept_revision(db_path, proposal, datetime.now())
                    except (StaleProposalError, ValueError) as error:
                        st.error(str(error))
                    except (sqlite3.Error, OSError):
                        logging.exception("Could not commit schedule")
                        st.error("The revision could not be saved; the old schedule remains.")
                    else:
                        st.session_state.pop("calendar_proposal", None)
                        st.session_state["calendar_notice"] = (
                            f"Accepted {saved_count} sessions. They will persist after restart."
                        )
                        st.rerun()
            with reject_col:
                if st.button("Reject / discard proposal"):
                    st.session_state.pop("calendar_proposal", None)
                    st.info("Proposal discarded. Accepted calendar is unchanged.")
        else:
            st.caption("Generate a preview. Nothing changes until you select Accept.")
