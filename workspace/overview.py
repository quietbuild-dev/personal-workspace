"""One read path for the planner and dashboard, recalculated on every Streamlit rerun."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

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


def load_overview(db_path: Path, today: date) -> WorkspaceOverview:
    initialize_database(db_path)  # Also performs the safe, additive availability migration.
    tasks = tuple(list_tasks(db_path))
    monday, sunday = week_bounds(today)
    availability = load_availability(db_path, monday, sunday)
    plan = generate_plan(tasks, availability, today)
    metrics = calculate_metrics(tasks, plan, availability, today)
    return WorkspaceOverview(tasks, availability, plan, metrics)
