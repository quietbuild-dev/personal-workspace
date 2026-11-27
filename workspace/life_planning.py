"""Protect a personal time window and preview deadline-safe study replanning.

No writes occur during a preview. Approval commits the event and revised study
sessions together in one SQLite transaction, including an undo record.
"""

import json
from contextlib import closing
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from itertools import combinations
from pathlib import Path

from workspace.advanced_planner import (
    FixedEvent,
    PlannerSnapshot,
    RevisionProposal,
    Slot,
    _already_done_minutes,
    _daily_limits,
    _gap_intervals,
    accepted_conflicts,
    effective_windows,
    occupied_history,
    validate_revision,
    week_bounds,
)
from workspace.advanced_repository import (
    StaleProposalError,
    _connect,
    _fetch_snapshot,
    initialize_advanced,
    undo_last_plan,
)
from workspace.deadline_guarantees import check_required_coverage
from workspace.scoped_planning import (
    MIN_NEW_BLOCK_MINUTES,
    preserved_proposal,
    saved_future_slots,
)
from workspace.study_dna import StudyDNA

PROTECTED_TITLE = "Personal time (protected)"


@dataclass(frozen=True)
class LifePreview:
    fingerprint: str
    day: date
    start: int
    end: int
    revision: RevisionProposal
    before: tuple[Slot, ...]
    required_ids: frozenset[int]
    feasible: bool
    explanation: str
    solver_message: str
    windows: tuple[tuple[date, int, int], ...] = ()

    @property
    def changed(self) -> int:
        return len(set(self.before) ^ set(self.revision.slots))


def _validate_window(snapshot: PlannerSnapshot, day: date, start: int, end: int, now: datetime):
    if not isinstance(now, datetime) or now.tzinfo is not None:
        raise ValueError("Use a local calendar time.")
    _, sunday = week_bounds(now.date())
    if type(day) is not date or not now.date() <= day <= sunday:
        raise ValueError("Choose a future date in the current planning week.")
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= 1440:
        raise ValueError("Choose a valid start and finish time.")
    if end - start < 30:
        raise ValueError("Protect at least 30 minutes.")
    if day == now.date() and start <= now.hour * 60 + now.minute:
        raise ValueError("The protected time must start in the future.")
    for event in snapshot.events:
        if (event.kind not in ("Social", "Exercise", "Personal") and event.day == day
                and event.start < end and start < event.end):
            raise ValueError(
                f"'{event.title}' is a fixed commitment during this time. "
                "Edit or move that event first; this tool only moves study sessions."
            )
    for session in snapshot.sessions:
        if (
            session.status == "done"
            and session.day == day
            and session.start < end
            and start < session.end
        ):
            raise ValueError("Completed study time already occupies part of this period.")


def _validate_windows(snapshot, windows, now):
    if not isinstance(windows, tuple) or not 1 <= len(windows) <= 14:
        raise ValueError("Choose 1 to 14 protected periods.")
    seen = set()
    for day, start, end in windows:
        _validate_window(snapshot, day, start, end, now)
        if (day, start, end) in seen:
            raise ValueError("Remove duplicate personal-time windows.")
        seen.add((day, start, end))
    ordered = sorted(windows)
    for prev, next_one in zip(ordered, ordered[1:]):
        if prev[0] == next_one[0] and prev[2] > next_one[1]:
            raise ValueError("Protected periods cannot overlap each other.")


def _virtual_snapshot_many(snapshot: PlannerSnapshot, windows):
    return replace(
        snapshot,
        events=snapshot.events + tuple(
            FixedEvent(-index, PROTECTED_TITLE, day, start, end, "Personal")
            for index, (day, start, end) in enumerate(windows, 1)
        ),
    )


def _virtual_snapshot(snapshot: PlannerSnapshot, day: date, start: int, end: int):
    return _virtual_snapshot_many(snapshot, ((day, start, end),))


