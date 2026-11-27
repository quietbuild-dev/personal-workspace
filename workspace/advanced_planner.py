"""Pure hourly calendar scheduling and reviewable replanning.

No Streamlit or database dependency. The greedy heuristic is deterministic,
not a proof of infeasibility or global optimality.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal


@dataclass(frozen=True)
class StudyStep:
    id: int
    task_id: int
    task_title: str
    title: str
    kind: Literal["checklist", "timed"]
    estimate_minutes: int
    remaining_minutes: int
    checked: bool
    deadline: date | None
    priority: int
    parent_completed: bool
    deadline_minute: int | None = None  # None means end of deadline date


@dataclass(frozen=True)
class TimeWindow:
    id: int
    day: date
    start: int  # minutes since midnight, inclusive
    end: int  # exclusive


@dataclass(frozen=True)
class FixedEvent:
    id: int
    title: str
    day: date
    start: int
    end: int
    kind: str = "Appointment"


@dataclass(frozen=True)
class SavedSession:
    id: int
    step_id: int
    day: date
    start: int
    end: int
    status: Literal["planned", "missed", "done"]
    actual_minutes: int


@dataclass(frozen=True)
class Slot:
    step_id: int
    day: date
    start: int
    end: int

    @property
    def minutes(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class Shortfall:
    step_id: int
    minutes: int
    reason: Literal["overdue", "could_not_fit", "outside_week"]


@dataclass(frozen=True)
class DayBudget:
    """Opt-in minutes for a calendar date; 0 explicitly means a day off."""

    day: date
    minutes: int


# These are search bounds, not recurring daily study commitments.
SEARCH_START = 8 * 60
SEARCH_END = 22 * 60


@dataclass(frozen=True)
class DayPreference:
    day: date
    start: int
    end: int


@dataclass(frozen=True)
class TaskDependency:
    task_id: int
    prerequisite_id: int


@dataclass(frozen=True)
class TaskState:
    id: int
    completed: bool


@dataclass(frozen=True)
class PlannerSnapshot:
    steps: tuple[StudyStep, ...]
    windows: tuple[TimeWindow, ...]
    events: tuple[FixedEvent, ...]
    sessions: tuple[SavedSession, ...]
    fingerprint: str
    budgets: tuple[DayBudget, ...] = ()
    preferences: tuple[DayPreference, ...] = ()
    dependencies: tuple[TaskDependency, ...] = ()
    task_states: tuple[TaskState, ...] = ()


@dataclass(frozen=True)
class RevisionProposal:
    monday: date
    sunday: date
    fingerprint: str
    slots: tuple[Slot, ...]
    shortfalls: tuple[Shortfall, ...]
    unchanged: int
    removed_or_changed: int
    added_or_changed: int
    unchanged_minutes: int

    @property
    def planned_minutes(self) -> int:
        return sum(slot.minutes for slot in self.slots)


def week_bounds(day: date) -> tuple[date, date]:
    if type(day) is not date:
        raise ValueError("A calendar date is required.")
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


def format_time(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _within_windows(day: date, start: int, end: int, windows: tuple[TimeWindow, ...]) -> bool:
    """Allow adjacent/overlapping availability windows as one continuous range."""
    merged = _merge([(w.start, w.end) for w in windows if w.day == day])
    return any(a <= start and end <= b for a, b in merged)


def _merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(end, merged[-1][1])
    return [(a, b) for a, b in merged]


def effective_windows(snapshot: PlannerSnapshot) -> tuple[TimeWindow, ...]:
    """Budget dates use calendar gaps; older, explicit windows remain untouched.

    The actual subtraction of lectures and appointments occurs in _gap_intervals.
    No automatic capacity exists for days without a budget or legacy window.
    """
    budget_days = {item.day for item in snapshot.budgets}
    legacy = [window for window in snapshot.windows if window.day not in budget_days]
    preferred = {item.day: (item.start, item.end) for item in snapshot.preferences}
    derived = [
        TimeWindow(
            -(index + 1),
            budget.day,
            preferred.get(budget.day, (SEARCH_START, SEARCH_END))[0],
            preferred.get(budget.day, (SEARCH_START, SEARCH_END))[1],
        )
        for index, budget in enumerate(snapshot.budgets)
        if budget.minutes > 0
    ]
    return tuple(legacy + derived)


def _daily_limits(snapshot: PlannerSnapshot) -> dict[date, int]:
    return {item.day: item.minutes for item in snapshot.budgets}


def _already_done_minutes(snapshot: PlannerSnapshot) -> dict[date, int]:
    """Completed study time counts toward a day's budget; missed time does not."""
    used: dict[date, int] = {}
    for session in snapshot.sessions:
        if session.status == "done":
            used[session.day] = used.get(session.day, 0) + session.actual_minutes
    return used


