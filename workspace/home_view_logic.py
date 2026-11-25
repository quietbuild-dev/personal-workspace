"""Read-only Home presentation selection; no Streamlit or persistence access."""

from datetime import date

from workspace.advanced_planner import format_time


def due_display(task, due_times, today: date) -> str:
    if task.deadline is None:
        return "No deadline"
    delta = (task.deadline - today).days
    if delta < 0:
        label = f"Overdue · due {task.deadline:%d/%m/%Y}"
    elif delta == 0:
        label = "Due today"
    elif delta == 1:
        label = "Due tomorrow"
    else:
        label = f"Due {task.deadline:%d/%m/%Y}"
    minute = due_times.get(task.id)
    return label + (f" at {format_time(minute)}" if minute is not None else "")


def focus_tasks(overview, today: date):
    """Show work for today, not simply the earliest four tasks in the database.

    A task belongs here if its deadline is due/overdue or it has an accepted
    study session today. Other tasks remain available on the Tasks page.
    """
    step_to_task = {step.id: step.task_id for step in overview.advanced.steps}
    scheduled_ids = {
        step_to_task[session.step_id]
        for session in overview.advanced.sessions
        if session.day == today and session.status == "planned" and session.step_id in step_to_task
    }
    focus = [
        task
        for task in overview.tasks
        if task.status == "pending"
        and ((task.deadline is not None and task.deadline <= today) or task.id in scheduled_ids)
    ]
    return sorted(
        focus,
        key=lambda task: (
            task.deadline is None,
            task.deadline or date.max,
            -task.priority,
            task.id,
        ),
    )[:4]


def completed_today(overview, today: date):
    """Use persisted completion timestamps; no new table or state is needed."""
    completed = [
        task
        for task in overview.tasks
        if task.status == "completed"
        and task.completed_at is not None
        and task.completed_at.astimezone().date() == today
    ]
    return sorted(completed, key=lambda task: task.completed_at, reverse=True)
