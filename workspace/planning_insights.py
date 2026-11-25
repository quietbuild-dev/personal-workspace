"""Explain and compare safe, read-only timetable proposals.

Risk assessment and metrics are shared by both engines. The original two-strategy
comparison remains available as a baseline and for the quick lost-time simulation.
"""

from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Literal

from workspace.advanced_planner import (
    FixedEvent,
    PlannerSnapshot,
    RevisionProposal,
    make_revision,
    week_bounds,
)


@dataclass(frozen=True)
class DeadlineRisk:
    task_id: int
    title: str
    deadline: date
    unscheduled_minutes: int
    reason: Literal["overdue", "could_not_fit"]


@dataclass(frozen=True)
class PlanAssessment:
    strategy: Literal["preserve", "rebuild"]
    revision: RevisionProposal
    risks: tuple[DeadlineRisk, ...]
    due_shortfall_minutes: int
    outside_week_minutes: int

    @property
    def moved_or_removed(self) -> int:
        return self.revision.removed_or_changed

    @property
    def scheduled_minutes(self) -> int:
        return self.revision.planned_minutes

    @property
    def changed(self) -> bool:
        return bool(self.revision.added_or_changed or self.revision.removed_or_changed)


@dataclass(frozen=True)
class PlanComparison:
    preserve: PlanAssessment
    rebuild: PlanAssessment


def _assess(snapshot: PlannerSnapshot, revision: RevisionProposal, strategy: str) -> PlanAssessment:
    steps = {step.id: step for step in snapshot.steps}
    problems: dict[int, DeadlineRisk] = {}
    outside = 0
    for shortfall in revision.shortfalls:
        if shortfall.reason == "outside_week":
            outside += shortfall.minutes
            continue
        step = steps.get(shortfall.step_id)
        if step is None or step.deadline is None:
            continue
        previous = problems.get(step.task_id)
        # A parent task may have several timed steps; aggregate into one warning.
        reason = (
            "overdue"
            if shortfall.reason == "overdue"
            or (previous is not None and previous.reason == "overdue")
            else "could_not_fit"
        )
        problems[step.task_id] = DeadlineRisk(
            task_id=step.task_id,
            title=step.task_title,
            deadline=step.deadline,
            unscheduled_minutes=shortfall.minutes
            + (previous.unscheduled_minutes if previous else 0),
            reason=reason,
        )
    risks = tuple(sorted(problems.values(), key=lambda risk: (risk.deadline, risk.title)))
    return PlanAssessment(
        strategy=strategy,
        revision=revision,
        risks=risks,
        due_shortfall_minutes=sum(r.unscheduled_minutes for r in risks),
        outside_week_minutes=outside,
    )


def assess_proposal(snapshot: PlannerSnapshot, revision: RevisionProposal) -> PlanAssessment:
    """Use the same deadline-risk calculation for every scheduling engine."""
    return _assess(snapshot, revision, "rebuild")


