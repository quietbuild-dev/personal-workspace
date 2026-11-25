"""Make a separate demo database and .ics file for all three new features.

Never overwrites any database or calendar file. Does not touch real user data.
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path

from workspace.advanced_planner import Slot, week_bounds
from workspace.advanced_repository import (
    accept_revision,
    add_fixed_event,
    add_step,
    add_window,
    initialize_advanced,
    load_snapshot,
    record_session,
)
from workspace.models import TaskDraft
from workspace.optimizer import proposal_from_slots
from workspace.repository import DEFAULT_DB_PATH, create_task, initialize_database


def create_demo(path: Path, now: datetime | None = None) -> tuple[Path, Path]:
    if now is None:
        now = datetime.now()
    path = path.expanduser().resolve()
    calendar_file = path.with_suffix(".ics")
    if path == DEFAULT_DB_PATH.resolve():
        raise ValueError("The demo must never use your personal database.")
    if path.exists() or calendar_file.exists():
        raise ValueError("Demo files already exist. Choose a fresh filename.")
    tomorrow = now.date() + timedelta(days=1)
    _, sunday = week_bounds(now.date())
    if tomorrow > sunday:
        raise ValueError("Run this demo earlier in the week; Sunday has no tomorrow this week.")
    previous_monday = week_bounds(now.date())[0] - timedelta(days=7)
    previous_tuesday = previous_monday + timedelta(days=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    initialize_database(path)
    initialize_advanced(path)
    old = create_task(path, TaskDraft("Completed reading", "University", None, 2, 60))
    old_step = add_step(path, old.id, "Read assigned chapters", "timed", 60)
    add_window(path, previous_tuesday, 10 * 60, 11 * 60)
    old_now = datetime.combine(previous_monday, datetime.min.time()).replace(hour=8)
    original = load_snapshot(path)
    old_plan = proposal_from_slots(
        original, old_now, (Slot(old_step, previous_tuesday, 600, 660),)
    )
    accept_revision(path, old_plan, old_now)
    recorded = next(s for s in load_snapshot(path).sessions if s.step_id == old_step)
    record_session(
        path, recorded.id, "done", 55,
        now=datetime.combine(previous_tuesday, datetime.min.time()).replace(hour=20),
    )
    task = create_task(path, TaskDraft("Statistics problem set", "University", sunday, 3, 120))
    step = add_step(path, task.id, "Work through exercises", "timed", 120)
    add_window(path, tomorrow, 10 * 60, 16 * 60)
    add_fixed_event(path, "Algorithms lecture", tomorrow, 9 * 60, 10 * 60, "Lecture")
    snap = load_snapshot(path)
    future = proposal_from_slots(snap, now, (Slot(step, tomorrow, 14 * 60, 16 * 60),))
    accept_revision(path, future, now)
    stamp = tomorrow.strftime("%Y%m%d")
    data = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Workspace Demo//EN\r\n"
        "BEGIN:VEVENT\r\nUID:pw-demo-team-meeting\r\nSUMMARY:Team meeting\r\n"
        f"DTSTART:{stamp}T110000\r\nDTEND:{stamp}T120000\r\nEND:VEVENT\r\n"
        "BEGIN:VEVENT\r\nUID:pw-demo-gym\r\nSUMMARY:Evening workout\r\n"
        f"DTSTART:{stamp}T180000\r\nDTEND:{stamp}T190000\r\nEND:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    calendar_file.write_text(data, encoding="utf-8")
    print(f"DEMO_DB={path}")
    print(f"DEMO_ICS={calendar_file}")
    print(f"STRESS_DAY={tomorrow.isoformat()}")
    print("Stress-test tomorrow 14:00-16:00: study should move earlier when possible.")
    print("Weekly replay: Last week has one completed 55-minute reading session.")
    print("The .ics file contains two conflict-free commitments for tomorrow.")
    print("Your personal database was not opened or modified.")
    return path, calendar_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    create_demo(arguments.output)


if __name__ == "__main__":
    main()
