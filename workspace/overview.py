"""One read path for the planner and dashboard, recalculated on every Streamlit rerun."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from workspace.advanced_planner import PlannerSnapshot
from workspace.advanced_repository import load_snapshot
from workspace.metrics import DashboardMetrics, calculate_metrics
from workspace.models import Task
from workspace.planner import PlanResult, generate_plan, week_bounds
from workspace.repository import initialize_database, list_tasks, load_availability


@dataclass(frozen=True)
class WorkspaceOverview:
    tasks: tuple[Task, ...]
    availability: dict[date, int]
    plan: PlanResult
    metrics: DashboardMetrics
    advanced: PlannerSnapshot


def load_overview(db_path: Path, today: date) -> WorkspaceOverview:
    initialize_database(db_path)  # Also performs the safe, additive availability migration.
    tasks = tuple(list_tasks(db_path))
    monday, sunday = week_bounds(today)
    availability = load_availability(db_path, monday, sunday)
    advanced = load_snapshot(db_path)
    step_based_minutes: dict[int, int] = {}
    for step in advanced.steps:
        if step.kind == "timed":
            step_based_minutes[step.task_id] = (
                step_based_minutes.get(step.task_id, 0) + step.remaining_minutes
            )
    # A parent with timed children is not also allocated as a legacy daily task.
    legacy_tasks = [task for task in tasks if task.id not in step_based_minutes]
    plan = generate_plan(legacy_tasks, availability, today)
    metrics = calculate_metrics(
        tasks, plan, availability, today, structured_remaining=step_based_minutes
    )
    return WorkspaceOverview(tasks, availability, plan, metrics, advanced)
