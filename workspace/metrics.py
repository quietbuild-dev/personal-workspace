"""Dashboard calculations with explicit fixed-date inputs; no database or UI."""

from dataclasses import dataclass
from datetime import date, timedelta

from workspace.models import Task
from workspace.planner import Allocation, PlanResult, week_bounds


@dataclass(frozen=True)
class DayWorkload:
    day: date
    available_minutes: int
    planned_minutes: int


@dataclass(frozen=True)
class DashboardMetrics:
    open_tasks: int
    remaining_minutes: int
    due_week_total: int
    due_week_completed: int
    completion_percentage: float | None
    today_allocations: tuple[Allocation, ...]
    overdue_tasks: tuple[Task, ...]
    upcoming_tasks: tuple[Task, ...]
    workload: tuple[DayWorkload, ...]
    overdue_minutes: int
    deadline_shortfall_minutes: int
    outside_plan_minutes: int
    insight: str


def format_minutes(minutes: int) -> str:
    hours, remainder = divmod(minutes, 60)
    return f"{hours}h {remainder:02d}m" if hours else f"{remainder}m"


def calculate_metrics(
    tasks: list[Task] | tuple[Task, ...],
    plan: PlanResult,
    availability: dict[date, int],
    today: date,
) -> DashboardMetrics:
    monday, sunday = week_bounds(today)
    pending = [task for task in tasks if task.status == "pending"]
    due_this_week = [
        task for task in tasks if task.deadline is not None and monday <= task.deadline <= sunday
    ]
    completed = sum(task.status == "completed" for task in due_this_week)
    percentage = 100 * completed / len(due_this_week) if due_this_week else None
    overdue = tuple(sorted(
        (t for t in pending if t.deadline is not None and t.deadline < today),
        key=lambda t: (t.deadline, -t.priority, t.id),
    ))
    upcoming = tuple(sorted(
        (t for t in pending if t.deadline is not None and t.deadline >= today),
        key=lambda t: (t.deadline, -t.priority, t.id),
    ))
    today_allocations = tuple(a for a in plan.allocations if a.day == today)
    scheduled = {}
    for allocation in plan.allocations:
        scheduled[allocation.day] = scheduled.get(allocation.day, 0) + allocation.minutes

    workload = []
    day = today
    while day <= sunday:
        workload.append(DayWorkload(day, availability.get(day, 0), scheduled.get(day, 0)))
        day += timedelta(days=1)

    residuals = {"overdue": 0, "insufficient_capacity_before_deadline": 0,
                 "outside_current_plan": 0}
    for item in plan.unallocated:
        residuals[item.reason] += item.minutes
    overdue_minutes = residuals["overdue"]
    shortfall = residuals["insufficient_capacity_before_deadline"]
    outside = residuals["outside_current_plan"]
    spare = sum(item.available_minutes - item.planned_minutes for item in workload)
    if overdue_minutes:
        insight = (
            f"{format_minutes(overdue_minutes)} of overdue work is not scheduled. "
            "Revise or clear those deadlines to include it in a new plan."
        )
    elif shortfall:
        insight = (
            f"{format_minutes(shortfall)} due this week cannot fit before its deadlines "
            "with the available time entered."
        )
    elif outside:
        insight = (
            f"{format_minutes(outside)} of later-due or undated work is outside this week's "
            "suggested plan; its future feasibility has not been assessed."
        )
    elif spare:
        insight = f"{format_minutes(spare)} of availability remains unassigned through Sunday."
    else:
        insight = "Current tasks fit within the entered capacity for the rest of this week."

    return DashboardMetrics(
        open_tasks=len(pending),
        remaining_minutes=sum(task.remaining_minutes for task in pending),
        due_week_total=len(due_this_week),
        due_week_completed=completed,
        completion_percentage=percentage,
        today_allocations=today_allocations,
        overdue_tasks=overdue,
        upcoming_tasks=upcoming,
        workload=tuple(workload),
        overdue_minutes=overdue_minutes,
        deadline_shortfall_minutes=shortfall,
        outside_plan_minutes=outside,
        insight=insight,
    )
