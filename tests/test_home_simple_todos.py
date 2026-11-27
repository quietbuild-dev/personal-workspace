"""Home to-do selection is based on stored task type, not missing deadlines."""

from datetime import date, datetime, timezone
from types import SimpleNamespace

from workspace.home_view_logic import simple_todo_tasks

TODAY = date(2026, 11, 27)


def _task(task_id, title, status="pending", deadline=None, completed_at=None):
    return SimpleNamespace(
        id=task_id,
        title=title,
        status=status,
        deadline=deadline,
        completed_at=completed_at,
        priority=2,
    )


def test_only_simple_to_dos_appear_and_a_due_date_is_allowed():
    groceries = _task(1, "Buy groceries", deadline=date(2026, 11, 29))
    homework = _task(2, "Finish assignment")  # No deadline, but tracked.
    video = _task(3, "Watch lecture video")  # No deadline, time tracked.
    legacy = _task(4, "Pick up a parcel")  # Old unscheduled quick to-do.
    overview = SimpleNamespace(
        tasks=(groceries, homework, video, legacy),
        advanced=SimpleNamespace(steps=()),
    )
    result = simple_todo_tasks(
        overview,
        TODAY,
        {1: "simple", 2: "progress", 3: "progress"},
    )
    assert [task.id for task in result] == [1, 4]


def test_done_todos_can_be_unchecked_today_not_forever():
    same_day = datetime(2026, 11, 27, 10, tzinfo=timezone.utc)
    yesterday = datetime(2026, 11, 26, 10, tzinfo=timezone.utc)
    pending = _task(1, "Laundry")
    done_today = _task(2, "Groceries", "completed", completed_at=same_day)
    older_done = _task(3, "Old errand", "completed", completed_at=yesterday)
    planned = _task(4, "Assignment", "pending")
    overview = SimpleNamespace(
        tasks=(pending, done_today, older_done, planned),
        advanced=SimpleNamespace(steps=()),
    )
    result = simple_todo_tasks(
        overview,
        TODAY,
        {1: "simple", 2: "simple", 3: "simple", 4: "progress"},
    )
    assert [task.id for task in result] == [1, 2]
    assert result[1].status == "completed"


def test_tracked_task_never_inferred_as_todo_even_without_steps():
    task = _task(8, "Prepare for exam")
    overview = SimpleNamespace(tasks=(task,), advanced=None)
    assert simple_todo_tasks(overview, TODAY, {8: "progress"}) == []
