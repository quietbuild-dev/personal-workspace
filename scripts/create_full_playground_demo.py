"""Create a rich, isolated Personal Workspace demo database and .ics sample.

Run from project root:
    python -m scripts.create_full_playground_demo --output PATH

This never opens, changes or overwrites the personal workspace database.
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from workspace.advanced_planner import Slot, week_bounds
from workspace.advanced_repository import (
    accept_revision,
    add_fixed_event,
    add_step,
    load_snapshot,
    record_session,
    save_day_preferences,
    set_task_dependencies,
)
from workspace.models import TaskDraft
from workspace.optimizer import proposal_from_slots
from workspace.quick_tasks import create_quick_task, edit_quick_task, linked_step_ids
from workspace.repository import DEFAULT_DB_PATH, list_tasks

DEMO_MARKER = "personal-workspace-safe-playground-v1"


def next_weekday(start: date, weekday: int) -> date:
    return start + timedelta(days=(weekday - start.weekday()) % 7)


def _ics_event(uid: str, title: str, when: date, start: str, end: str) -> str:
    stamp = when.strftime("%Y%m%d")
    return (
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"SUMMARY:{title}\r\n"
        f"DTSTART:{stamp}T{start}00\r\n"
        f"DTEND:{stamp}T{end}00\r\n"
        "END:VEVENT\r\n"
    )


def create_demo(db: Path, now: datetime | None = None) -> dict[str, object]:
    now = now or datetime.now()
    if now.tzinfo is not None:
        raise ValueError("Use local time without a timezone offset.")
    db = db.expanduser().resolve()
    ics_file = db.with_suffix(".ics")
    if db.suffix.lower() != ".db" or db.name.lower() == "workspace.db":
        raise ValueError("Use a distinct demo filename ending in .db (not workspace.db).")
    if db == DEFAULT_DB_PATH.resolve():
        raise ValueError("Refusing to use your personal workspace database.")
    if db.exists() or ics_file.exists():
        raise FileExistsError("Demo DB or matching .ics already exists. Use a new filename.")
    db.parent.mkdir(parents=True, exist_ok=True)
    today = now.date()
    monday, sunday = week_bounds(today)
    prev_monday = monday - timedelta(days=7)
    next_monday = monday + timedelta(days=7)
    events: list[tuple[date, str, int, int, str]] = []
    tasks: list[int] = []
    try:

        def event(day: date, title: str, start: int, end: int, kind: str) -> None:
            add_fixed_event(db, title, day, start, end, kind)
            events.append((day, title, start, end, kind))

        # Realistic study availability for the rest of this week and next month.
        # Days in the past don't get future study availability.
        for offset in range(36):
            day = today + timedelta(days=offset)
            weekend = day.weekday() >= 5
            cap = 120 if weekend else 210
            if day.weekday() == 6:
                cap = 90
            if offset == 0 and now.hour >= 17:
                cap = 0
            save_day_preferences(db, day, cap, 10 * 60, 20 * 60)

        # Visible current-week examples, including a Friday evening that can be freed.
        friday = next_weekday(today, 4)
        saturday = next_weekday(today, 5)
        sunday_event = next_weekday(today, 6)
        if friday > today or now.hour < 10:
            event(friday, "Software Engineering lecture", 10 * 60, 11 * 60 + 30, "Lecture")
        event(friday, "Lunch with classmates", 12 * 60 + 30, 13 * 60 + 30, "Social")
        event(friday, "Dinner and cinema", 19 * 60 + 30, 21 * 60 + 30, "Social")
        event(saturday, "Pilates class", 10 * 60, 11 * 60, "Exercise")
        event(saturday, "Birthday dinner - Sofia", 19 * 60, 21 * 60, "Social")
        event(sunday_event, "Groceries and weekly reset", 16 * 60, 17 * 60, "Personal")
        event(sunday_event, "Call family", 18 * 60, 18 * 60 + 45, "Personal")

        # Weekly-looking lectures and workouts: these are SEPARATE EVENTS, not recurrence rules.
        for week in range(1, 5):
            base = monday + timedelta(days=7 * week)
            event(base, "Algorithms lecture", 10 * 60, 12 * 60, "Lecture")
            event(base + timedelta(days=1), "Statistics lecture", 9 * 60, 11 * 60, "Lecture")
            event(base + timedelta(days=2), "Machine Learning seminar", 13 * 60, 15 * 60, "Lecture")
            event(base + timedelta(days=3), "Software Engineering lab", 9 * 60, 11 * 60, "Lecture")
            event(base + timedelta(days=1), "Gym - strength", 18 * 60, 19 * 60, "Exercise")
            event(base + timedelta(days=3), "Yoga class", 18 * 60, 19 * 60, "Exercise")
            event(base + timedelta(days=4), "Coffee with friends", 17 * 60, 18 * 60, "Social")
            event(base + timedelta(days=5), "Apartment cleaning", 10 * 60, 11 * 60, "Personal")

        # Daily examples over one week, separate scheduled occurrences.
        for offset in range(7):
            day = today + timedelta(days=offset)
            event(day, "Evening reading", 21 * 60 + 40, 22 * 60, "Personal")

        # Different periodic-looking personal commitments.
        event(today + timedelta(days=9), "Dentist appointment", 16 * 60, 17 * 60, "Appointment")
        event(
            today + timedelta(days=13),
            "Birthday - Emma (reminder)",
            8 * 60 + 15,
            8 * 60 + 30,
            "Personal",
        )
        event(today + timedelta(days=13), "Birthday dinner - Emma", 19 * 60, 21 * 60, "Social")
        event(today + timedelta(days=20), "Student society event", 18 * 60, 20 * 60, "Social")
        for month_delta in (1, 2):
            year = today.year + (today.month - 1 + month_delta) // 12
            month = (today.month - 1 + month_delta) % 12 + 1
            day = date(year, month, 1)
            event(day, "Monthly budget review", 8 * 60 + 15, 8 * 60 + 45, "Personal")
        event(
            today + timedelta(days=365),
            "Birthday - Sofia (next year, example)",
            9 * 60,
            9 * 60 + 15,
            "Personal",
        )

        def task(
            title: str,
            category: str,
            days_until: int | None,
            priority: int,
            minutes: int,
            *,
            planned: bool = True,
            due_time: int | None = None,
            checklists: tuple[str, ...] = (),
        ) -> int:
            deadline = today + timedelta(days=days_until) if days_until is not None else None
            task_id = create_quick_task(
                db,
                TaskDraft(title, category, deadline, priority, minutes),
                due_minute=due_time,
                schedule=planned,
            )
            tasks.append(task_id)
            for item in checklists:
                add_step(db, task_id, item, "checklist")
            return task_id

        stats = task(
            "Statistics problem set 4",
            "Statistics",
            3,
            3,
            180,
            due_time=18 * 60,
            checklists=("Solve exercises 1-5", "Check final answers", "Upload PDF"),
        )
        swe_outline = task(
            "SWE final report outline",
            "Software Engineering",
            4,
            3,
            120,
            checklists=("Write constraints section", "Document test results"),
        )
        task("Algorithms exam revision", "Algorithms", 6, 3, 240)
        task("ML model evaluation exercises", "Machine Learning", 8, 2, 150)
        task("Economics reading - chapters 6 and 7", "Economics", 10, 2, 120)
        swe_demo = task("Rehearse SWE project demonstration", "Software Engineering", 12, 2, 90)
        task("Statistics mock exam", "Statistics", 14, 3, 180)
        task("Machine Learning group slides", "Machine Learning", 16, 2, 120)
        task("Algorithms optional problem set", "Algorithms", 20, 1, 120)
        task("Economics case study", "Economics", 21, 2, 150)
        task("Buy birthday gift for Sofia", "Personal", 1, 2, 30, planned=False)
        task("Renew library books", "Personal", 5, 1, 15, planned=False)
        task("Email teaching assistant", "University", 2, 2, 20, planned=False)
        task("Book a winter train ticket", "Personal", 12, 1, 30, planned=False)
        task("Try a new recipe", "Personal", None, 1, 45, planned=False)
        task("Read a novel", "Personal", None, 1, 120, planned=False)
        set_task_dependencies(db, swe_demo, [swe_outline])

        # Real recorded progress, rather than falsely labelling booked hours done.
        # A different study task is partially completed for Deadline Runway.
        economics_id = next(
            t.id for t in list_tasks(db) if t.title == "Economics reading - chapters 6 and 7"
        )
        edit_quick_task(
            db,
            economics_id,
            TaskDraft(
                "Economics reading - chapters 6 and 7",
                "Economics",
                today + timedelta(days=10),
                2,
                120,
            ),
            65,
        )

        # Last week's genuinely recorded history for Weekly Replay.
        last_wed = prev_monday + timedelta(days=2)
        last_thu = prev_monday + timedelta(days=3)
        save_day_preferences(db, last_wed, 120, 9 * 60, 18 * 60)
        save_day_preferences(db, last_thu, 120, 9 * 60, 18 * 60)
        done_task = task("Last week: Database recap", "Computer Science", None, 2, 75)
        missed_task = task("Last week: Missed algorithms practice", "Algorithms", None, 1, 60)
        links = linked_step_ids(db)
        old_now = datetime.combine(prev_monday, datetime.min.time()).replace(hour=8)
        historic = proposal_from_slots(
            load_snapshot(db),
            old_now,
            (
                Slot(links[done_task], last_wed, 10 * 60, 11 * 60),
                Slot(links[missed_task], last_thu, 15 * 60, 16 * 60),
            ),
        )
        accept_revision(db, historic, old_now)
        for session in load_snapshot(db).sessions:
            if session.step_id == links[done_task]:
                record_session(
                    db,
                    session.id,
                    "done",
                    55,
                    now=datetime.combine(last_wed, datetime.min.time()).replace(hour=20),
                )
            if session.step_id == links[missed_task]:
                record_session(
                    db,
                    session.id,
                    "missed",
                    0,
                    now=datetime.combine(last_thu, datetime.min.time()).replace(hour=20),
                )

        # One approved session this week for Energy Today / Make Room for Life.
        days_left = [
            today + timedelta(days=i) for i in range(1, 7) if today + timedelta(days=i) <= sunday
        ]
        planned_day = next((d for d in days_left if d.weekday() == 4), None)
        if planned_day is not None:
            # Friday 17:00-18:30 stays free of fixed events; protect 17:00-19:00 to test replanning.
            future_slots = (Slot(links[stats], planned_day, 17 * 60, 18 * 60 + 30),)
        elif days_left:
            planned_day = days_left[0]
            future_slots = (Slot(links[stats], planned_day, 14 * 60, 15 * 60 + 30),)
        else:
            future_slots = ()
        if future_slots:
            current_plan = proposal_from_slots(load_snapshot(db), now, future_slots)
            accept_revision(db, current_plan, now)

        # Marker is intentionally created LAST. The demo launcher refuses non-demo DBs.
        with sqlite3.connect(db) as connection:
            connection.execute(
                "CREATE TABLE pw_playground_demo (marker TEXT NOT NULL, generated_at TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO pw_playground_demo(marker,generated_at) VALUES(?,?)",
                (DEMO_MARKER, datetime.now().isoformat(timespec="seconds")),
            )

        sample_tue = next_monday + timedelta(days=1)
        sample_sat = next_monday + timedelta(days=5)
        ics_contents = (
            "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
            "PRODID:-//Personal Workspace Safe Demo//EN\r\n"
            + _ics_event("demo-guest-talk-1", "Visiting professor talk", sample_tue, "1600", "1700")
            + _ics_event(
                "demo-museum-visit-1", "Museum visit with friends", sample_sat, "1500", "1630"
            )
            + "END:VCALENDAR\r\n"
        )
        with ics_file.open("x", encoding="utf-8", newline="") as stream:
            stream.write(ics_contents)
    except Exception:
        db.unlink(missing_ok=True)
        ics_file.unlink(missing_ok=True)
        raise

    result = {
        "database": db,
        "ics": ics_file,
        "tasks": len(tasks),
        "events": len(events),
        "history_sessions": 2,
        "study_date": planned_day,
        "this_week": (monday, sunday),
    }
    print(f"DEMO_DB={db}")
    print(f"DEMO_ICS={ics_file}")
    print(f"TASKS={len(tasks)} EVENTS={len(events)}")
    print("WEEKLY_REPLAY=Last week includes completed and missed sessions")
    if planned_day:
        print(f"FOCUS_DAY={planned_day.isoformat()}")
    print("REPEATS=Sample daily, weekly, monthly and yearly occurrences were seeded individually.")
    print("REAL_RECURRENCE=Not implemented yet; planned for the next update.")
    print("SAFETY=No personal database was read or modified.")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    create_demo(arguments.output)


if __name__ == "__main__":
    main()
