"""Export is read-only and contains only accepted calendar bookings."""

from datetime import date

from workspace.advanced_planner import FixedEvent, PlannerSnapshot, SavedSession, StudyStep
from workspace.calendar_export import build_calendar_ics

DAY = date(2026, 11, 25)


def test_export_accepted_sessions_and_events_but_not_unaccepted_or_done():
    snapshot = PlannerSnapshot(
        steps=(StudyStep(1, 2, "SWE Report", "Research", "timed", 90, 90, False, DAY, 3, False),),
        windows=(),
        events=(FixedEvent(7, "Lecture, A; B", DAY, 540, 600),),
        sessions=(
            SavedSession(1, 1, DAY, 700, 760, "planned", 0),
            SavedSession(2, 1, DAY, 800, 860, "done", 60),
        ),
        fingerprint="demo",
    )
    raw = build_calendar_ics(snapshot)
    assert b"BEGIN:VCALENDAR\r\n" in raw
    assert raw.count(b"BEGIN:VEVENT") == 2
    assert b"DTSTART:20261125T114000" in raw
    assert b"Study: SWE Report - Research" in raw
    assert b"Lecture\\, A\\; B" in raw
    assert b"UID:study-2" not in raw
    assert raw.endswith(b"END:VCALENDAR\r\n")
    assert not build_calendar_ics(snapshot, start_day=date(2026, 11, 26)).count(b"BEGIN:VEVENT")


def test_export_folds_non_ascii_long_lines():
    snap = PlannerSnapshot((), (), (FixedEvent(1, "Cafe " + "e" * 200 + "é", DAY, 1, 2),), (), "x")
    data = build_calendar_ics(snap)
    assert all(len(line) <= 75 for line in data.split(b"\r\n"))