def _eligible_saved(
    session: SavedSession,
    step: StudyStep,
    snapshot: PlannerSnapshot,
    now: datetime,
    occupied: dict[date, list[tuple[int, int]]],
) -> bool:
    minute_now = now.hour * 60 + now.minute + (now.second > 0 or now.microsecond > 0)
    if step.remaining_minutes == 0 or step.parent_completed:
        return False
    if session.day < now.date() or (session.day == now.date() and session.start < minute_now):
        return False
    if step.deadline is not None and session.day > step.deadline:
        return False
    if (
        step.deadline is not None
        and session.day == step.deadline
        and step.deadline_minute is not None
        and session.end > step.deadline_minute
    ):
        return False
    if not _within_windows(session.day, session.start, session.end, effective_windows(snapshot)):
        return False
    return not any(
        _overlaps((session.start, session.end), interval)
        for interval in occupied.get(session.day, [])
    )


def accepted_conflicts(snapshot: PlannerSnapshot, now: datetime) -> tuple[str, ...]:
    """Surface accepted sessions invalidated by changed commitments or time windows."""
    steps = {step.id: step for step in snapshot.steps}
    occupied = occupied_history(snapshot)
    issues: list[str] = []
    limits = _daily_limits(snapshot)
    booked = _already_done_minutes(snapshot)
    for session in sorted(snapshot.sessions, key=lambda s: (s.day, s.start, s.id)):
        if session.status != "planned":
            continue
        step = steps.get(session.step_id)
        if step is None:
            issues.append(f"Session #{session.id}: its study step was deleted.")
            continue
        exceeds_budget = (
            session.day in limits
            and booked.get(session.day, 0) + session.end - session.start > limits[session.day]
        )
        if exceeds_budget or not _eligible_saved(session, step, snapshot, now, occupied):
            issues.append(
                f"{step.title} · {session.day:%a %d %b} "
                f"{format_time(session.start)}–{format_time(session.end)} needs review."
            )
        occupied.setdefault(session.day, []).append((session.start, session.end))
        booked[session.day] = booked.get(session.day, 0) + session.end - session.start
    from workspace.dependencies import validate_dependencies

    try:
        validate_dependencies(
            snapshot,
            tuple(
                Slot(s.step_id, s.day, s.start, s.end)
                for s in snapshot.sessions
                if s.status == "planned" and s.step_id in steps
            ),
        )
    except ValueError as error:
        issues.append(str(error))
    return tuple(issues)


def _blocked_by_events(events: tuple[FixedEvent, ...]) -> dict[date, list[tuple[int, int]]]:
    blocked: dict[date, list[tuple[int, int]]] = {}
    for event in events:
        blocked.setdefault(event.day, []).append((event.start, event.end))
    return blocked


def occupied_history(snapshot: PlannerSnapshot) -> dict[date, list[tuple[int, int]]]:
    """Completed sessions remain on the calendar even when a week is replanned."""
    blocked = _blocked_by_events(snapshot.events)
    for session in snapshot.sessions:
        if session.status == "done":
            blocked.setdefault(session.day, []).append((session.start, session.end))
    return blocked


