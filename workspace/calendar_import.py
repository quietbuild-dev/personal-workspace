"""Safe, offline, deliberately bounded .ics import for fixed calendar commitments.

Supports single-day timed events (floating, UTC, or IANA TZID) and one-day
all-day events. Recurrences, overnight/multi-day events, and unsupported
zones are explicitly reported and skipped, never silently misinterpreted.

Parsing and preview have no side effects. Selected events save atomically with
an expected planner fingerprint, so no unreviewed changes reach the database.
"""

from __future__ import annotations

import hashlib
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from workspace.advanced_planner import PlannerSnapshot
from workspace.advanced_repository import (
    EVENT_KINDS,
    StaleProposalError,
    _connect,
    _fetch_snapshot,
    initialize_advanced,
)

MAX_FILE_BYTES = 1_500_000
MAX_EVENTS = 200


@dataclass(frozen=True)
class ImportedEvent:
    key: str
    title: str
    day: date
    start: int
    end: int
    all_day: bool = False


@dataclass(frozen=True)
class ImportPreview:
    events: tuple[ImportedEvent, ...]
    warnings: tuple[str, ...]


def _lines(payload: bytes) -> list[str]:
    if not isinstance(payload, bytes) or not payload:
        raise ValueError("Choose a nonempty .ics file.")
    if len(payload) > MAX_FILE_BYTES:
        raise ValueError("The .ics file exceeds the 1.5 MB preview limit.")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Please export a UTF-8 .ics file.") from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    unfolded: list[str] = []
    for line in text.split("\n"):
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def _text(value: str) -> str:
    """Unescape RFC 5545 text without interpreting markup or HTML."""
    out = []
    index = 0
    while index < len(value):
        if value[index] == "\\" and index + 1 < len(value):
            next_char = value[index + 1]
            out.append({"n": " ", "N": " ", ",": ",", ";": ";", "\\": "\\"}.get(
                next_char, "\\" + next_char
            ))
            index += 2
        else:
            out.append(value[index])
            index += 1
    return " ".join("".join(out).split())


def _property(line: str):
    if ":" not in line:
        return None
    header, value = line.split(":", 1)
    parts = header.split(";")
    name = parts[0].upper()
    params = {}
    for part in parts[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            params[k.upper()] = v.strip('"')
    return name, params, value


def _read_datetime(params: dict, value: str) -> tuple[date, int, bool]:
    if params.get("VALUE", "").upper() == "DATE" or (
        len(value) == 8 and value.isdigit()
    ):
        d = datetime.strptime(value, "%Y%m%d").date()
        return d, 0, True
    if value.endswith("Z"):
        parsed = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    else:
        parsed = datetime.strptime(value, "%Y%m%dT%H%M%S")
        tzid = params.get("TZID")
        if tzid:
            try:
                parsed = parsed.replace(tzinfo=ZoneInfo(tzid))
            except ZoneInfoNotFoundError as exc:
                raise ValueError(f"Unrecognized timezone: {tzid}") from exc
    if parsed.tzinfo:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed.date(), parsed.hour * 60 + parsed.minute, False


def _event(fields: dict) -> ImportedEvent:
    if any(name in fields for name in ("RRULE", "RDATE", "RECURRENCE-ID", "EXDATE")):
        raise ValueError("Recurring events need expansion and are not supported yet")
    if fields.get("STATUS", ({}, ""))[1].upper() == "CANCELLED":
        raise ValueError("Cancelled event")
    if "DTSTART" not in fields or "DTEND" not in fields:
        raise ValueError("Missing start or finish")
    start_day, start, start_all_day = _read_datetime(*fields["DTSTART"])
    end_day, end, end_all_day = _read_datetime(*fields["DTEND"])
    if start_all_day != end_all_day:
        raise ValueError("Mixed all-day and timed endpoints")
    if start_all_day:
        if (end_day - start_day).days != 1:
            raise ValueError("Multi-day or zero-day event not supported")
        end = 1440
    elif start_day != end_day:
        raise ValueError("Overnight or multi-day event not supported")
    if not 0 <= start < end <= 1440:
        raise ValueError("Invalid event duration or time")
    raw_title = fields.get("SUMMARY", ({}, "Untitled event"))[1]
    title = _text(raw_title) or "Untitled event"
    if len(title) > 120:
        title = title[:117] + "..."
    uid = fields.get("UID", ({}, ""))[1].strip()
    # RFC UID is globally unique. For files with no UID, derive a stable
    # identity from the displayed event so reimports still detect duplicates.
    identity = ("uid\0" + uid) if uid else (
        f"fallback\0{title}\0{start_day.isoformat()}\0{start}\0{end}"
    )
    key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return ImportedEvent(key, title, start_day, start, end, start_all_day)


def parse_ics(payload: bytes) -> ImportPreview:
    lines = _lines(payload)
    if not any(line.upper() == "BEGIN:VCALENDAR" for line in lines) or not any(
        line.upper() == "END:VCALENDAR" for line in lines
    ):
        raise ValueError("Not a complete iCalendar (.ics) file.")
    result: list[ImportedEvent] = []
    warnings = []
    fields = {}
    in_event = False
    nested = 0
    count = 0
    seen = set()
    for line in lines:
        tag = line.upper()
        if tag == "BEGIN:VEVENT":
            if in_event:
                raise ValueError("Malformed nested VEVENT in .ics file.")
            in_event, nested, fields = True, 0, {}
            count += 1
            if count > MAX_EVENTS:
                raise ValueError("The file has more than 200 events. Export a smaller range.")
        elif tag == "END:VEVENT":
            if not in_event or nested:
                raise ValueError("Malformed VEVENT in .ics file.")
            in_event = False
            try:
                entry = _event(fields)
            except (ValueError, OverflowError) as error:
                warnings.append(f"Event {count} skipped: {error}.")
            else:
                if entry.key in seen:
                    warnings.append(f"Event {count} skipped: duplicate UID in file.")
                else:
                    seen.add(entry.key)
                    result.append(entry)
        elif in_event:
            if tag.startswith("BEGIN:"):
                nested += 1
            elif tag.startswith("END:"):
                nested -= 1
                if nested < 0:
                    raise ValueError("Malformed nested iCalendar component.")
            elif nested == 0:
                parsed = _property(line)
                if parsed:
                    name, params, value = parsed
                    if name in (
                        "DTSTART", "DTEND", "SUMMARY", "UID", "RRULE", "RDATE",
                        "RECURRENCE-ID", "EXDATE", "STATUS",
                    ):
                        fields[name] = (params, value)
    if in_event:
        raise ValueError("Incomplete VEVENT in .ics file.")
    if count == 0:
        warnings.append("No events found in the file.")
    return ImportPreview(tuple(result), tuple(warnings))


def imported_keys(db_path: Path) -> frozenset[str]:
    """Read-only lookup, even on an old database without import metadata."""
    if not db_path.is_file():
        return frozenset()
    with closing(_connect(db_path)) as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='calendar_import_receipts'"
        ).fetchone()
        if not exists:
            return frozenset()
        return frozenset(
            row[0] for row in conn.execute("SELECT source_key FROM calendar_import_receipts")
        )