def _previous_slots(snapshot: PlannerSnapshot, now: datetime):
    _, sunday = week_bounds(now.date())
    cutoff = now.hour * 60 + now.minute + bool(now.second or now.microsecond)
    return tuple(
        Slot(item.step_id, item.day, item.start, item.end)
        for item in snapshot.sessions
        if item.status == "planned"
        and now.date() <= item.day <= sunday
        and (item.day != now.date() or item.start >= cutoff)
    )


def _required_preservation(snapshot, before, proposal, must_ids, now):
    required = check_required_coverage(snapshot, proposal, now, must_ids)
    baseline = preserved_proposal(snapshot, now, before)
    prior = check_required_coverage(snapshot, baseline, now, must_ids)
    if required.outstanding_minutes > prior.outstanding_minutes:
        return (
            False,
            "This would leave more deadline work without study time. "
            "Try another period or add study hours.",
        )
    steps = {step.id: step for step in snapshot.steps}
    old = {}
    new = {}
    for slot in before:
        old[slot.step_id] = old.get(slot.step_id, 0) + slot.minutes
    for slot in proposal.slots:
        new[slot.step_id] = new.get(slot.step_id, 0) + slot.minutes
    for step_id, count in old.items():
        step = steps.get(step_id)
        if (
            step is not None
            and step.deadline is not None
            and step.deadline <= proposal.sunday
            and new.get(step_id, 0) < count
        ):
            return (
                False,
                f"Moving study time would reduce coverage for '{step.task_title}'. "
                "Try a different time window.",
            )
    return True, "Your deadlines are still covered as well as before."


def preview_time_protection(
    snapshot: PlannerSnapshot,
    now: datetime,
    day: date,
    start: int,
    end: int,
    *,
    dna: StudyDNA | None = None,
    required_ids: frozenset[int] = frozenset(),
    gap_minutes: int = 5,
) -> LifePreview:
    """Build a read-only proposal. Never label a shortfall as feasible."""
    if not isinstance(required_ids, frozenset):
        raise ValueError("Required task IDs must be a frozen set.")
    return preview_time_protection_many(
        snapshot, now, ((day, start, end),), dna=dna, required_ids=required_ids,
        gap_minutes=gap_minutes,
    )


