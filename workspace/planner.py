"""Pure, deterministic, deadline-first greedy planning for the current week."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from workspace.models import Task

UnallocatedReason = Literal[
    "overdue", "insufficient_capacity_before_deadline", "outside_current_plan"
]


@dataclass(frozen=True)
class Allocation:
    task_id: int
    day: date
    minutes: int


@dataclass(frozen=True)
class Unallocated:
    task_id: int
    minutes: int
    reason: UnallocatedReason


@dataclass(frozen=True)
class PlanResult:
    allocations: tuple[Allocation, ...]
    unallocated: tuple[Unallocated, ...]


def week_bounds(today: date) -> tuple[date, date]:
    if type(today) is not date:
        raise ValueError("Today must be a calendar date.")
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)


def generate_plan(
    tasks: list[Task] | tuple[Task, ...], availability: dict[date, int], today: date
) -> PlanResult:
    """Allocate work from today to Sunday without moving deadlines.

    Earliest deadline wins; equal deadlines rank by higher priority then lower ID.
    Allocations are suggestions and do not change remaining task minutes.
    This heuristic does not establish global optimality or future feasibility.
    """
    _, sunday = week_bounds(today)
    for day, value in availability.items():
        if type(day) is not date or type(value) is not int or not 0 <= value <= 1440:
            raise ValueError("Availability requires calendar dates and integer minutes 0–1440.")
    remaining_capacity = {}
    day = today
    while day <= sunday:
        remaining_capacity[day] = availability.get(day, 0)
        day += timedelta(days=1)

    pending = [task for task in tasks if task.status == "pending"]
    if len({task.id for task in pending}) != len(pending):
        raise ValueError("Task IDs must be unique in a planning request.")
    for task in pending:
        if task.remaining_minutes <= 0:
            raise ValueError("Pending tasks must have positive remaining minutes.")

    pending.sort(key=lambda task: (task.deadline or date.max, -task.priority, task.id))
    allocations: list[Allocation] = []
    unallocated: list[Unallocated] = []

    for task in pending:
        remaining = task.remaining_minutes
        if task.deadline is not None and task.deadline < today:
            unallocated.append(Unallocated(task.id, remaining, "overdue"))
            continue
        for day, free in remaining_capacity.items():
            if task.deadline is not None and day > task.deadline:
                break
            amount = min(remaining, free)
            if amount:
                allocations.append(Allocation(task.id, day, amount))
                remaining_capacity[day] -= amount
                remaining -= amount
            if remaining == 0:
                break
        if remaining:
            reason: UnallocatedReason = (
                "insufficient_capacity_before_deadline"
                if task.deadline is not None and task.deadline <= sunday
                else "outside_current_plan"
            )
            unallocated.append(Unallocated(task.id, remaining, reason))

    return PlanResult(tuple(allocations), tuple(unallocated))
