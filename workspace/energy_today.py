"""Scoped energy adaptation: reshape only already accepted study blocks on one day."""

from datetime import date, datetime

from workspace.advanced_planner import (
    PlannerSnapshot,
    RevisionProposal,
    Slot,
    effective_windows,
    week_bounds,
)
from workspace.scoped_planning import MIN_NEW_BLOCK_MINUTES, preserved_proposal, saved_future_slots

MODE_MINUTES = {"Low energy": 25, "Normal": 50, "High energy": 90, "Deep focus": 90}


def divide_slot(
    slot: Slot, maximum: int, *, minimum: int = MIN_NEW_BLOCK_MINUTES
) -> tuple[Slot, ...]:
    """Divide into nearly equal blocks, never inventing tiny remainders.

    An existing short block remains unchanged rather than creating a new one.
    The segments are contiguous; this feature does not claim breaks were reserved.
    The regular planner still requires 20-minute new sessions. Low Energy
    alone may split *existing* accepted sessions into 10-minute pieces.
    """
    if minimum < 10 or maximum < minimum:
        raise ValueError("Focus length must be at least 10 minutes.")
    length = slot.minutes
    if length <= maximum:
        return (slot,)
    count = (length + maximum - 1) // maximum
    if length // count < minimum:
        # Keep a short accepted session intact instead of rejecting the whole day.
        return (slot,)
    base, extra = divmod(length, count)
    cursor = slot.start
    parts = []
    for index in range(count):
        stop = cursor + base + (index < extra)
        parts.append(Slot(slot.step_id, slot.day, cursor, stop))
        cursor = stop
    return tuple(parts)


