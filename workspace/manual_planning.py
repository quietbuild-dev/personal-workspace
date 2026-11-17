"""Move one proposed block without mutating the accepted schedule."""

from dataclasses import replace
from datetime import date, datetime

from workspace.advanced_planner import (
    PlannerSnapshot,
    RevisionProposal,
    Slot,
    validate_revision,
)


def move_proposed_block(
    snapshot: PlannerSnapshot,
    proposal: RevisionProposal,
    position: int,
    new_day: date,
    new_start: int,
    now: datetime,
) -> RevisionProposal:
    """Return a validated, user-adjusted proposal; no database writes."""
    if type(position) is not int or not 0 <= position < len(proposal.slots):
        raise ValueError("Choose a proposed study block.")
    if type(new_day) is not date or type(new_start) is not int:
        raise ValueError("Choose a valid calendar date and start time.")
    previous = proposal.slots[position]
    updated = Slot(previous.step_id, new_day, new_start, new_start + previous.minutes)
    slots = list(proposal.slots)
    slots[position] = updated
    slots.sort(key=lambda slot: (slot.day, slot.start, slot.step_id))
    old_keys = {
        (s.step_id, s.day, s.start, s.end)
        for s in snapshot.sessions
        if s.status == "planned" and proposal.monday <= s.day <= proposal.sunday
    }
    next_keys = {(s.step_id, s.day, s.start, s.end) for s in slots}
    unchanged = old_keys & next_keys
    changed = replace(
        proposal,
        slots=tuple(slots),
        unchanged=len(unchanged),
        removed_or_changed=len(old_keys - next_keys),
        added_or_changed=len(next_keys - old_keys),
        unchanged_minutes=sum(end - start for _, _, start, end in unchanged),
    )
    validate_revision(snapshot, changed, now)
    return changed