def preview_time_protection_many(
    snapshot: PlannerSnapshot,
    now: datetime,
    windows: tuple[tuple[date, int, int], ...],
    *,
    dna: StudyDNA | None = None,
    required_ids: frozenset[int] = frozenset(),
    gap_minutes: int = 5,
) -> LifePreview:
    """One optimization preview for all requested periods, not chained previews."""
    if not isinstance(required_ids, frozenset):
        raise ValueError("Required task IDs must be a frozen set.")
    if gap_minutes not in (0, 5, 10, 15):
        raise ValueError("Choose a valid break preference.")
    _validate_windows(snapshot, windows, now)
    virtual = _virtual_snapshot_many(snapshot, windows)
    before = saved_future_slots(snapshot, now)
    displaced = tuple(
        slot for slot in before
        if any(slot.day == d and slot.start < finish and start < slot.end
               for d, start, finish in windows)
    )
    kept = tuple(slot for slot in before if slot not in displaced)
    original_proposal = preserved_proposal(snapshot, now, before)

    # No other task is introduced, no accepted nonconflicting block is touched,
    # and each moved block keeps its entire original duration.
    placed = list(kept)
    blocked = occupied_history(virtual)
    for slot in kept:
        blocked.setdefault(slot.day, []).append((slot.start, slot.end))
    limits = _daily_limits(snapshot)
    booked = _already_done_minutes(snapshot)
    for slot in kept:
        booked[slot.day] = booked.get(slot.day, 0) + slot.minutes
    study_windows = effective_windows(virtual)
    steps = {step.id: step for step in snapshot.steps}
    failure = None
    _, sunday = week_bounds(now.date())
    cutoff = now.hour * 60 + now.minute + bool(now.second or now.microsecond)
    for old in sorted(displaced, key=lambda x: (x.day, x.start, x.step_id)):
        if old.minutes < MIN_NEW_BLOCK_MINUTES:
            failure = (
                "A conflicting booked session is shorter than 20 minutes. "
                "Edit that session before protecting this time."
            )
            break
        step = steps.get(old.step_id)
        if step is None:
            failure = "A booked study task no longer exists. Review the calendar first."
            break
        candidates = []
        for offset in range((sunday - now.date()).days + 1):
            d = now.date() + timedelta(days=offset)
            if step.deadline is not None and d > step.deadline:
                continue
            earliest = cutoff if d == now.date() else 0
            for lo, hi in _gap_intervals(
                d, study_windows, blocked.get(d, []), earliest
            ):
                if d == step.deadline and step.deadline_minute is not None:
                    hi = min(hi, step.deadline_minute)
                if hi - lo < old.minutes:
                    continue
                if (d in limits and
                        booked.get(d, 0) + old.minutes > limits[d]):
                    continue
                for minute in range(((lo + 4) // 5) * 5, hi - old.minutes + 1, 5):
                    near_study = [
                        other for other in placed if other.day == d
                    ]
                    gap_missing = any(
                        0 <= minute - other.end < gap_minutes
                        or 0 <= other.start - (minute + old.minutes) < gap_minutes
                        for other in near_study
                    )
                    candidates.append((
                        int(gap_missing),
                        abs((d - old.day).days) * 10000 + abs(minute - old.start),
                        d, minute,
                    ))
        replacements = []
        if candidates:
            _, _, new_day, new_start = min(candidates)
            replacements = [Slot(old.step_id, new_day, new_start, new_start + old.minutes)]
        else:
            # Try at most three useful blocks before rejecting the request. The
            # user never gets five-minute remnants or extra unrelated tasks.
            gaps = []
            for offset in range((sunday - now.date()).days + 1):
                d = now.date() + timedelta(days=offset)
                if step.deadline is not None and d > step.deadline:
                    continue
                earliest = cutoff if d == now.date() else 0
                free_budget = limits.get(d, 1440) - booked.get(d, 0)
                for lo, hi in _gap_intervals(d, study_windows, blocked.get(d, []), earliest):
                    if d == step.deadline and step.deadline_minute is not None:
                        hi = min(hi, step.deadline_minute)
                    start_at = ((lo + 4) // 5) * 5
                    capacity = 5 * (min(hi - start_at, free_budget) // 5)
                    if capacity >= MIN_NEW_BLOCK_MINUTES:
                        gaps.append((d, start_at, capacity))
            gaps.sort(key=lambda item: (
                abs((item[0] - old.day).days), abs(item[1] - old.start),
                item[0], item[1],
            ))
            # The bounded combination search favors fewer changed blocks.
            for count in (2, 3):
                if replacements:
                    break
                for chosen in combinations(gaps[:32], count):
                    # All blocks must fit inside independently free gaps.
                    total = old.minutes
                    amounts = []
                    for index, (_, _, capacity) in enumerate(chosen):
                        needed_for_rest = (count - index - 1) * MIN_NEW_BLOCK_MINUTES
                        amount = min(capacity, total - needed_for_rest)
                        if amount < MIN_NEW_BLOCK_MINUTES:
                            break
                        amounts.append(amount)
                        total -= amount
                    if total != 0 or len(amounts) != count:
                        continue
                    per_day = {}
                    for (d, _, _), amount in zip(chosen, amounts):
                        per_day[d] = per_day.get(d, 0) + amount
                    if any(
                        day in limits and booked.get(day, 0) + amount > limits[day]
                        for day, amount in per_day.items()
                    ):
                        continue
                    replacements = [
                        Slot(old.step_id, d, start, start + amount)
                        for (d, start, _), amount in zip(chosen, amounts)
                    ]
                    break
        if not replacements:
            failure = (
                "There is not enough available time to move "
                f"'{step.task_title}' without changing other study sessions. "
                "Try a shorter period or adjust availability."
            )
            break
        for revised in replacements:
            placed.append(revised)
            blocked.setdefault(revised.day, []).append((revised.start, revised.end))
            booked[revised.day] = booked.get(revised.day, 0) + revised.minutes

    if failure is None:
        try:
            revision = preserved_proposal(virtual, now, tuple(placed))
            feasible, explanation = _required_preservation(
                snapshot, before, revision, required_ids, now
            )
        except ValueError as error:
            failure = (
                "Keeping your other study blocks unchanged would create a conflict: "
                f"{error}"
            )
    if failure is not None:
        revision = original_proposal
        feasible, explanation = False, failure
    return LifePreview(
        snapshot.fingerprint, windows[0][0], windows[0][1], windows[0][2],
        revision, before, required_ids, feasible, explanation,
        "Only study blocks inside protected time are considered for moving.",
        windows,
    )


def _life_marker(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS last_life_plan_undo ("
        "singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
        "expected_fingerprint TEXT NOT NULL, "
        "event_id INTEGER NOT NULL)"
    )


def accept_time_protection(db_path: Path, preview: LifePreview, now: datetime) -> int:
    """Atomically save a protected event, study plan, and compatible Undo record."""
    if not isinstance(preview, LifePreview) or not preview.feasible:
        raise ValueError("Only a feasible, reviewed personal-time plan can be saved.")
    initialize_advanced(db_path)
    with closing(_connect(db_path)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            _life_marker(conn)
            latest = _fetch_snapshot(conn)
            if latest.fingerprint != preview.fingerprint:
                raise StaleProposalError("Your calendar changed. Preview personal time again.")
            windows = preview.windows or ((preview.day, preview.start, preview.end),)
            _validate_windows(latest, windows, now)
            if preview.revision.fingerprint != latest.fingerprint:
                raise StaleProposalError("Your preview is no longer current.")
            virtual = _virtual_snapshot_many(latest, windows)
            validate_revision(virtual, preview.revision, now)
            still_feasible, explanation = _required_preservation(
                latest,
                _previous_slots(latest, now),
                preview.revision,
                preview.required_ids,
                now,
            )
            if not still_feasible:
                raise ValueError(explanation)
            proposal = preview.revision
            previous = {
                (session.step_id, session.day, session.start, session.end): session.id
                for session in latest.sessions
                if session.status == "planned"
                and proposal.monday <= session.day <= proposal.sunday
            }
            desired = {(slot.step_id, slot.day, slot.start, slot.end) for slot in proposal.slots}
            before_rows = conn.execute(
                "SELECT id,step_id,day,start_minute,end_minute,status,actual_minutes "
                "FROM scheduled_sessions WHERE status='planned' AND day BETWEEN ? AND ? "
                "ORDER BY id",
                (proposal.monday.isoformat(), proposal.sunday.isoformat()),
            ).fetchall()
            event_ids = []
            for day, start, end in windows:
                event_id = conn.execute(
                    "INSERT INTO fixed_events(title,day,start_minute,end_minute) "
                    "VALUES (?,?,?,?)",
                    (PROTECTED_TITLE, day.isoformat(), start, end),
                ).lastrowid
                conn.execute(
                    "INSERT INTO fixed_event_kinds(event_id,kind) VALUES (?,?)",
                    (event_id, "Personal"),
                )
                event_ids.append(event_id)
            conn.executemany(
                "DELETE FROM scheduled_sessions WHERE id=?",
                [(item_id,) for key, item_id in previous.items() if key not in desired],
            )
            conn.executemany(
                "INSERT INTO scheduled_sessions(step_id,day,start_minute,end_minute) "
                "VALUES (?,?,?,?)",
                [
                    (step_id, day.isoformat(), start, finish)
                    for step_id, day, start, finish in sorted(desired - previous.keys())
                ],
            )
            saved_snapshot = _fetch_snapshot(conn)
            if accepted_conflicts(saved_snapshot, now):
                raise ValueError("The protected schedule conflicts with existing obligations.")
            after_fingerprint = saved_snapshot.fingerprint
            conn.execute(
                "INSERT INTO last_plan_undo "
                "(singleton,expected_fingerprint,monday,sunday,previous_sessions) "
                "VALUES (1,?,?,?,?) ON CONFLICT(singleton) DO UPDATE SET "
                "expected_fingerprint=excluded.expected_fingerprint, "
                "monday=excluded.monday,sunday=excluded.sunday, "
                "previous_sessions=excluded.previous_sessions",
                (
                    after_fingerprint,
                    proposal.monday.isoformat(),
                    proposal.sunday.isoformat(),
                    json.dumps([dict(row) for row in before_rows]),
                ),
            )
            conn.execute(
                "INSERT INTO last_life_plan_undo(singleton,expected_fingerprint,event_id) "
                "VALUES (1,?,?) ON CONFLICT(singleton) DO UPDATE SET "
                "expected_fingerprint=excluded.expected_fingerprint,"
                "event_id=excluded.event_id",
                (after_fingerprint, event_ids[0]),
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS last_life_extra_events ("
                "singleton INTEGER PRIMARY KEY CHECK(singleton=1), event_ids TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT INTO last_life_extra_events(singleton,event_ids) VALUES (1,?) "
                "ON CONFLICT(singleton) DO UPDATE SET event_ids=excluded.event_ids",
                (json.dumps(event_ids[1:]),),
            )
            conn.commit()
            return event_ids[0]
        except Exception:
            conn.rollback()
            raise


def undo_last_plan_with_protection(db_path: Path, now: datetime | None = None) -> int:
    """Undo a protected window and associated study revision together when relevant."""
    if now is None:
        now = datetime.now()
    initialize_advanced(db_path)
    fallback = False
    with closing(_connect(db_path)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            marker_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='last_life_plan_undo'"
            ).fetchone()
            if not marker_exists:
                fallback = True
            else:
                marker = conn.execute(
                    "SELECT expected_fingerprint,event_id FROM last_life_plan_undo "
                    "WHERE singleton=1"
                ).fetchone()
                row = conn.execute(
                    "SELECT * FROM last_plan_undo WHERE singleton=1"
                ).fetchone()
                if row is None or marker is None or marker[0] != row["expected_fingerprint"]:
                    fallback = True
                else:
                    current = _fetch_snapshot(conn)
                    if current.fingerprint != row["expected_fingerprint"]:
                        raise StaleProposalError(
                            "The calendar changed since this plan was saved. "
                            "Review a new plan instead of overwriting later edits."
                        )
                    extra_exists = conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' "
                        "AND name='last_life_extra_events'"
                    ).fetchone()
                    extras = []
                    if extra_exists:
                        extra_row = conn.execute(
                            "SELECT event_ids FROM last_life_extra_events WHERE singleton=1"
                        ).fetchone()
                        extras = json.loads(extra_row[0]) if extra_row else []
                    conn.executemany(
                        "DELETE FROM fixed_events WHERE id=?",
                        [(event_id,) for event_id in (marker[1], *extras)],
                    )
                    saved = json.loads(row["previous_sessions"])
                    conn.execute(
                        "DELETE FROM scheduled_sessions "
                        "WHERE status='planned' AND day BETWEEN ? AND ?",
                        (row["monday"], row["sunday"]),
                    )
                    conn.executemany(
                        "INSERT INTO scheduled_sessions "
                        "(id,step_id,day,start_minute,end_minute,status,actual_minutes) "
                        "VALUES (?,?,?,?,?,?,?)",
                        [
                            (
                                item["id"], item["step_id"], item["day"],
                                item["start_minute"], item["end_minute"],
                                item["status"], item["actual_minutes"],
                            )
                            for item in saved
                        ],
                    )
                    restored = _fetch_snapshot(conn)
                    if accepted_conflicts(restored, now):
                        raise ValueError(
                            "The previous schedule is no longer safe to restore."
                        )
                    conn.execute("DELETE FROM last_plan_undo WHERE singleton=1")
                    conn.execute("DELETE FROM last_life_plan_undo WHERE singleton=1")
                    if extra_exists:
                        conn.execute("DELETE FROM last_life_extra_events WHERE singleton=1")
                    conn.commit()
                    return len(saved)
            conn.rollback()
        except Exception:
            conn.rollback()
            raise
    if fallback:
        return undo_last_plan(db_path, now)
    raise ValueError("Unable to find a reversible plan.")