def _gap_intervals(
    day: date,
    windows: tuple[TimeWindow, ...],
    blocked: list[tuple[int, int]],
    minimum_start: int,
) -> list[tuple[int, int]]:
    gaps = []
    for start, end in _merge([(w.start, w.end) for w in windows if w.day == day]):
        cursor = max(start, minimum_start)
        for busy_start, busy_end in _merge(blocked):
            if busy_end <= cursor or busy_start >= end:
                continue
            if busy_start > cursor:
                gaps.append((cursor, min(busy_start, end)))
            cursor = max(cursor, busy_end)
            if cursor >= end:
                break
        if cursor < end:
            gaps.append((cursor, end))
    return [(start, end) for start, end in gaps if end > start]


def make_revision(
    snapshot: PlannerSnapshot,
    now: datetime,
    *,
    preserve_existing: bool = True,
    reschedule_session_id: int | None = None,
) -> RevisionProposal:
    """Preserve eligible accepted sessions, then fill earliest gaps deadline-first.

    Each step's allocated plus shortfall minutes equals its remaining minutes.
    A partial failure to allocate is not evidence that no feasible timetable exists.
    """
    if not isinstance(now, datetime) or now.tzinfo is not None:
        raise ValueError("Use a naive local datetime for the local weekly calendar.")
    today = now.date()
    monday, sunday = week_bounds(today)
    minute_now = now.hour * 60 + now.minute + (now.second > 0 or now.microsecond > 0)
    steps = {s.id: s for s in snapshot.steps if s.kind == "timed" and not s.parent_completed}
    if len(steps) != len(
        [s for s in snapshot.steps if s.kind == "timed" and not s.parent_completed]
    ):
        raise ValueError("Duplicate study step identifiers.")
    for step in steps.values():
        if not 0 <= step.remaining_minutes <= step.estimate_minutes:
            raise ValueError("Step remaining time is outside its estimate.")
    from workspace.dependencies import dependency_context, prerequisite_ready, validate_dependencies

    ranks, prerequisites = dependency_context(snapshot)

    existing = [s for s in snapshot.sessions if s.status == "planned" and monday <= s.day <= sunday]
    occupied = occupied_history(snapshot)
    if reschedule_session_id is not None:
        target = next(
            (session for session in existing if session.id == reschedule_session_id), None
        )
        if target is None:
            raise ValueError("Select a current accepted study session to reschedule.")
        occupied.setdefault(target.day, []).append((target.start, target.end))
    windows = effective_windows(snapshot)
    limits = _daily_limits(snapshot)
    booked = _already_done_minutes(snapshot)
    slots: list[Slot] = []
    allocated: dict[int, int] = {step_id: 0 for step_id in steps}
    preserved: set[tuple[int, date, int, int]] = set()

    if preserve_existing:
        for session in sorted(existing, key=lambda s: (s.day, s.start, s.id)):
            if session.id == reschedule_session_id:
                continue
            step = steps.get(session.step_id)
            if step is None or session.day < today:
                continue
            if any(
                not prerequisite_ready(snapshot, parent) for parent in prerequisites[step.task_id]
            ):
                continue
            if allocated[step.id] + session.end - session.start > step.remaining_minutes:
                continue
            if (
                session.day in limits
                and booked.get(session.day, 0) + session.end - session.start > limits[session.day]
            ):
                continue
            if _eligible_saved(session, step, snapshot, now, occupied):
                slots.append(Slot(step.id, session.day, session.start, session.end))
                allocated[step.id] += session.end - session.start
                occupied.setdefault(session.day, []).append((session.start, session.end))
                booked[session.day] = booked.get(session.day, 0) + session.end - session.start
                preserved.add((step.id, session.day, session.start, session.end))

    shortfalls: list[Shortfall] = []
    sorted_steps = sorted(
        steps.values(),
        key=lambda s: (ranks[s.task_id], s.deadline or date.max, -s.priority, s.task_id, s.id),
    )
    for step in sorted_steps:
        remainder = step.remaining_minutes - allocated[step.id]
        if remainder <= 0:
            continue
        release = (today, 0)
        dependency_blocked = False
        for parent in prerequisites[step.task_id]:
            if prerequisite_ready(snapshot, parent):
                continue
            parent_steps = [s for s in snapshot.steps if s.task_id == parent]
            if (
                not any(s.kind == "timed" for s in parent_steps)
                or any(s.kind == "checklist" and not s.checked for s in parent_steps)
                or any(
                    allocated.get(s.id, 0) < s.remaining_minutes
                    for s in parent_steps
                    if s.kind == "timed"
                )
            ):
                dependency_blocked = True
                break
            parent_ids = {s.id for s in parent_steps}
            release = max(
                release,
                max(((s.day, s.end) for s in slots if s.step_id in parent_ids), default=release),
            )
        if dependency_blocked:
            reason = (
                "could_not_fit" if step.deadline and step.deadline <= sunday else "outside_week"
            )
            if step.deadline and step.deadline < today:
                reason = "overdue"
            shortfalls.append(Shortfall(step.id, remainder, reason))
            continue
        if step.deadline is not None and step.deadline < today:
            shortfalls.append(Shortfall(step.id, remainder, "overdue"))
            continue
        for offset in range((sunday - today).days + 1):
            day = today + timedelta(days=offset)
            if day < release[0]:
                continue
            if step.deadline is not None and day > step.deadline:
                break
            earliest = minute_now if day == today else 0
            if day == release[0]:
                earliest = max(earliest, release[1])
            for start, end in _gap_intervals(day, windows, occupied.get(day, []), earliest):
                if step.deadline == day and step.deadline_minute is not None:
                    end = min(end, step.deadline_minute)
                # New suggestions begin on a predictable five-minute boundary.
                # Saved sessions are never rounded or silently moved.
                start = ((start + 4) // 5) * 5
                if end <= start:
                    continue
                cap_left = limits.get(day, SEARCH_END - SEARCH_START) - booked.get(day, 0)
                amount = min(remainder, end - start, max(0, cap_left))
                # Never introduce a new five-/ten-minute study fragment.
                # Tiny unscheduled remainders remain explicit shortfalls.
                if amount >= 20:
                    slots.append(Slot(step.id, day, start, start + amount))
                    occupied.setdefault(day, []).append((start, start + amount))
                    allocated[step.id] += amount
                    booked[day] = booked.get(day, 0) + amount
                    remainder -= amount
                if remainder == 0:
                    break
            if remainder == 0:
                break
        if remainder:
            reason = (
                "could_not_fit"
                if step.deadline is not None and step.deadline <= sunday
                else "outside_week"
            )
            shortfalls.append(Shortfall(step.id, remainder, reason))
    proposed_keys = {(s.step_id, s.day, s.start, s.end) for s in slots}
    old_keys = {(s.step_id, s.day, s.start, s.end) for s in existing}
    unchanged_keys = old_keys & proposed_keys
    proposal = RevisionProposal(
        monday=monday,
        sunday=sunday,
        fingerprint=snapshot.fingerprint,
        slots=tuple(sorted(slots, key=lambda s: (s.day, s.start, s.step_id))),
        shortfalls=tuple(shortfalls),
        unchanged=len(unchanged_keys),
        removed_or_changed=len(old_keys - proposed_keys),
        added_or_changed=len(proposed_keys - old_keys),
        unchanged_minutes=sum(end - start for _, _, start, end in unchanged_keys),
    )
    validate_dependencies(snapshot, proposal.slots)
    return proposal


def validate_revision(snapshot: PlannerSnapshot, proposal: RevisionProposal, now: datetime) -> None:
    """Independent safety checks, including cases where a proposal was forged/tampered."""
    if not isinstance(now, datetime) or now.tzinfo is not None:
        raise ValueError("Use a naive local datetime for the local weekly calendar.")
    monday, sunday = week_bounds(now.date())
    if proposal.monday != monday or proposal.sunday != sunday:
        raise ValueError("This proposal belongs to a different week. Generate a new one.")
    if proposal.fingerprint != snapshot.fingerprint:
        raise ValueError("Tasks or commitments changed. Generate a fresh proposal.")
    steps = {s.id: s for s in snapshot.steps if s.kind == "timed" and not s.parent_completed}
    allocated: dict[int, int] = {}
    occupied = occupied_history(snapshot)
    windows = effective_windows(snapshot)
    limits = _daily_limits(snapshot)
    booked = _already_done_minutes(snapshot)
    cutoff = now.hour * 60 + now.minute + (now.second > 0 or now.microsecond > 0)
    for slot in proposal.slots:
        if (
            type(slot.step_id) is not int
            or type(slot.day) is not date
            or type(slot.start) is not int
            or type(slot.end) is not int
        ):
            raise ValueError("Session dates and times must use calendar dates and whole minutes.")
        step = steps.get(slot.step_id)
        if step is None:
            raise ValueError("Proposal references a missing or completed study step.")
        if not (now.date() <= slot.day <= sunday) or (step.deadline and slot.day > step.deadline):
            raise ValueError("A proposed session falls outside its valid date range.")
        if (
            step.deadline == slot.day
            and step.deadline_minute is not None
            and slot.end > step.deadline_minute
        ):
            raise ValueError("A proposed session ends after its deadline time.")
        if not (0 <= slot.start < slot.end <= 1440):
            raise ValueError("A proposed session has an invalid time range.")
        if slot.day == now.date() and slot.start < cutoff:
            raise ValueError("The proposed session start has passed. Generate a new proposal.")
        if not _within_windows(slot.day, slot.start, slot.end, windows):
            raise ValueError("A proposed session is outside available time windows.")
        if any(_overlaps((slot.start, slot.end), item) for item in occupied.get(slot.day, [])):
            raise ValueError("Proposed sessions conflict with an event or another session.")
        if slot.day in limits and booked.get(slot.day, 0) + slot.minutes > limits[slot.day]:
            raise ValueError("Proposed sessions exceed the day's study-time budget.")
        booked[slot.day] = booked.get(slot.day, 0) + slot.minutes
        occupied.setdefault(slot.day, []).append((slot.start, slot.end))
        allocated[slot.step_id] = allocated.get(slot.step_id, 0) + slot.minutes
        if allocated[slot.step_id] > step.remaining_minutes:
            raise ValueError("A study step was allocated more time than remains.")
    residuals: dict[int, int] = {}
    for item in proposal.shortfalls:
        if (
            type(item.minutes) is not int
            or item.step_id not in steps
            or item.minutes <= 0
            or item.step_id in residuals
        ):
            raise ValueError("Proposal has invalid remaining-work records.")
        residuals[item.step_id] = item.minutes
    if any(
        allocated.get(i, 0) + residuals.get(i, 0) != step.remaining_minutes
        for i, step in steps.items()
    ):
        raise ValueError("The proposal does not account for all remaining study work.")
    from workspace.dependencies import validate_dependencies

    validate_dependencies(snapshot, proposal.slots)


def hourly_workload(snapshot: PlannerSnapshot, now: datetime) -> dict[date, tuple[int, int]]:
    """Actual free-window minutes and *accepted* booked minutes for each remaining day."""
    today = now.date()
    _, sunday = week_bounds(today)
    events = occupied_history(snapshot)
    windows = effective_windows(snapshot)
    limits = _daily_limits(snapshot)
    completed = _already_done_minutes(snapshot)
    cutoff = now.hour * 60 + now.minute + (now.second > 0 or now.microsecond > 0)
    booked: dict[date, int] = {}
    for session in snapshot.sessions:
        if session.status == "planned" and today <= session.day <= sunday:
            booked[session.day] = booked.get(session.day, 0) + session.end - session.start
    result: dict[date, tuple[int, int]] = {}
    for i in range((sunday - today).days + 1):
        day = today + timedelta(days=i)
        free = sum(
            end - start
            for start, end in _gap_intervals(
                day, windows, events.get(day, []), cutoff if day == today else 0
            )
        )
        if day in limits:
            free = min(free, max(0, limits[day] - completed.get(day, 0)))
        result[day] = free, booked.get(day, 0)
    return result
