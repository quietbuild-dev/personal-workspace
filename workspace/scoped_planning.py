"""Small, reviewable changes to accepted study sessions only.

These utilities never schedule previously unbooked work. They account for the
remaining unscheduled work explicitly and leave database writes to the existing
transactional acceptance/Undo code.
"""

from datetime import datetime

from workspace.advanced_planner import (
    RevisionProposal,
    Shortfall,
    Slot,
    validate_revision,
    week_bounds,
)
from workspace.stale_bookings import outdated_planned_sessions

MIN_NEW_BLOCK_MINUTES = 20


def saved_future_slots(snapshot, now: datetime) -> tuple[Slot, ...]:
    """Require an accepted plan that can be preserved without dropping past rows."""
    outdated = outdated_planned_sessions(snapshot, now)
    if outdated:
        raise ValueError(
            f"{len(outdated)} outdated study booking(s) belong to completed or removed "
            "tasks. Use 'Remove outdated bookings' in Calendar before replanning. "
            "Nothing has been changed."
        )
    monday, sunday = week_bounds(now.date())
    cutoff = now.hour * 60 + now.minute + bool(now.second or now.microsecond)
    result = []
    for session in snapshot.sessions:
        if session.status != "planned" or not monday <= session.day <= sunday:
            continue
        if session.day < now.date() or (session.day == now.date() and session.start < cutoff):
            raise ValueError(
                "A saved study session is already in the past. Record its progress "
                "in Calendar before adjusting the remaining plan."
            )
        result.append(Slot(session.step_id, session.day, session.start, session.end))
    return tuple(sorted(result, key=lambda s: (s.day, s.start, s.step_id)))


def preserved_proposal(snapshot, now: datetime, slots: tuple[Slot, ...]) -> RevisionProposal:
    """Build a validated revision with exactly the requested accepted work."""
    monday, sunday = week_bounds(now.date())
    steps = {s.id: s for s in snapshot.steps if s.kind == "timed" and not s.parent_completed}
    allocated = {}
    for slot in slots:
        allocated[slot.step_id] = allocated.get(slot.step_id, 0) + slot.minutes
    shortfalls = []
    for step in steps.values():
        remaining = step.remaining_minutes - allocated.get(step.id, 0)
        if remaining < 0:
            raise ValueError("Existing study blocks exceed recorded remaining work.")
        if remaining:
            if step.deadline and step.deadline < now.date():
                reason = "overdue"
            elif step.deadline and step.deadline <= sunday:
                reason = "could_not_fit"
            else:
                reason = "outside_week"
            shortfalls.append(Shortfall(step.id, remaining, reason))
    current = set(saved_future_slots(snapshot, now))
    proposed = set(slots)
    unchanged = current & proposed
    result = RevisionProposal(
        monday,
        sunday,
        snapshot.fingerprint,
        tuple(sorted(slots, key=lambda s: (s.day, s.start, s.step_id))),
        tuple(shortfalls),
        len(unchanged),
        len(current - proposed),
        len(proposed - current),
        sum(s.minutes for s in unchanged),
    )
    validate_revision(snapshot, result, now)
    return result
