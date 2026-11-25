"""Explainable, read-only schedule diagnostics built on the existing validated planner.

The stress test delegates to the same optimizer and constraint validation as
Make Room for Life. It never saves a proposal or silently changes an event.
"""

from dataclasses import dataclass
from datetime import datetime

from workspace.advanced_planner import PlannerSnapshot, SavedSession, Slot, week_bounds
from workspace.life_planning import LifePreview, preview_time_protection


@dataclass(frozen=True)
class ScheduleHealth:
    conflict_messages: tuple[str, ...]
    unreserved_deadline_minutes: int
    insufficient_breaks: int
    active_deadline_steps: int


def schedule_health(snapshot: PlannerSnapshot, now: datetime) -> ScheduleHealth:
    """Identify potential issues, not probabilistic risk or proven infeasibility."""
    from workspace.advanced_planner import accepted_conflicts

    _, sunday = week_bounds(now.date())
    steps = {step.id: step for step in snapshot.steps}
    minute_now = now.hour * 60 + now.minute + bool(now.second or now.microsecond)
    future = tuple(
        s for s in snapshot.sessions
        if s.status == "planned" and now.date() <= s.day <= sunday
        and (s.day != now.date() or s.start >= minute_now)
    )
    total_missing = 0
    count = 0
    for step in steps.values():
        if step.kind != "timed" or step.parent_completed or step.remaining_minutes <= 0:
            continue
        if step.deadline is None or not now.date() <= step.deadline <= sunday:
            continue
        count += 1
        reserved = sum(
            s.end - s.start for s in future
            if s.step_id == step.id and (s.day < step.deadline or (
                s.day == step.deadline
                and (step.deadline_minute is None or s.end <= step.deadline_minute)
            ))
        )
        total_missing += max(0, step.remaining_minutes - reserved)
    gaps = 0
    by_day: dict = {}
    for s in future:
        by_day.setdefault(s.day, []).append(s)
    for sessions in by_day.values():
        ordered = sorted(sessions, key=lambda s: (s.start, s.end))
        gaps += sum(
            0 <= right.start - left.end < 10
            for left, right in zip(ordered, ordered[1:])
        )
    return ScheduleHealth(
        tuple(accepted_conflicts(snapshot, now)), total_missing, gaps, count
    )


def explanation_factors(
    snapshot: PlannerSnapshot, session: SavedSession, now: datetime
) -> tuple[str, ...]:
    """Describe verified inputs, explicitly not a causal trace of solver decisions."""
    step = next((s for s in snapshot.steps if s.id == session.step_id), None)
    if step is None:
        return ("The study step no longer exists. Review this session.",)
    descriptions = []
    if step.deadline:
        distance = (step.deadline - session.day).days
        if distance < 0:
            descriptions.append("This block is after its recorded deadline; review it.")
        elif distance == 0:
            descriptions.append("This block is on the task's deadline date.")
        else:
            descriptions.append(f"The task deadline is {distance} day(s) after this block.")
    else:
        descriptions.append("There is no deadline recorded for this task.")
    priority_label = {1: "Low", 2: "Medium", 3: "High"}.get(step.priority, "Unknown")
    descriptions.append(f"Priority: {priority_label}.")
    if any(dep.task_id == step.task_id for dep in snapshot.dependencies):
        descriptions.append("This task has prerequisites that the planner must respect.")
    preferences = {item.day: item for item in snapshot.preferences}
    preference = preferences.get(session.day)
    if preference:
        descriptions.append(
            "Within your preferred study hours."
            if preference.start <= session.start and session.end <= preference.end
            else "Outside the preferred study hours; check your saved plan."
        )
    else:
        descriptions.append("No narrower preferred-hours interval is set for this day.")
    overlapping = [
        event for event in snapshot.events
        if event.day == session.day and event.start < session.end and session.start < event.end
    ]
    descriptions.append(
        "Does not overlap any fixed commitment."
        if not overlapping else "Overlaps a fixed commitment and needs review."
    )
    return tuple(descriptions)


def stress_test(
    snapshot: PlannerSnapshot, now: datetime, day, start: int, end: int,
    *, dna=None, required_ids: frozenset[int] = frozenset(),
) -> LifePreview:
    """What-if: lose this availability and calculate a validated, read-only alternative."""
    return preview_time_protection(
        snapshot, now, day, start, end, dna=dna, required_ids=required_ids
    )


def moved_session_summary(preview: LifePreview) -> tuple[tuple[Slot, ...], tuple[Slot, ...]]:
    """Show exactly which blocks disappear and appear in the stress scenario."""
    old = set(preview.before)
    new = set(preview.revision.slots)
    return (
        tuple(sorted(old - new, key=lambda s: (s.day, s.start, s.step_id))),
        tuple(sorted(new - old, key=lambda s: (s.day, s.start, s.step_id))),
    )
