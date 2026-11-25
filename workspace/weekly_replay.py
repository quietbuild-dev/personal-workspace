"""Truthful historical summary from currently retained study-session records.

This is deliberately NOT an immutable reconstruction of older proposals:
accepted replanning can replace still-planned sessions in the current DB.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from workspace.advanced_planner import PlannerSnapshot, week_bounds


@dataclass(frozen=True)
class ReplayDay:
    day: date
    booked_minutes: int
    finished_minutes: int
    missed_minutes: int
    remaining_booked_minutes: int


@dataclass(frozen=True)
class ReplaySubject:
    name: str
    booked_minutes: int
    finished_minutes: int


@dataclass(frozen=True)
class WeeklyReplay:
    monday: date
    sunday: date
    days: tuple[ReplayDay, ...]
    subjects: tuple[ReplaySubject, ...]

    @property
    def booked_minutes(self) -> int:
        return sum(item.booked_minutes for item in self.days)

    @property
    def finished_minutes(self) -> int:
        return sum(item.finished_minutes for item in self.days)

    @property
    def missed_minutes(self) -> int:
        return sum(item.missed_minutes for item in self.days)

    @property
    def pending_minutes(self) -> int:
        return sum(item.remaining_booked_minutes for item in self.days)


def weekly_replay(snapshot: PlannerSnapshot, week_of: date) -> WeeklyReplay:
    if type(week_of) is not date:
        raise ValueError("Choose a valid week.")
    monday, sunday = week_bounds(week_of)
    steps = {step.id: step for step in snapshot.steps}
    sessions = [s for s in snapshot.sessions if monday <= s.day <= sunday]
    days: list[ReplayDay] = []
    for offset in range(7):
        day = monday + timedelta(days=offset)
        rows = [s for s in sessions if s.day == day]
        days.append(
            ReplayDay(
                day=day,
                booked_minutes=sum(s.end - s.start for s in rows),
                finished_minutes=sum(s.actual_minutes for s in rows if s.status == "done"),
                missed_minutes=sum(s.end - s.start for s in rows if s.status == "missed"),
                remaining_booked_minutes=sum(
                    s.end - s.start for s in rows if s.status == "planned"
                ),
            )
        )
    groups: dict[str, list[int]] = {}
    for s in sessions:
        step = steps.get(s.step_id)
        title = step.task_title if step else "Deleted task"
        counters = groups.setdefault(title, [0, 0])
        counters[0] += s.end - s.start
        counters[1] += s.actual_minutes if s.status == "done" else 0
    subjects = tuple(
        ReplaySubject(title, count[0], count[1])
        for title, count in sorted(groups.items(), key=lambda it: (-it[1][0], it[0]))
    )
    return WeeklyReplay(monday, sunday, tuple(days), subjects)
