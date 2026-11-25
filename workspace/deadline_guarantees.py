"""Deadline-completeness checks for explicitly compared study plans.

'Covered' means every remaining timed minute due this week has an allocated slot;
it does not mean the student has already completed that work.
"""

from dataclasses import dataclass
from datetime import datetime

from workspace.advanced_planner import PlannerSnapshot, RevisionProposal


@dataclass(frozen=True)
class Coverage:
    required_minutes: int
    allocated_minutes: int
    outstanding_minutes: int
    tasks_short: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return self.outstanding_minutes == 0


def check_required_coverage(
    snapshot: PlannerSnapshot,
    proposal: RevisionProposal,
    now: datetime,
    must_task_ids: frozenset[int],
) -> Coverage:
    planned = {}
    for slot in proposal.slots:
        planned[slot.step_id] = planned.get(slot.step_id, 0) + slot.minutes
    required = allocated = 0
    missing = set()
    for step in snapshot.steps:
        if (
            step.kind != "timed"
            or step.parent_completed
            or step.task_id not in must_task_ids
            or step.deadline is None
            or step.deadline > proposal.sunday
            or not step.remaining_minutes
        ):
            continue
        required += step.remaining_minutes
        count = min(step.remaining_minutes, planned.get(step.id, 0))
        allocated += count
        if count < step.remaining_minutes:
            missing.add(step.task_title)
    return Coverage(required, allocated, required - allocated, tuple(sorted(missing)))
