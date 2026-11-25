"""Bounded CP-SAT weekly scheduling; pure proposals, no persistence or UI imports."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from time import perf_counter

from workspace.advanced_planner import (
    PlannerSnapshot,
    RevisionProposal,
    Shortfall,
    Slot,
    _already_done_minutes,
    _blocked_by_events,
    _gap_intervals,
    effective_windows,
    make_revision,
    validate_revision,
    week_bounds,
)

MIN_PREFERRED_SESSION_MINUTES = 25

GOALS = {
    "deadlines": "Meet my deadlines",
    "important": "Focus on important tasks",
    "routine": "Keep my routine",
    "throughput": "Get as much done as possible",
    "balance": "Balance my workload",
}
GOAL_NOTES = {
    "deadlines": "Favor work due this week, with more weight on nearer deadlines.",
    "important": "Favor high-priority work; earlier low-priority deadlines may lose time.",
    "routine": "Keep valid accepted blocks first, then fit more work around them.",
    "throughput": "Fit the most unfinished minutes, then preserve accepted blocks.",
    "balance": "Fit the most minutes, then reduce the busiest day's workload and fragmentation.",
}


@dataclass(frozen=True)
class OptimizationResult:
    revision: RevisionProposal
    goal: str
    engine: str
    status: str
    runtime_seconds: float
    proven_levels: int = 0
    message: str = ""
    solver_seconds: float = 0.0


def proposal_from_slots(snapshot, now, slots):
    """Account for every minute and compare exact accepted block identities."""
    monday, sunday = week_bounds(now.date())
    allocated = {}
    for slot in slots:
        allocated[slot.step_id] = allocated.get(slot.step_id, 0) + slot.minutes
    shortfalls = []
    for step in snapshot.steps:
        if step.kind != "timed" or step.parent_completed:
            continue
        remainder = step.remaining_minutes - allocated.get(step.id, 0)
        if remainder:
            reason = "outside_week"
            if step.deadline is not None and step.deadline <= sunday:
                reason = "overdue" if step.deadline < now.date() else "could_not_fit"
            shortfalls.append(Shortfall(step.id, remainder, reason))
    old = {
        (s.step_id, s.day, s.start, s.end)
        for s in snapshot.sessions
        if s.status == "planned" and monday <= s.day <= sunday
    }
    new = {(s.step_id, s.day, s.start, s.end) for s in slots}
    return RevisionProposal(
        monday,
        sunday,
        snapshot.fingerprint,
        tuple(sorted(slots, key=lambda s: (s.day, s.start, s.step_id))),
        tuple(shortfalls),
        len(old & new),
        len(old - new),
        len(new - old),
        sum(b - a for _, _, a, b in old & new),
    )


def _cp_module():
    from ortools.sat.python import cp_model

    return cp_model


def optimize(
    snapshot: PlannerSnapshot,
    now: datetime,
    *,
    goal="deadlines",
    time_limit=2.0,
    reschedule_session_id=None,
) -> OptimizationResult:
    """Lexicographic objectives; OPTIMAL only when every level is proven.

    Integer minutes avoid rounding accepted sessions or tiny residual work.
    At most one interval per step per free segment; accepted boundaries split
    segments so exact preservation remains representable. A size guard limits
    model growth. Solver time is shared across three objective levels.
    """
    if goal not in GOALS:
        raise ValueError("Choose a supported scheduling goal.")
    if not isinstance(now, datetime) or now.tzinfo is not None:
        raise ValueError("Use a naive local datetime for the local weekly calendar.")
    if not 0 < time_limit <= 30:
        raise ValueError("Solver time limit must be between zero and 30 seconds.")
    tick = perf_counter()
    # Also validates the input and supplies a safe fallback before calling native code.
    baseline = make_revision(
        snapshot,
        now,
        preserve_existing=goal == "routine",
        reschedule_session_id=reschedule_session_id,
    )
    validate_revision(snapshot, baseline, now)

    def fallback(status, message, solver_seconds=0.0):
        return OptimizationResult(
            baseline,
            goal,
            "greedy",
            status,
            perf_counter() - tick,
            message=message,
            solver_seconds=solver_seconds,
        )

    try:
        cp = _cp_module()
    except (ImportError, OSError):
        return fallback("UNAVAILABLE", "Optimizer unavailable; showing the greedy fallback.")
    try:
        return _solve(
            cp, snapshot, now, goal, time_limit, reschedule_session_id, tick, fallback, baseline
        )
    except (RuntimeError, ValueError, OverflowError) as error:
        return fallback(
            "ERROR",
            f"Optimizer could not produce a valid plan ({type(error).__name__}); "
            "showing the greedy fallback.",
        )


def _solve(cp, snapshot, now, goal, time_limit, reschedule_id, tick, fallback, baseline):
    model = cp.CpModel()
    monday, sunday = week_bounds(now.date())
    days = [now.date() + timedelta(days=i) for i in range((sunday - now.date()).days + 1)]
    steps = {
        s.id: s
        for s in snapshot.steps
        if s.kind == "timed" and not s.parent_completed and s.remaining_minutes > 0
    }
    saved = [s for s in snapshot.sessions if s.status == "planned" and s.day in days]
    blocked = _blocked_by_events(snapshot.events)
    for session in snapshot.sessions:
        if session.status == "done" or session.id == reschedule_id:
            blocked.setdefault(session.day, []).append((session.start, session.end))
    windows = effective_windows(snapshot)
    cutoff = now.hour * 60 + now.minute + bool(now.second or now.microsecond)
    limits = {b.day: b.minutes for b in snapshot.budgets}
    completed = _already_done_minutes(snapshot)
    segments = []
    for day in days:
        for a, b in _gap_intervals(
            day, windows, blocked.get(day, []), cutoff if day == now.date() else 0
        ):
            cuts = sorted(
                {a, b} | {p for s in saved if s.day == day for p in (s.start, s.end) if a < p < b}
            )
            segments.extend((day, x, y) for x, y in zip(cuts, cuts[1:]))
    if len(segments) * len(steps) > 12000:
        return fallback(
            "SIZE_LIMIT",
            "This week is too large for the bounded optimizer; showing the greedy fallback.",
        )
    # (step, day, segment start/end, start variable, end variable, duration, presence)
    records = []
    for step in steps.values():
        for day, a, b in segments:
            if step.deadline is not None and day > step.deadline:
                continue
            if step.deadline == day and step.deadline_minute is not None:
                b = min(b, step.deadline_minute)
            if a >= b:
                continue
            key = f"{step.id}_{day}_{a}"
            start = model.new_int_var(a, b, "start_" + key)
            end = model.new_int_var(a, b, "end_" + key)
            amount = model.new_int_var(0, min(b - a, step.remaining_minutes), "dur_" + key)
            present = model.new_bool_var("use_" + key)
            model.add(amount >= 1).only_enforce_if(present)
            model.add(amount == 0).only_enforce_if(present.Not())
            model.add(end == start + amount)
            interval = model.new_optional_interval_var(start, amount, end, present, key)
            records.append((step, day, a, b, start, end, amount, present, interval))
    amounts = {}
    for step in steps.values():
        amounts[step.id] = sum(r[6] for r in records if r[0].id == step.id)
        model.add(amounts[step.id] <= step.remaining_minutes)
    _add_dependencies(model, snapshot, records, amounts, monday)
    loads = []
    for day in days:
        model.add_no_overlap([r[8] for r in records if r[1] == day])
        work = sum(r[6] for r in records if r[1] == day)
        model.add(work <= max(0, limits.get(day, 1440) - completed.get(day, 0)))
        loads.append(work + completed.get(day, 0))
    preserved = []
    for s in saved:
        pieces = [
            r
            for r in records
            if r[0].id == s.step_id and r[1] == s.day and s.start <= r[2] and r[3] <= s.end
        ]
        if sum(r[3] - r[2] for r in pieces) != s.end - s.start:
            continue
        keep = model.new_bool_var(f"keep_{s.id}")
        for r in pieces:
            model.add(r[6] == r[3] - r[2]).only_enforce_if(keep)
        preserved.append((s, keep))
    total = sum(r[6] for r in records)
    due = sum(
        r[6] * (8 - (r[0].deadline - now.date()).days)
        for r in records
        if r[0].deadline is not None and now.date() <= r[0].deadline <= sunday
    )
    importance = sum(r[6] * {1: 1, 2: 3, 3: 9}[r[0].priority] for r in records)
    keep_count = sum(p for _, p in preserved)
    fragments = sum(r[7] for r in records)
    # These are soft preferences, never feasibility constraints. Short study
    # blocks remain possible for genuinely short tasks or small free gaps.
    tiny_blocks = []
    move_distances = []
    prior_by_step = {}
    for previous in saved:
        prior_by_step.setdefault(previous.step_id, []).append(
            (previous.day - monday).days * 1440 + previous.start
        )
    for index, r in enumerate(records):
        if r[0].remaining_minutes >= MIN_PREFERRED_SESSION_MINUTES:
            tiny = model.new_bool_var(f"tiny_{index}")
            model.add(r[6] <= MIN_PREFERRED_SESSION_MINUTES - 1).only_enforce_if([r[7], tiny])
            model.add(r[6] >= MIN_PREFERRED_SESSION_MINUTES).only_enforce_if([r[7], tiny.Not()])
            model.add(tiny == 0).only_enforce_if(r[7].Not())
            tiny_blocks.append(tiny)
        previous_starts = prior_by_step.get(r[0].id, ())
        if previous_starts:
            candidate_start = (r[1] - monday).days * 1440 + r[2]
            nearest = min(previous_starts, key=lambda old: abs(old - candidate_start))
            move = model.new_int_var(0, 10080, f"shift_{index}")
            model.add(move >= (r[1] - monday).days * 1440 + r[4] - nearest).only_enforce_if(r[7])
            model.add(move >= nearest - ((r[1] - monday).days * 1440 + r[4])).only_enforce_if(r[7])
            model.add(move == 0).only_enforce_if(r[7].Not())
            move_distances.append(move)
    # Routine rewards exact preservation first, total scheduled work second,
    # and nearby changes over changes to a different day only on a tie.
    quality = -(sum(move_distances) + 25 * fragments + 35 * sum(tiny_blocks))
    peak = model.new_int_var(0, max([1440, *completed.values()]), "peak")
    model.add_max_equality(peak, loads)
    # Three sequential maximizations avoid arbitrary cross-unit weight scales.
    objectives = {
        "deadlines": (due, total, quality),
        "important": (importance, total, quality),
        "routine": (keep_count, total, quality),
        "throughput": (total, keep_count, quality),
        "balance": (total, -peak, quality),
    }[goal]
    # Seed the search with a feasible plan, split at the same segment boundaries.
    for r in records:
        pieces = [
            (max(s.start, r[2]), min(s.end, r[3]))
            for s in baseline.slots
            if s.step_id == r[0].id and s.day == r[1] and s.start < r[3] and r[2] < s.end
        ]
        start = min((a for a, _ in pieces), default=r[2])
        amount = sum(b - a for a, b in pieces)
        for var, value in (
            (r[4], start),
            (r[5], start + amount),
            (r[6], amount),
            (r[7], int(amount > 0)),
        ):
            model.add_hint(var, value)
    old = {(s.step_id, s.day, s.start, s.end) for s in baseline.slots}
    for s, var in preserved:
        model.add_hint(var, int((s.step_id, s.day, s.start, s.end) in old))
    solver = cp.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 20875
    solve_start = perf_counter()
    best = None
    proven = 0
    last_status = "UNKNOWN"
    search_seconds = 0.0
    for level, objective in enumerate(objectives):
        remaining = time_limit - (perf_counter() - solve_start)
        if remaining <= 0:
            break
        solver.parameters.max_time_in_seconds = remaining / (3 - level)
        model.maximize(objective)
        search_tick = perf_counter()
        status = solver.solve(model)
        search_seconds += perf_counter() - search_tick
        last_status = solver.status_name(status)
        if status not in (cp.OPTIMAL, cp.FEASIBLE):
            break
        raw = [
            Slot(r[0].id, r[1], solver.value(r[4]), solver.value(r[5]))
            for r in records
            if solver.value(r[7])
        ]
        kept = [s for s, p in preserved if solver.value(p)]
        best = _coalesce(raw, kept)
        if status != cp.OPTIMAL:
            break
        proven += 1
        model.add(objective == solver.value(objective))
        model.clear_hints()
        for index in range(len(model.proto.variables)):
            variable = model.get_int_var_from_proto_index(index)
            model.add_hint(variable, solver.value(variable))
    if best is None:
        return fallback(
            last_status,
            "No optimizer solution returned within the search limit; showing the greedy fallback.",
            search_seconds,
        )
    proposal = proposal_from_slots(snapshot, now, best)
    validate_revision(snapshot, proposal, now)
    if _score(snapshot, proposal, now, goal, segments, len(records)) < _score(
        snapshot, baseline, now, goal, segments, len(records)
    ):
        return fallback(
            "BASELINE_BETTER",
            "The search did not improve the baseline for this goal; showing the greedy plan.",
            search_seconds,
        )
    return OptimizationResult(
        proposal,
        goal,
        "cp-sat",
        "OPTIMAL" if proven == 3 else "FEASIBLE",
        perf_counter() - tick,
        proven,
        "Best plan found within the search limit." if proven < 3 else "",
        search_seconds,
    )


def _coalesce(slots, kept):
    boundaries = {(s.step_id, s.day, p) for s in kept for p in (s.start, s.end)}
    merged = []
    for slot in sorted(slots, key=lambda s: (s.day, s.start, s.step_id)):
        if (
            merged
            and merged[-1].step_id == slot.step_id
            and merged[-1].day == slot.day
            and merged[-1].end == slot.start
            and (slot.step_id, slot.day, slot.start) not in boundaries
        ):
            previous = merged.pop()
            slot = Slot(slot.step_id, slot.day, previous.start, slot.end)
        merged.append(slot)
    return tuple(merged)


def _score(snapshot, proposal, now, goal, segments, record_count):
    """Same objective units as the model, including artificial segment boundaries."""
    steps = {s.id: s for s in snapshot.steps}
    due = sum(
        s.minutes * (8 - (steps[s.step_id].deadline - now.date()).days)
        for s in proposal.slots
        if steps[s.step_id].deadline is not None
        and now.date() <= steps[s.step_id].deadline <= proposal.sunday
    )
    importance = sum(
        s.minutes * {1: 1, 2: 3, 3: 9}[steps[s.step_id].priority] for s in proposal.slots
    )
    fragments = sum(
        1
        for s in proposal.slots
        for day, a, b in segments
        if s.day == day and s.start < b and a < s.end
    )
    loads = {
        day: amount
        for day, amount in _already_done_minutes(snapshot).items()
        if now.date() <= day <= proposal.sunday
    }
    for slot in proposal.slots:
        loads[slot.day] = loads.get(slot.day, 0) + slot.minutes
    total, keep = proposal.planned_minutes, proposal.unchanged
    from workspace.schedule_quality import shift_distance_minutes

    short = sum(s.minutes < MIN_PREFERRED_SESSION_MINUTES for s in proposal.slots)
    quality = -(shift_distance_minutes(snapshot, proposal) + 25 * fragments + 35 * short)
    return {
        "deadlines": (due, total, quality),
        "important": (importance, total, quality),
        "routine": (keep, total, quality),
        "throughput": (total, keep, quality),
        "balance": (total, -max(loads.values(), default=0), quality),
    }[goal]


def _add_dependencies(model, snapshot, records, amounts, monday):
    from workspace.dependencies import dependency_context, prerequisite_ready

    _, parents = dependency_context(snapshot)
    if not snapshot.dependencies:
        return
    starts, finishes, active = {}, {}, {}
    for task in parents:
        rows = [r for r in records if r[0].task_id == task]
        enabled = model.new_bool_var(f"active_task_{task}")
        work = sum(r[6] for r in rows)
        model.add(work >= 1).only_enforce_if(enabled)
        model.add(work == 0).only_enforce_if(enabled.Not())
        active[task] = enabled
        firsts, lasts = [10080], [0]
        for index, r in enumerate(rows):
            offset = (r[1] - monday).days * 1440
            first = model.new_int_var(0, 10080, f"first_{task}_{index}")
            last = model.new_int_var(0, 10080, f"last_{task}_{index}")
            model.add(first == offset + r[4]).only_enforce_if(r[7])
            model.add(last == offset + r[5]).only_enforce_if(r[7])
            model.add(first == 10080).only_enforce_if(r[7].Not())
            model.add(last == 0).only_enforce_if(r[7].Not())
            firsts.append(first)
            lasts.append(last)
        starts[task] = model.new_int_var(0, 10080, f"task_start_{task}")
        finishes[task] = model.new_int_var(0, 10080, f"task_end_{task}")
        model.add_min_equality(starts[task], firsts)
        model.add_max_equality(finishes[task], lasts)
    for task, prerequisites in parents.items():
        for parent in prerequisites:
            if prerequisite_ready(snapshot, parent):
                continue
            required = [s for s in snapshot.steps if s.task_id == parent]
            if not any(s.kind == "timed" for s in required) or any(
                s.kind == "checklist" and not s.checked for s in required
            ):
                model.add(active[task] == 0)
                continue
            for step in required:
                if step.kind == "timed":
                    model.add(amounts.get(step.id, 0) == step.remaining_minutes).only_enforce_if(
                        active[task]
                    )
            model.add(starts[task] >= finishes[parent]).only_enforce_if(active[task])
