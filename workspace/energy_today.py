"""Temporary focus-mode planning: split proposed time into manageable blocks.

The underlying optimizer chooses valid dates/times. This layer never moves or
creates occupied time; it splits only the chosen day's sessions, preserving
all minutes, deadlines, dependency order, and availability constraints.
"""

from dataclasses import replace
from datetime import date, datetime

from workspace.advanced_planner import (
    PlannerSnapshot,
    RevisionProposal,
    Slot,
    make_revision,
    validate_revision,
    week_bounds,
)

MODE_MINUTES = {"Low energy": 25, "Normal": 50, "Deep focus": 90}


def divide_slot(slot: Slot, limit: int) -> tuple[Slot, ...]:
    """Partition without gaps or lost minutes; avoid tiny leftover tails."""
    if type(limit) is not int or limit < 1:
        raise ValueError("Focus length must be a positive whole number of minutes.")
    count = (slot.minutes + limit - 1) // limit
    base, extra = divmod(slot.minutes, count)
    cursor = slot.start
    parts = []
    for idx in range(count):
        stop = cursor + base + (idx < extra)
        parts.append(Slot(slot.step_id, slot.day, cursor, stop))
        cursor = stop
    return tuple(parts)


def energy_proposal(
    snapshot: PlannerSnapshot,
    now: datetime,
    mode: str,
    focus_day: date,
) -> RevisionProposal:
    """Preview-only. An explicit user approval is required to save elsewhere."""
    if mode not in MODE_MINUTES:
        raise ValueError("Choose Low energy, Normal, or Deep focus.")
    if type(focus_day) is not date or not now.date() <= focus_day <= week_bounds(now.date())[1]:
        raise ValueError("Choose today or a remaining date in the current planning week.")
    baseline = make_revision(snapshot, now, preserve_existing=True)
    limit = MODE_MINUTES[mode]
    slots = tuple(
        part
        for slot in baseline.slots
        for part in (divide_slot(slot, limit) if slot.day == focus_day else (slot,))
    )
    existing = {
        (s.step_id, s.day, s.start, s.end)
        for s in snapshot.sessions
        if s.status == "planned" and baseline.monday <= s.day <= baseline.sunday
    }
    new = {(s.step_id, s.day, s.start, s.end) for s in slots}
    unchanged = existing & new
    revision = replace(
        baseline,
        slots=slots,
        unchanged=len(unchanged),
        removed_or_changed=len(existing - new),
        added_or_changed=len(new - existing),
        unchanged_minutes=sum(end - start for _, _, start, end in unchanged),
    )
    validate_revision(snapshot, revision, now)
    return revision


def focus_suggestions(snapshot: PlannerSnapshot, proposal: RevisionProposal, mode: str, day: date):
    """Task-order *suggestions*, not a claim to know actual task difficulty.

    Deadline is the primary key; remaining duration is a transparent effort proxy.
    This display does not reorder the saved calendar or circumvent dependencies.
    """
    if mode not in MODE_MINUTES:
        raise ValueError("Unknown focus mode.")
    steps = {step.id: step for step in snapshot.steps}
    active = {
        slot.step_id: steps[slot.step_id]
        for slot in proposal.slots
        if slot.day == day and slot.step_id in steps
    }
    if mode == "Low energy":
        key = lambda s: (s.deadline or date.max, s.remaining_minutes, -s.priority, s.id)
    elif mode == "Deep focus":
        key = lambda s: (s.deadline or date.max, -s.remaining_minutes, -s.priority, s.id)
    else:
        key = lambda s: (s.deadline or date.max, -s.priority, s.id)
    return tuple(sorted(active.values(), key=key))