def schedule_metrics(snapshot: PlannerSnapshot, revision: RevisionProposal, now: datetime) -> dict:
    """Comparable minute-based metrics, including days with zero planned work."""
    from statistics import pstdev

    from workspace.advanced_planner import _already_done_minutes, hourly_workload

    steps = {s.id: s for s in snapshot.steps if s.kind == "timed" and not s.parent_completed}
    high_need = sum(s.remaining_minutes for s in steps.values() if s.priority == 3)
    due_need = sum(
        s.remaining_minutes
        for s in steps.values()
        if s.deadline is not None and s.deadline <= revision.sunday
    )
    high = sum(s.minutes for s in revision.slots if steps[s.step_id].priority == 3)
    due = sum(
        s.minutes
        for s in revision.slots
        if steps[s.step_id].deadline is not None and steps[s.step_id].deadline <= revision.sunday
    )
    loads = {
        day: value
        for day, value in _already_done_minutes(snapshot).items()
        if now.date() <= day <= revision.sunday
    }
    for day in hourly_workload(snapshot, now):
        loads.setdefault(day, 0)
    for slot in revision.slots:
        loads[slot.day] += slot.minutes
    assessment = assess_proposal(snapshot, revision)
    old = {
        (s.step_id, s.day, s.start, s.end)
        for s in snapshot.sessions
        if s.status == "planned" and revision.monday <= s.day <= revision.sunday
    }
    new = {(s.step_id, s.day, s.start, s.end) for s in revision.slots}
    removed, added = old - new, new - old
    # Pair changed blocks of the same step for an explicit movement-count convention.
    moved = sum(
        min(sum(key[0] == i for key in removed), sum(key[0] == i for key in added))
        for i in {key[0] for key in removed}
    )
    return {
        "scheduled_minutes": revision.planned_minutes,
        "deadline_urgency_score": sum(
            s.minutes * (8 - (steps[s.step_id].deadline - now.date()).days)
            for s in revision.slots
            if steps[s.step_id].deadline is not None
            and now.date() <= steps[s.step_id].deadline <= revision.sunday
        ),
        "priority_weighted_minutes": sum(
            s.minutes * {1: 1, 2: 3, 3: 9}[steps[s.step_id].priority] for s in revision.slots
        ),
        "before_deadline_minutes": sum(
            s.minutes for s in revision.slots if steps[s.step_id].deadline is not None
        ),
        "due_coverage_pct": round(100 * due / due_need, 1) if due_need else 100.0,
        "high_priority_minutes": high,
        "high_priority_coverage_pct": round(100 * high / high_need, 1) if high_need else 100.0,
        "deadline_shortfall_minutes": assessment.due_shortfall_minutes,
        "tasks_at_risk": len(assessment.risks),
        "preserved_sessions": revision.unchanged,
        "moved_or_removed_sessions": revision.removed_or_changed,
        "moved_sessions": moved,
        "removed_sessions": len(removed) - moved,
        "added_or_changed_sessions": revision.added_or_changed,
        "daily_std_minutes": round(pstdev(loads.values()), 2),
        "peak_day_minutes": max(loads.values(), default=0),
        "session_count": len(revision.slots),
        "short_sessions": sum(s.minutes < 25 for s in revision.slots),
    }


def compare_plans(
    snapshot: PlannerSnapshot,
    now: datetime,
    *,
    reschedule_session_id: int | None = None,
) -> PlanComparison:
    """Compute comparable strategies without changing any database or saved session."""
    keep = make_revision(
        snapshot,
        now,
        preserve_existing=True,
        reschedule_session_id=reschedule_session_id,
    )
    rebuild = make_revision(
        snapshot,
        now,
        preserve_existing=False,
        reschedule_session_id=reschedule_session_id,
    )
    return PlanComparison(
        preserve=_assess(snapshot, keep, "preserve"),
        rebuild=_assess(snapshot, rebuild, "rebuild"),
    )


def scenario_unavailable(
    snapshot: PlannerSnapshot,
    now: datetime,
    day: date,
    start: int,
    end: int,
) -> PlannerSnapshot:
    """Create a non-accept-able simulated snapshot with extra blocked calendar time.

    A distinct fingerprint guarantees that even if a scenario proposal is accidentally
    handed to the persistence layer, it cannot be applied to real saved data.
    """
    _, sunday = week_bounds(now.date())
    if type(day) is not date or not now.date() <= day <= sunday:
        raise ValueError("Choose a date between today and the end of this week.")
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= 1440:
        raise ValueError("Choose a valid unavailable period.")
    if day == now.date() and end <= now.hour * 60 + now.minute:
        raise ValueError("Choose future unavailable time, not time that has already passed.")
    blocked = FixedEvent(-1, "What-if: unavailable", day, start, end, "Other")
    return replace(
        snapshot,
        events=(*snapshot.events, blocked),
        fingerprint=f"scenario:{snapshot.fingerprint}:{day.isoformat()}:{start}:{end}",
    )


def explain_comparison(comparison: PlanComparison) -> str:
    """An evidence-based summary; neither greedy strategy is claimed optimal."""
    a, b = comparison.preserve, comparison.rebuild
    if a.scheduled_minutes == b.scheduled_minutes:
        if a.moved_or_removed < b.moved_or_removed:
            return "Both fit the same work; keeping your plan disturbs fewer existing sessions."
        if a.moved_or_removed == b.moved_or_removed:
            return "Both strategies fit the same work with the same number of changes."
        return "Both fit the same work; rebuilding changes fewer existing sessions in this case."
    if a.scheduled_minutes > b.scheduled_minutes:
        return "Keeping your plan fits more work under the current greedy scheduling rules."
    return "Rebuilding fits more work, but may change previously accepted study blocks."