def eligibility(
    snapshot: PlannerSnapshot, item: ImportedEvent, known_keys: frozenset[str]
) -> str:
    if item.key in known_keys:
        return "Already imported"
    for event in snapshot.events:
        if event.day != item.day:
            continue
        if (event.start, event.end, event.title.casefold()) == (
            item.start, item.end, item.title.casefold()
        ):
            return "Already on calendar"
        if event.start < item.end and item.start < event.end:
            return "Overlaps a fixed commitment"
    for session in snapshot.sessions:
        if session.status == "planned" and session.day == item.day:
            if session.start < item.end and item.start < session.end:
                return "Overlaps accepted study"
    return "Ready"


def import_selected(
    db_path: Path,
    entries: tuple[ImportedEvent, ...],
    selected_keys: frozenset[str],
    expected_fingerprint: str,
    *, kind: str = "Appointment",
) -> int:
    """All-or-nothing import after freshness, eligibility and pairwise conflict checks."""
    if kind not in EVENT_KINDS:
        raise ValueError("Choose a supported event category.")
    if not selected_keys or not isinstance(selected_keys, frozenset):
        raise ValueError("Select at least one event to import.")
    if len(selected_keys) > MAX_EVENTS:
        raise ValueError("Too many events selected.")
    selected = [entry for entry in entries if entry.key in selected_keys]
    if len(selected) != len(selected_keys):
        raise ValueError("Invalid selection. Preview the file again.")
    initialize_advanced(db_path)
    with closing(_connect(db_path)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS calendar_import_receipts ("
                "source_key TEXT PRIMARY KEY, "
                "event_id INTEGER NOT NULL REFERENCES fixed_events(id) ON DELETE CASCADE)"
            )
            latest = _fetch_snapshot(conn)
            if latest.fingerprint != expected_fingerprint:
                raise StaleProposalError("Calendar changed. Preview the import again.")
            known = frozenset(
                row[0] for row in conn.execute("SELECT source_key FROM calendar_import_receipts")
            )
            for item in selected:
                status = eligibility(latest, item, known)
                if status != "Ready":
                    raise ValueError(f"Cannot import '{item.title}': {status}.")
            for i, first in enumerate(selected):
                for other in selected[i + 1:]:
                    same_day = first.day == other.day
                    overlapping = first.start < other.end and other.start < first.end
                    if same_day and overlapping:
                        raise ValueError("Two selected events overlap. Import one at a time.")
            for item in selected:
                event_id = conn.execute(
                    "INSERT INTO fixed_events(title,day,start_minute,end_minute) "
                    "VALUES (?,?,?,?)",
                    (item.title, item.day.isoformat(), item.start, item.end),
                ).lastrowid
                conn.execute(
                    "INSERT INTO fixed_event_kinds(event_id,kind) VALUES (?,?)",
                    (event_id, kind),
                )
                conn.execute(
                    "INSERT INTO calendar_import_receipts(source_key,event_id) VALUES (?,?)",
                    (item.key, event_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return len(selected)
