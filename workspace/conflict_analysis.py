"""Calculated capacity bounds, not an unsatisfiable-core or a feasibility promise."""

from dataclasses import dataclass
from datetime import timedelta

from workspace.advanced_planner import (
    SEARCH_END,
    SEARCH_START,
    TimeWindow,
    _already_done_minutes,
    _gap_intervals,
    effective_windows,
    occupied_history,
)
from workspace.dependencies import dependency_context, prerequisite_ready


@dataclass(frozen=True)
class WorkConflict:
    task_id: int
    title: str
    needed_minutes: int
    shortfall_minutes: int
    capacity_upper_bound: int
    commitments_removed_minutes: int
    budget_removed_minutes: int
    explanation: str
    suggestions: tuple[str, ...]


def analyze_conflicts(snapshot, proposal, now):
    """Per-task bounds ignore competing work and precedence; state that explicitly."""
    _, parents = dependency_context(snapshot)
    windows = effective_windows(snapshot)
    blocked = occupied_history(snapshot)
    done = _already_done_minutes(snapshot)
    budgets = {b.day: b.minutes for b in snapshot.budgets}
    steps = {s.id: s for s in snapshot.steps}
    by_task = {}
    for shortfall in proposal.shortfalls:
        task = steps[shortfall.step_id].task_id
        by_task[task] = by_task.get(task, 0) + shortfall.minutes
    output = []
    cutoff = now.hour * 60 + now.minute + bool(now.second or now.microsecond)
    for task, shortfall in by_task.items():
        required = [
            s
            for s in snapshot.steps
            if s.task_id == task and s.kind == "timed" and not s.parent_completed
        ]
        representative = required[0]
        due = representative.deadline
        last = min(due or proposal.sunday, proposal.sunday)
        capacity = commitment_loss = budget_loss = 0
        suggestions = []
        for offset in range(max(0, (last - now.date()).days + 1)):
            day = now.date() + timedelta(days=offset)
            earliest = cutoff if day == now.date() else 0
            end = representative.deadline_minute if due == day else None
            end = 1440 if end is None else end
            available = tuple(
                TimeWindow(w.id, day, w.start, min(w.end, end))
                for w in windows
                if w.day == day and w.start < end
            )
            nominal = sum(b - a for a, b in _gap_intervals(day, available, [], earliest))
            free = sum(
                b - a for a, b in _gap_intervals(day, available, blocked.get(day, []), earliest)
            )
            cap = max(0, budgets.get(day, 1440) - done.get(day, 0))
            capacity += min(free, cap)
            commitment_loss += nominal - free
            budget_loss += max(0, free - cap)
            if free > cap and day in budgets and budgets[day] < 840:
                gain = min(free - cap, 840 - budgets[day])
                suggestions.append(
                    f"On {day:%a %d %b}, the daily limit excludes {gain} min "
                    "of free study-window time. Raising that limit may help."
                )
            # Potential outside-window capacity, clipped to deadline, search bounds and budget.
            broad = (TimeWindow(-1, day, SEARCH_START, min(SEARCH_END, end)),)
            excluded = blocked.get(day, []) + [(w.start, w.end) for w in available]
            extra = sum(b - a for a, b in _gap_intervals(day, broad, excluded, earliest))
            gain = min(extra, max(0, cap - free))
            if gain > 0 and available:
                suggestions.append(
                    f"On {day:%a %d %b}, up to {gain} additional min are free "
                    "outside your study window within 08:00–22:00. "
                    "Extending availability may help."
                )
        needed = sum(s.remaining_minutes for s in required)
        boundary = f"before {due:%a %d %b}" if due and due <= proposal.sunday else "this week"
        if representative.deadline_minute is not None and due and due <= proposal.sunday:
            minute = representative.deadline_minute
            boundary += f" at {minute // 60:02d}:{minute % 60:02d}"
        text = (
            f"{representative.task_title} needs {needed} min {boundary}; "
            f"{shortfall} min remain unplanned. At most {capacity} min of calendar capacity "
            "are available, before considering other tasks or dependencies."
        )
        if commitment_loss or budget_loss:
            text += (
                f" Recorded commitments remove {commitment_loss} min inside availability; "
                f"daily limits exclude a further {budget_loss} min."
            )
        for parent in sorted(parents[task]):
            if prerequisite_ready(snapshot, parent):
                continue
            prerequisite_steps = [s for s in snapshot.steps if s.task_id == parent]
            title = prerequisite_steps[0].task_title if prerequisite_steps else f"task #{parent}"
            if any(s.kind == "checklist" and not s.checked for s in prerequisite_steps):
                text += f" {title} has unchecked checklist items, which block this task's plan."
            elif not any(s.kind == "timed" for s in prerequisite_steps):
                text += f" {title} needs completion or timed estimates before this can be planned."
            else:
                text += f" All remaining timed work for {title} must fit before this task starts."
        if needed > capacity:
            text += f" Calendar capacity alone is short by at least {needed - capacity} min."
        elif not parents[task]:
            suggestions.append(
                "Compare another goal to see whether more of this task fits; "
                "other assignments may receive less time."
            )
        if due and due < now.date():
            suggestions = ["The deadline has passed. Review the deadline and remaining estimate."]
        output.append(
            WorkConflict(
                task,
                representative.task_title,
                needed,
                shortfall,
                capacity,
                commitment_loss,
                budget_loss,
                text,
                tuple(suggestions[:2]),
            )
        )
    return tuple(output)