def _fit_with_gaps(snapshot, now, original, segments, all_booked, gap_minutes, start_count=0):
    """Shift one saved session within the SAME day, or keep it intact if impossible.

    This never creates time, changes assignments, or moves any other accepted work.
    """
    if len(segments) <= 1:
        return (original,)
    # A longer rest comes after every fourth short focus block, not
    # after four minutes or four tasks. Rest is not counted as study.
    gaps = tuple(
        max(15, gap_minutes) if (start_count + index + 1) % 4 == 0 else gap_minutes
        for index in range(len(segments) - 1)
    )
    if not any(gaps):
        return segments
    total_span = original.minutes + sum(gaps)
    if total_span > 1440:
        return (original,)
    other = [
        (slot.start, slot.end)
        for slot in all_booked
        if slot.day == original.day and slot != original
    ]
    other += [(event.start, event.end) for event in snapshot.events if event.day == original.day]
    other += [
        (session.start, session.end)
        for session in snapshot.sessions
        if session.day == original.day and session.status != "planned"
    ]
    step = next((entry for entry in snapshot.steps if entry.id == original.step_id), None)
    windows = [
        (
            window.start,
            min(window.end, step.deadline_minute)
            if step is not None
            and step.deadline == original.day
            and step.deadline_minute is not None
            else window.end,
        )
        for window in effective_windows(snapshot)
        if window.day == original.day
    ]
    cutoff = now.hour * 60 + now.minute + bool(now.second or now.microsecond)
    candidates = []
    for low, high in windows:
        low = max(low, cutoff) if original.day == now.date() else low
        if high - low < total_span:
            continue
        for start in range(((low + 4) // 5) * 5, high - total_span + 1, 5):
            finish = start + total_span
            if any(a < finish and start < b for a, b in other):
                continue
            candidates.append((abs(start - original.start), start))
    if not candidates:
        return (original,)
    _, cursor = min(candidates)
    result = []
    for index, segment in enumerate(segments):
        result.append(Slot(segment.step_id, original.day, cursor, cursor + segment.minutes))
        cursor += segment.minutes
        if index < len(segments) - 1:
            cursor += gaps[index]
    return tuple(result)


def _low_energy_day(snapshot, now, focus_day, originals, break_minutes):
    """Place all short focus sessions as one valid day sequence when possible.

    A group shares a single free window, preserving task order, total study
    minutes, deadlines, and every fixed or completed appointment. A request
    that cannot fit returns None, never fictitious study or a missed break.
    """
    ordered = sorted(originals, key=lambda slot: (slot.start, slot.end, slot.step_id))
    parts = tuple(part for slot in ordered for part in divide_slot(slot, 25, minimum=10))
    if not parts:
        return ()
    if len(parts) <= 1:
        return tuple(ordered)
    pause = max(5, break_minutes)
    gap_sizes = tuple(
        max(15, pause) if (index + 1) % 4 == 0 else pause for index in range(len(parts) - 1)
    )
    total_span = sum(part.minutes for part in parts) + sum(gap_sizes)
    cutoff = now.hour * 60 + now.minute + bool(now.second or now.microsecond)
    unavailable = [
        (event.start, event.end) for event in snapshot.events if event.day == focus_day
    ] + [
        (session.start, session.end)
        for session in snapshot.sessions
        if session.day == focus_day and session.status != "planned"
    ]
    steps = {entry.id: entry for entry in snapshot.steps}
    windows = sorted(
        (window.start, window.end)
        for window in effective_windows(snapshot)
        if window.day == focus_day
    )
    candidates = []
    for window_start, window_end in windows:
        earliest = max(window_start, cutoff) if focus_day == now.date() else window_start
        for start in range(((earliest + 4) // 5) * 5, window_end - total_span + 1, 5):
            finish = start + total_span
            if any(begin < finish and start < end for begin, end in unavailable):
                continue
            result = []
            cursor = start
            valid = True
            for i, part in enumerate(parts):
                end = cursor + part.minutes
                step = steps.get(part.step_id)
                if (
                    step
                    and step.deadline
                    and (
                        focus_day > step.deadline
                        or (
                            focus_day == step.deadline
                            and step.deadline_minute is not None
                            and end > step.deadline_minute
                        )
                    )
                ):
                    valid = False
                    break
                result.append(Slot(part.step_id, focus_day, cursor, end))
                cursor = end + (gap_sizes[i] if i < len(gap_sizes) else 0)
            if valid:
                candidates.append((abs(start - ordered[0].start), start, tuple(result)))
    return min(candidates)[2] if candidates else None


def energy_proposal(
    snapshot: PlannerSnapshot,
    now: datetime,
    mode: str,
    focus_day: date,
    *,
    break_minutes: int = 5,
) -> RevisionProposal:
    """Reshape only booked work on one day, adding genuine gaps only if feasible."""
    if mode not in MODE_MINUTES:
        raise ValueError("Choose Low energy, Normal, or High energy.")
    if break_minutes not in (0, 5, 10, 15):
        raise ValueError("Choose a valid break preference.")
    if type(focus_day) is not date or not now.date() <= focus_day <= week_bounds(now.date())[1]:
        raise ValueError("Choose today or a remaining date in the current planning week.")
    baseline = saved_future_slots(snapshot, now)
    if not any(slot.day == focus_day for slot in baseline):
        raise ValueError("No booked study sessions on that day. Choose another day.")
    # Normal is intentionally a no-op. A preview should never shuffle saved
    # work merely because the user selected the default energy mode.
    if mode == "Normal":
        return preserved_proposal(snapshot, now, baseline)
    if mode == "Low energy":
        originals = tuple(slot for slot in baseline if slot.day == focus_day)
        grouped = _low_energy_day(snapshot, now, focus_day, originals, break_minutes)
        if grouped is not None:
            other_days = tuple(slot for slot in baseline if slot.day != focus_day)
            return preserved_proposal(snapshot, now, other_days + grouped)
        # A whole day seldom fits into one uninterrupted window when lectures
        # and appointments are present. Try splitting individual saved sessions.
        # Each candidate is validated; failure keeps that original slot intact.
        planned = list(baseline)
        block_count = 0
        for original in sorted(originals, key=lambda s: (s.start, s.end)):
            pieces = divide_slot(original, 25, minimum=10)
            if len(pieces) <= 1:
                block_count += 1
                continue
            candidate = _fit_with_gaps(
                snapshot,
                now,
                original,
                pieces,
                planned,
                max(5, break_minutes),
                start_count=block_count,
            )
            if candidate != (original,):
                trial = tuple(item for item in planned if item != original) + candidate
                try:
                    preserved_proposal(snapshot, now, trial)
                except ValueError:
                    pass
                else:
                    planned.remove(original)
                    planned.extend(candidate)
                    block_count += len(candidate)
                    continue
            block_count += 1
        return preserved_proposal(snapshot, now, tuple(planned))
    if mode in ("High energy", "Deep focus"):
        # Higher energy favors fewer, longer blocks of the SAME task. Joining
        # nearby accepted sessions preserves their total study minutes and
        # never uses time occupied by a lecture or a different study task.
        current = list(baseline)
        active = sorted((s for s in current if s.day == focus_day), key=lambda s: s.start)
        index = 0
        while index + 1 < len(active):
            first, second = active[index], active[index + 1]
            length = first.minutes + second.minutes
            if (
                first.step_id == second.step_id
                and 0 <= second.start - first.end <= 20
                and length <= MODE_MINUTES[mode]
            ):
                combined = Slot(first.step_id, first.day, first.start, first.start + length)
                trial = tuple(s for s in current if s not in (first, second)) + (combined,)
                try:
                    preserved_proposal(snapshot, now, trial)
                except ValueError:
                    pass
                else:
                    current = list(trial)
                    active[index : index + 2] = [combined]
                    continue
            index += 1
        if set(current) != set(baseline):
            return preserved_proposal(snapshot, now, tuple(current))
    planned = list(baseline)
    study_count = 0
    for old in baseline:
        if old.day != focus_day:
            continue
        pieces = divide_slot(old, MODE_MINUTES[mode])
        energy_gap = max(5, break_minutes) if mode == "Low energy" else break_minutes
        adjusted = _fit_with_gaps(
            snapshot,
            now,
            old,
            pieces,
            planned,
            energy_gap,
            start_count=study_count,
        )
        if adjusted != (old,):
            planned.remove(old)
            planned.extend(adjusted)
        study_count += len(adjusted)
    if sum(s.minutes for s in planned) != sum(s.minutes for s in baseline):
        raise ValueError("The adjustment must preserve all booked study minutes.")
    return preserved_proposal(snapshot, now, tuple(planned))


def focus_suggestions(snapshot: PlannerSnapshot, proposal: RevisionProposal, mode: str, day: date):
    """Deadline-first suggestions, not an inferred measure of task difficulty."""
    if mode not in MODE_MINUTES:
        raise ValueError("Unknown focus mode.")
    steps = {step.id: step for step in snapshot.steps}
    active = {
        slot.step_id: steps[slot.step_id]
        for slot in proposal.slots
        if slot.day == day and slot.step_id in steps
    }
    if mode == "Low energy":

        def key(s):
            return (s.deadline or date.max, s.remaining_minutes, -s.priority, s.id)
    elif mode in ("Deep focus", "High energy"):

        def key(s):
            return (s.deadline or date.max, -s.remaining_minutes, -s.priority, s.id)
    else:

        def key(s):
            return (s.deadline or date.max, -s.priority, s.id)

    return tuple(sorted(active.values(), key=key))
