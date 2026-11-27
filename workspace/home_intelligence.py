"""Read-only, explainable daily briefing and deadline runway calculations.

Uses *recorded remaining work* for completion. Accepted sessions reserve time but do
not complete work. Free study capacity is a shared pool, never a promise that
all deadlines are individually feasible.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from workspace.advanced_planner import effective_windows, week_bounds


@dataclass(frozen=True)
class Briefing:
    text: str
    agenda: tuple[tuple[int, int, str, str], ...]
    upcoming: tuple[str, ...]


@dataclass(frozen=True)
class RunwayItem:
    task_id: int
    title: str
    deadline: date
    remaining_minutes: int
    estimate_minutes: int
    done_percent: int
    reserved_minutes: int
    needs_slot_minutes: int
    open_capacity_minutes: int
    capacity_configured: bool
    capacity_until: date
    days_left: int
    plannable: bool


def display_duration(minutes: int) -> str:
    hours, mins = divmod(max(0, minutes), 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def _clock(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _due_phrase(day: date, today: date) -> str:
    distance = (day - today).days
    if distance < 0:
        return f"{abs(distance)}d overdue"
    if distance == 0:
        return "due today"
    if distance == 1:
        return "due tomorrow"
    return f"due in {distance} days"


def daily_briefing(tasks, snapshot, now: datetime) -> Briefing:
    """Summarize calendar facts, not inferred emotions or AI predictions."""
    today = now.date()
    steps_by_id = {step.id: step for step in snapshot.steps}
    agenda = [(e.start, e.end, e.title, e.kind) for e in snapshot.events if e.day == today]
    for session in snapshot.sessions:
        if session.day == today and session.status == "planned":
            step = steps_by_id.get(session.step_id)
            if step is not None:
                agenda.append((session.start, session.end, step.task_title, "Study"))
    agenda.sort(key=lambda entry: (entry[0], entry[1], entry[2]))
    lecture_count = sum(1 for item in agenda if item[3] == "Lecture")
    study_minutes = sum(item[1] - item[0] for item in agenda if item[3] == "Study")
    pending = sorted(
        (task for task in tasks if task.status == "pending" and task.deadline is not None),
        key=lambda t: (t.deadline, -t.priority, t.id),
    )
    _, sunday = week_bounds(today)
    approaching = [t for t in pending if today <= t.deadline <= sunday]
    # Say only what is actually booked, without awkward "0 lectures" or "0m" lines.
    today_items = []
    if lecture_count:
        today_items.append(f"{lecture_count} lecture{'s' if lecture_count != 1 else ''}")
    if study_minutes:
        today_items.append(f"{display_duration(study_minutes)} of study planned")
    other_count = sum(kind not in ("Lecture", "Study") for _, _, _, kind in agenda)
    if other_count:
        today_items.append(f"{other_count} other plan{'s' if other_count != 1 else ''}")
    summary = (
        "Today: " + ", ".join(today_items) + "."
        if today_items
        else "Nothing booked on your calendar today."
    )
    if approaching:
        summary += (
            f"\n\n{len(approaching)} deadline{'s' if len(approaching) != 1 else ''} due by Sunday."
        )
    near = approaching
    upcoming = tuple(f"{task.title} ({_due_phrase(task.deadline, today)})" for task in near[:3])
    return Briefing(summary, tuple(agenda), upcoming)


def _merged(intervals):
    combined: list[list[int]] = []
    for start, end in sorted((a, b) for a, b in intervals if b > a):
        if not combined or start > combined[-1][1]:
            combined.append([start, end])
        else:
            combined[-1][1] = max(combined[-1][1], end)
    return [(start, end) for start, end in combined]


def _free_minutes_in_window(windows, blocked, lower, upper):
    """Count free time in a union of windows, excluding a union of busy blocks."""
    result = 0
    busy = _merged(blocked)
    for low, high in _merged(windows):
        start, end = max(low, lower), min(high, upper)
        if end <= start:
            continue
        cursor = start
        for a, b in busy:
            if b <= cursor or a >= end:
                continue
            if a > cursor:
                result += a - cursor
            cursor = max(cursor, b)
            if cursor >= end:
                break
        result += max(0, end - cursor)
    return result


def available_study_minutes(snapshot, now: datetime, deadline: date, deadline_minute=None):
    """Unbooked capacity within calendar windows and per-day study budgets.

    This is a shared capacity estimate, not an optimizer feasibility assertion.
    Count every fixed event and saved future study session as unavailable.
    """
    today = now.date()
    if deadline < today:
        return 0
    windows_by_day = {}
    for window in effective_windows(snapshot):
        windows_by_day.setdefault(window.day, []).append((window.start, window.end))
    blocked = {}
    for event in snapshot.events:
        blocked.setdefault(event.day, []).append((event.start, event.end))
    booked_minutes = {}
    completed_minutes = {}
    for session in snapshot.sessions:
        if session.status in ("planned", "done"):
            blocked.setdefault(session.day, []).append((session.start, session.end))
        if session.status == "planned":
            booked_minutes[session.day] = booked_minutes.get(session.day, 0) + (
                session.end - session.start
            )
        elif session.status == "done":
            completed_minutes[session.day] = completed_minutes.get(session.day, 0) + (
                session.actual_minutes
            )
    budgets = {budget.day: budget.minutes for budget in snapshot.budgets}
    current_minute = now.hour * 60 + now.minute + int(bool(now.second or now.microsecond))
    total = 0
    for offset in range((deadline - today).days + 1):
        day = today + timedelta(days=offset)
        end = deadline_minute if day == deadline and deadline_minute is not None else 1440
        open_minutes = _free_minutes_in_window(
            windows_by_day.get(day, ()),
            blocked.get(day, ()),
            current_minute if day == today else 0,
            end,
        )
        if day in budgets:
            budget_left = max(
                0,
                budgets[day] - booked_minutes.get(day, 0) - completed_minutes.get(day, 0),
            )
            open_minutes = min(open_minutes, budget_left)
        total += open_minutes
    return total


def deadline_runway(tasks, snapshot, now: datetime, *, days_ahead=7, max_items=5):
    """Upcoming tasks and their true remaining work, reserved time and shared capacity."""
    if not 1 <= days_ahead <= 60:
        raise ValueError("days_ahead must be between 1 and 60")
    today = now.date()
    last_day = today + timedelta(days=days_ahead)
    steps_by_task = {}
    for step in snapshot.steps:
        if step.kind == "timed":
            steps_by_task.setdefault(step.task_id, []).append(step)
    selected = sorted(
        (
            task
            for task in tasks
            if task.status == "pending"
            and task.deadline is not None
            and today <= task.deadline <= last_day
        ),
        key=lambda task: (task.deadline, -task.priority, task.id),
    )[:max_items]
    configured = bool(snapshot.windows or any(b.minutes > 0 for b in snapshot.budgets))
    results = []
    for task in selected:
        steps = steps_by_task.get(task.id, ())
        estimate = sum(step.estimate_minutes for step in steps) if steps else task.estimate_minutes
        remaining = (
            sum(step.remaining_minutes for step in steps) if steps else task.remaining_minutes
        )
        estimate = max(1, estimate)
        remaining = min(estimate, max(0, remaining))
        allowed_step_ids = {step.id for step in steps if step.remaining_minutes > 0}
        deadline_minute = next(
            (step.deadline_minute for step in steps if step.deadline_minute is not None), None
        )
        current_minute = now.hour * 60 + now.minute + int(bool(now.second or now.microsecond))
        reserved = sum(
            session.end - session.start
            for session in snapshot.sessions
            if session.status == "planned"
            and session.step_id in allowed_step_ids
            and (session.day > today or (session.day == today and session.start >= current_minute))
            and (
                session.day < task.deadline
                or (
                    session.day == task.deadline
                    and (deadline_minute is None or session.end <= deadline_minute)
                )
            )
        )
        reserved = min(remaining, reserved)
        # No known timed step means the task is tracked as a legacy daily task:
        # we cannot reliably associate accepted hourly sessions with it.
        capacity = available_study_minutes(snapshot, now, task.deadline, deadline_minute)
        results.append(
            RunwayItem(
                task.id,
                task.title,
                task.deadline,
                remaining,
                estimate,
                round(100 * (estimate - remaining) / estimate),
                reserved,
                max(0, remaining - reserved),
                capacity,
                configured,
                task.deadline,
                (task.deadline - today).days,
                bool(steps),
            )
        )
    return tuple(results)
