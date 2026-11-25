"""Deterministic, offline draft capture. All inferred fields require user confirmation."""

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

from workspace.models import TaskDraft

_MONTHS = {name.lower(): month for month in range(1, 13) for name in (
    calendar.month_name[month], calendar.month_abbr[month]
)}
_MONTH_WORDS = "|".join(sorted(map(re.escape, _MONTHS), key=len, reverse=True))
_DATE_TEXT = (
    rf"(?:\d{{4}}-\d{{2}}-\d{{2}}|(?:{_MONTH_WORDS})\s+\d{{1,2}}"
    r"(?:\s*,?\s*\d{4})?|today|tomorrow)"
)
_DUE_RE = re.compile(rf"\b(?:due(?:\s+on)?|by|deadline(?:\s+on)?)\s+(?P<date>{_DATE_TEXT})\b", re.I)
_STANDALONE_DATE_RE = re.compile(rf"^(?P<date>{_DATE_TEXT})$", re.I)
_TIME_RE = re.compile(
    r"(?<!\w)(?P<amount>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>hours?|hrs?|hr|h|minutes?|mins?|min|m)\b", re.I
)
_PRIORITY_RE = re.compile(
    r"\b(?:(?P<level>high|medium|normal|low)\s+priority|"
    r"priority\s*:?\s*(?P<reversed>high|medium|normal|low))\b", re.I
)


@dataclass(frozen=True)
class CaptureDraft:
    title: str
    category: str
    deadline: date | None
    priority: int
    estimate_minutes: int
    notes: tuple[str, ...]


def _read_date(value: str, today: date) -> tuple[date | None, str | None]:
    text = value.strip().lower()
    if text == "today":
        return today, None
    if text == "tomorrow":
        return today + timedelta(days=1), None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            return date.fromisoformat(text), None
        except ValueError:
            return None, "The deadline date is invalid. Choose a date manually."
    match = re.fullmatch(
        rf"(?P<month>{_MONTH_WORDS})\s+(?P<day>\d{{1,2}})"
        r"(?:\s*,?\s*(?P<year>\d{4}))?", text
    )
    if match is None:
        return None, "Deadline not understood. Choose a date manually."
    month, day = _MONTHS[match.group("month")], int(match.group("day"))
    explicit = match.group("year") is not None
    year = int(match.group("year")) if explicit else today.year
    try:
        resolved = date(year, month, day)
        if not explicit and resolved < today:
            resolved = date(year + 1, month, day)
            return resolved, f"Assumed {resolved.year} for the date without a year."
        return resolved, None
    except ValueError:
        return None, "The deadline date is invalid. Choose a date manually."


def parse_task_text(text: str, today: date, categories=()) -> CaptureDraft:
    """Extract explicit date/duration/priority fields; never write to storage."""
    if not isinstance(text, str) or len(text) > 1500:
        raise ValueError("Enter up to 1,500 characters of task details.")
    if type(today) is not date:
        raise ValueError("Today's calendar date must be provided.")
    source = text.strip()
    if not source:
        raise ValueError("Describe a task before parsing it.")
    notes: list[str] = []
    deadline = None
    date_match = _DUE_RE.search(source)
    if date_match:
        deadline, note = _read_date(date_match.group("date"), today)
        if note:
            notes.append(note)
        source = source[:date_match.start()] + source[date_match.end():]
    else:
        # An isolated month/day or ISO segment can also specify the due date.
        for segment in re.split(r"[,;]", source):
            if match := _STANDALONE_DATE_RE.fullmatch(segment.strip()):
                deadline, note = _read_date(match.group("date"), today)
                if note:
                    notes.append(note)
                source = source.replace(segment, "", 1)
                break
    if re.search(r"\b(?:due|deadline)\b", source, re.I):
        notes.append("Some deadline text was not recognized. Confirm the date manually.")

    priorities = list(_PRIORITY_RE.finditer(source))
    priority = 2
    if priorities:
        level = (priorities[-1].group("level") or priorities[-1].group("reversed")).lower()
        priority = {"low": 1, "medium": 2, "normal": 2, "high": 3}[level]
        if len({(m.group("level") or m.group("reversed")).lower() for m in priorities}) > 1:
            notes.append("Conflicting priorities found; using the last one. Please verify.")
    source = _PRIORITY_RE.sub(" ", source)

    minutes = 0
    amounts = list(_TIME_RE.finditer(source))
    if amounts:
        for match in amounts:
            amount = float(match.group("amount"))
            multiplier = 60 if match.group("unit").lower().startswith(("h", "hr")) else 1
            minutes += round(amount * multiplier)
        if len(amounts) > 2:
            notes.append("Several durations were added together; verify the total.")
    else:
        notes.append("No duration recognized; estimate set to 1 hour.")
        minutes = 60
    source = _TIME_RE.sub(" ", source)
    minutes = max(1, minutes)
    if minutes > 100_000:
        notes.append("The duration is unusually long; please correct it before saving.")
        minutes = 60

    title = re.sub(r"\s+", " ", source).strip(" ,;:.-")
    title = re.sub(r"\b(?:and|for)\s*$", "", title, flags=re.I).strip(" ,;:.-")
    if not title:
        notes.append("No task title recognized; add a title manually.")
    elif len(title) > 120:
        notes.append("Title shortened to 120 characters; check the wording.")
        title = title[:120].rstrip()
    available = tuple(str(c) for c in categories)
    academic = bool(
        re.search(r"\b(?:exam|assignment|course|lecture|homework|essay)\b", title, re.I)
    )
    category = "University" if academic and "University" in available else "Personal"
    if category not in available and available:
        category = "Personal" if "Personal" in available else available[0]
    return CaptureDraft(title, category, deadline, priority, minutes, tuple(notes))


def validated_draft(capture: CaptureDraft) -> TaskDraft:
    """Use the existing domain validator, not a parser-specific validation rule."""
    return TaskDraft(
        capture.title,
        capture.category,
        capture.deadline,
        capture.priority,
        capture.estimate_minutes,
    )
