"""Safe Calendar .ics import: inspect, select, and explicitly approve events."""

import logging
import sqlite3

import streamlit as st

from workspace.advanced_planner import format_time
from workspace.advanced_repository import StaleProposalError
from workspace.calendar_import import (
    eligibility,
    import_selected,
    imported_keys,
    parse_ics,
)


def render_calendar_import(snapshot, db_path) -> None:
    with st.expander("Import commitments · .ics file", expanded=False):
        st.caption(
            "Import selected events from Google, Apple, or Outlook exports. "
            "Preview only until you confirm; nothing is sent online."
        )
        upload = st.file_uploader(
            "Choose .ics file", type=["ics"], key="calendar_import_file"
        )
        if upload is None:
            return
        try:
            parsed = parse_ics(upload.getvalue())
            known = imported_keys(db_path)
        except (ValueError, sqlite3.Error, OSError) as error:
            st.error(str(error))
            return
        st.caption(f"{len(parsed.events)} supported events found")
        for warning in parsed.warnings[:8]:
            st.warning(warning)
        if len(parsed.warnings) > 8:
            st.caption(f"+{len(parsed.warnings) - 8} more warnings")
        statuses = {item.key: eligibility(snapshot, item, known) for item in parsed.events}
        ready = {item.key: item for item in parsed.events if statuses[item.key] == "Ready"}
        for item in parsed.events[:12]:
            status = statuses[item.key]
            st.caption(
                f"{item.day:%d %b} · {format_time(item.start)}–"
                f"{format_time(item.end)} · {item.title} — {status}"
            )
        if len(parsed.events) > 12:
            st.caption(f"+{len(parsed.events) - 12} more events")
        if not ready:
            st.info("No conflict-free events are available to import.")
            return
        selected = st.multiselect(
            "Select events to add", options=list(ready),
            format_func=lambda key: (
                f"{ready[key].day:%d %b} {format_time(ready[key].start)} · "
                f"{ready[key].title}"
            ),
            key="calendar_import_selected",
        )
        kind = st.selectbox(
            "Category for imported events",
            ["Appointment", "Lecture", "Personal", "Social", "Exercise", "Other"],
            key="calendar_import_category",
        )
        if st.button(
            f"Import {len(selected)} selected events", type="primary",
            disabled=not bool(selected), key="calendar_import_commit",
        ):
            try:
                count = import_selected(
                    db_path, parsed.events, frozenset(selected), snapshot.fingerprint,
                    kind=kind,
                )
            except (StaleProposalError, ValueError) as error:
                st.error(str(error))
            except (sqlite3.Error, OSError):
                logging.exception("Calendar import failed")
                st.error("Import failed and was rolled back. Your saved calendar is unchanged.")
            else:
                st.session_state.pop("calendar_import_selected", None)
                st.session_state["calendar_message"] = (
                    f"Imported {count} commitment(s). Review study conflicts in Calendar."
                )
                st.rerun()
        st.caption(
            "Duplicate and overlapping events are excluded; selected overlaps are rejected. "
            "Recurring and multi-day events are skipped with warnings. "
            "UTC/TZID timestamps are converted to this computer's local timezone."
        )
