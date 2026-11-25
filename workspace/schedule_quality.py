"""Human-readable metrics for comparing saved and suggested schedules."""

from __future__ import annotations

from collections import defaultdict

from workspace.advanced_planner import PlannerSnapshot, RevisionProposal


def shift_distance_minutes(snapshot: PlannerSnapshot, revision: RevisionProposal) -> int:
    """Approximate total displacement for matched original study blocks.

    Original sessions without a matching proposed block are counted as removed
    elsewhere. Matching is deterministic, by step and nearest start time, with
    each proposed block used at most once. This is a diagnostic metric, not an
    exact minimum-cost assignment or an optimality claim.
    """
    originals = defaultdict(list)
    suggested = defaultdict(list)
    for s in snapshot.sessions:
        if s.status == "planned" and revision.monday <= s.day <= revision.sunday:
            originals[s.step_id].append((s.day.toordinal() * 1440 + s.start, s.end - s.start))
    for s in revision.slots:
        suggested[s.step_id].append((s.day.toordinal() * 1440 + s.start, s.minutes))

    displacement = 0
    for step, previous in originals.items():
        remaining = list(suggested.get(step, ()))
        for old_start, old_minutes in sorted(previous):
            if not remaining:
                continue
            index = min(
                range(len(remaining)),
                key=lambda i: (abs(remaining[i][0] - old_start), i),
            )
            new_start, _new_minutes = remaining.pop(index)
            displacement += abs(new_start - old_start)
    return displacement


def describe_goal_tradeoff(selected: dict, routine: dict) -> str:
    """A concise, factual comparison without claiming that reserved time is completed work."""
    changed = selected["moved_or_removed_sessions"] - routine["moved_or_removed_sessions"]
    due = selected["due_coverage_pct"] - routine["due_coverage_pct"]
    priority = selected["high_priority_coverage_pct"] - routine["high_priority_coverage_pct"]
    parts = []
    if abs(priority) >= 0.1:
        parts.append(
            f"{abs(priority):g} points {'more' if priority > 0 else 'less'} priority coverage"
        )
    if abs(due) >= 0.1:
        parts.append(f"{abs(due):g} points {'more' if due > 0 else 'less'} deadline coverage")
    if changed:
        parts.append(f"{abs(changed)} {'more' if changed > 0 else 'fewer'} existing blocks changed")
    if not parts:
        return "These plans have the same headline coverage and disruption metrics."
    return "Compared with keeping your routine: " + "; ".join(parts) + "."
