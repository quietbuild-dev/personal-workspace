"""Export accepted local calendar events as a portable iCalendar file.

No external calendar API, login, or network access is involved. Floating local
DTSTART/DTEND values let calendar clients interpret the user's local times.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from workspace.advanced_planner import PlannerSnapshot


def _escape(value: str) -> str:
    """Escape text according to RFC 5545 TEXT encoding."""
    return (
        value.replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def _date_time(day: date, minute: int) -> str:
    if not 0 <= minute <= 1440:
        raise ValueError("Calendar minutes must be between 0 and 1440.")
    return (datetime.combine(day, datetime.min.time()) + timedelta(minutes=minute)).strftime(
        "%Y%m%dT%H%M%S"
    )


def _fold(line: str) -> list[str]:
    """Fold long content lines at 75 UTF-8 octets (RFC 5545)."""
    result = []
    current = ""
    for character in line:
        allowance = 75 if not result else 74  # continuation begins with a space
        if len((current + character).encode("utf-8")) > allowance:
            result.append((" " if result else "") + current)
            current = character
        else:
            current += character
    result.append((" " if result else "") + current)
    return result


def build_calendar_ics(
    snapshot: PlannerSnapshot, *, start_day: date | None = None, end_day: date | None = None
) -> bytes:
    """Create a .ics download of fixed events and accepted planned study sessions.

    Proposed (not yet accepted) schedules are deliberately excluded. Completed
    sessions are excluded to avoid presenting historical study as future bookings.
    """
    if start_day is not None and end_day is not None and start_day > end_day:
        raise ValueError("Start date must be on or before end date.")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Personal Workspace//Local Schedule//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Personal Workspace",
    ]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    steps = {step.id: step for step in snapshot.steps}

    def in_range(day: date) -> bool:
        return (start_day is None or day >= start_day) and (end_day is None or day <= end_day)

    def add_event(uid: str, title: str, day: date, start: int, end: int, description: str):
        if not in_range(day):
            return
        lines.extend(
            (
                "BEGIN:VEVENT",
                "UID:" + uid + "@personal-workspace.local",
                "DTSTAMP:" + stamp,
                "DTSTART:" + _date_time(day, start),
                "DTEND:" + _date_time(day, end),
                "SUMMARY:" + _escape(title),
                "DESCRIPTION:" + _escape(description),
                "END:VEVENT",
            )
        )

    for event in snapshot.events:
        add_event(f"fixed-{event.id}", event.title, event.day, event.start, event.end, event.kind)
    for session in snapshot.sessions:
        if session.status != "planned":
            continue
        step = steps.get(session.step_id)
        if step is None:
            continue
        title = f"Study: {step.task_title}"
        if step.title and step.title != step.task_title:
            title += f" - {step.title}"
        add_event(
            f"study-{session.id}",
            title,
            session.day,
            session.start,
            session.end,
            "Accepted study block from Personal Workspace",
        )
    lines.append("END:VCALENDAR")
    return ("\r\n".join(fragment for line in lines for fragment in _fold(line)) + "\r\n").encode(
        "utf-8"
    )


def save_calendar_to_downloads(
    ics_content: bytes, selected_week_start: date, downloads_dir: Path | None = None
) -> Path:
    """Save an explicit local export without overwriting an existing .ics file."""
    folder = Path.home() / "Downloads" if downloads_dir is None else Path(downloads_dir)
    if not folder.is_dir():
        raise FileNotFoundError(f"Downloads folder not found: {folder}")
    name = f"personal-workspace-{selected_week_start.isoformat()}"
    for sequence in range(1, 1001):
        suffix = "" if sequence == 1 else f"-{sequence}"
        output = folder / f"{name}{suffix}.ics"
        try:
            with output.open("xb") as stream:
                stream.write(ics_content)
        except FileExistsError:
            continue
        return output
    raise FileExistsError("There are already too many copies of this calendar export.")
