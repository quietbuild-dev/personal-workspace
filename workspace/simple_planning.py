"""Read-only proposal summaries shared by the simplified Home and Week pages."""

from dataclasses import dataclass
from datetime import datetime

from workspace.advanced_planner import PlannerSnapshot, RevisionProposal, make_revision


@dataclass(frozen=True)
class ProposalNotice:
    revision: RevisionProposal
    new_sessions: int
    removed_sessions: int
    changed: bool
    shortfall_minutes: int


def proposal_notice(
    snapshot: PlannerSnapshot,
    now: datetime,
    *,
    reschedule_session_id: int | None = None,
) -> ProposalNotice:
    """Make a preview from saved data; never accept or mutate a schedule."""
    revision = make_revision(
        snapshot, now, preserve_existing=True, reschedule_session_id=reschedule_session_id
    )
    accepted = {
        (s.step_id, s.day, s.start, s.end)
        for s in snapshot.sessions
        if s.status == "planned" and revision.monday <= s.day <= revision.sunday
    }
    suggested = {(s.step_id, s.day, s.start, s.end) for s in revision.slots}
    new_count = len(suggested - accepted)
    removed_count = len(accepted - suggested)
    return ProposalNotice(
        revision=revision,
        new_sessions=new_count,
        removed_sessions=removed_count,
        changed=bool(new_count or removed_count),
        shortfall_minutes=sum(s.minutes for s in revision.shortfalls if s.reason != "outside_week"),
    )
