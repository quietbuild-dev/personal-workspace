"""Synthetic reproducible comparison. Never opens a personal database.

python -m scripts.evaluate_optimizer --repeats 3 --csv docs/optimizer-benchmark.csv
"""

import argparse
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter

from workspace.advanced_planner import (
    DayBudget,
    DayPreference,
    FixedEvent,
    PlannerSnapshot,
    SavedSession,
    StudyStep,
    TaskDependency,
    TimeWindow,
    effective_windows,
    make_revision,
    validate_revision,
)
from workspace.optimizer import GOALS, optimize
from workspace.planning_insights import schedule_metrics

NOW = datetime(2026, 11, 16, 8)
DAY = NOW.date()


def work(i, minutes, priority=2, due_day=4, due_minute=None):
    return StudyStep(
        i,
        i,
        f"Assignment {i}",
        "Study",
        "timed",
        minutes,
        minutes,
        False,
        DAY + timedelta(days=due_day),
        priority,
        False,
        due_minute,
    )


def example(steps, windows=None, **kwargs):
    return PlannerSnapshot(
        tuple(steps),
        tuple(windows if windows is not None else [TimeWindow(1, DAY, 540, 660)]),
        kwargs.pop("events", ()),
        kwargs.pop("sessions", ()),
        "synthetic-benchmark",
        **kwargs,
    )


def scenarios():
    windows = [TimeWindow(i, DAY + timedelta(days=i), 540, 720) for i in range(5)]
    yield "light", 0, example([work(i, 60) for i in range(1, 4)], windows)
    busy = example(
        [work(i, 90, 1 + i % 3, i % 5) for i in range(1, 11)],
        windows,
        events=tuple(FixedEvent(i, "Lecture", DAY + timedelta(days=i), 600, 690) for i in range(5)),
    )
    yield "busy_commitments", 0, busy
    yield "overloaded", 0, example([work(i, 180, 1 + i % 3) for i in range(1, 13)], windows)
    yield "competing_deadlines", 0, example([work(i, 90, 2, i % 3) for i in range(1, 9)], windows)
    yield (
        "important_later",
        0,
        example([work(1, 60, 1, 0), work(2, 60, 3, 2)], [TimeWindow(1, DAY, 540, 600)]),
    )
    saved = (SavedSession(1, 1, DAY, 540, 600, "planned", 0),)
    yield (
        "preserve_routine",
        0,
        example([work(1, 60, 2, 0, 660), work(2, 60, 2, 0, 600)], sessions=saved),
    )
    yield (
        "dependency_chain",
        0,
        example(
            [work(i, 40, 2, 0) for i in range(1, 4)],
            dependencies=(TaskDependency(2, 1), TaskDependency(3, 2)),
        ),
    )
    fragmented = [
        TimeWindow(i * 3 + j, DAY + timedelta(days=i), a, b)
        for i in range(5)
        for j, (a, b) in enumerate([(540, 555), (600, 620), (900, 930)])
    ]
    yield "fragmented", 0, example([work(i, 90) for i in range(1, 5)], fragmented)
    yield "greedy_suboptimal", 0, example([work(1, 60, 2, 0, 660), work(2, 60, 2, 0, 600)])
    yield "greedy_already_good", 0, example([work(1, 60, 2, 0, 600), work(2, 60, 2, 0, 660)])
    yield (
        "off_grid_routine",
        0,
        example([work(1, 60)], sessions=(SavedSession(1, 1, DAY, 554, 614, "planned", 0),)),
    )
    yield "no_capacity", 0, example([work(1, 60)], [])
    for seed in (20875, 88, 991):
        rng = random.Random(seed)
        steps = [
            work(
                i,
                rng.choice([30, 60, 90, 150]),
                rng.randint(1, 3),
                rng.randint(0, 4),
                rng.choice([660, 780, 1020]),
            )
            for i in range(1, 13)
        ]
        days = [DAY + timedelta(days=i) for i in range(5)]
        yield (
            "seeded_mixed",
            seed,
            example(
                steps,
                [],
                budgets=tuple(DayBudget(d, rng.choice([90, 120, 180])) for d in days),
                preferences=tuple(DayPreference(d, 540, 1020) for d in days),
                events=tuple(
                    FixedEvent(i, "Fixed commitment", d, 660, 780) for i, d in enumerate(days)
                ),
            ),
        )


def audit(snapshot, proposal, now=NOW):
    """Independent minute-occupancy audit, distinct from the interval model/validator."""
    issues = []
    occupied = set()
    for event in snapshot.events:
        occupied.update((event.day, minute) for minute in range(event.start, event.end))
    daily = {}
    for session in snapshot.sessions:
        if session.status == "done":
            occupied.update((session.day, m) for m in range(session.start, session.end))
            daily[session.day] = daily.get(session.day, 0) + session.actual_minutes
    allowed = {(w.day, m) for w in effective_windows(snapshot) for m in range(w.start, w.end)}
    steps = {s.id: s for s in snapshot.steps if s.kind == "timed" and not s.parent_completed}
    allocated = {}
    by_task = {}
    cutoff = now.hour * 60 + now.minute + bool(now.second or now.microsecond)
    for slot in proposal.slots:
        step = steps.get(slot.step_id)
        if step is None:
            issues.append("unknown_step")
            continue
        points = {(slot.day, m) for m in range(slot.start, slot.end)}
        if not 0 <= slot.start < slot.end <= 1440:
            issues.append("duration")
        if points & occupied:
            issues.append("overlap")
        if not points <= allowed:
            issues.append("availability")
        if not now.date() <= slot.day <= proposal.sunday or (
            slot.day == now.date() and slot.start < cutoff
        ):
            issues.append("time_boundary")
        if step.deadline and (
            slot.day > step.deadline
            or (
                slot.day == step.deadline
                and slot.end > (step.deadline_minute if step.deadline_minute is not None else 1440)
            )
        ):
            issues.append("deadline")
        occupied |= points
        daily[slot.day] = daily.get(slot.day, 0) + slot.minutes
        allocated[slot.step_id] = allocated.get(slot.step_id, 0) + slot.minutes
        by_task.setdefault(step.task_id, []).append(slot)
    done_daily = {}
    for session in snapshot.sessions:
        if session.status == "done":
            done_daily[session.day] = done_daily.get(session.day, 0) + session.actual_minutes
    for budget in snapshot.budgets:
        # Historical excess cannot be undone; no further work may be added there.
        if daily.get(budget.day, 0) > max(budget.minutes, done_daily.get(budget.day, 0)):
            issues.append("daily_budget")
    residual = {s.step_id: s.minutes for s in proposal.shortfalls}
    for i, step in steps.items():
        if allocated.get(i, 0) > step.remaining_minutes:
            issues.append("overallocated")
        if allocated.get(i, 0) + residual.get(i, 0) != step.remaining_minutes:
            issues.append("work_accounting")
    completed = {s.id for s in snapshot.task_states if s.completed}
    for edge in snapshot.dependencies:
        children = by_task.get(edge.task_id, [])
        if not children:
            continue
        required = [s for s in snapshot.steps if s.task_id == edge.prerequisite_id]
        if edge.prerequisite_id in completed or any(s.parent_completed for s in required):
            continue
        timed = [s for s in required if s.kind == "timed"]
        if (
            not timed
            or any(s.kind == "checklist" and not s.checked for s in required)
            or any(allocated.get(s.id, 0) != s.remaining_minutes for s in timed)
        ):
            issues.append("dependency_completion")
        earlier = by_task.get(edge.prerequisite_id, [])
        if earlier and max((s.day, s.end) for s in earlier) > min(
            (s.day, s.start) for s in children
        ):
            issues.append("dependency_order")
    return issues


def evaluate(repeats=3, time_limit=1.0):
    if repeats < 1:
        raise ValueError("repeats must be positive")
    rows = []
    for name, seed, snap in scenarios():
        for method in ("greedy_preserve", "greedy_rebuild", *GOALS):
            for repeat in range(repeats):
                tick = perf_counter()
                if method.startswith("greedy"):
                    proposal = make_revision(
                        snap, NOW, preserve_existing=method == "greedy_preserve"
                    )
                    status, engine, proven = "HEURISTIC", "greedy", 0
                    solver_ms = 0.0
                else:
                    result = optimize(snap, NOW, goal=method, time_limit=time_limit)
                    proposal = result.revision
                    status, engine, proven = result.status, result.engine, result.proven_levels
                    solver_ms = result.solver_seconds * 1000
                elapsed = (perf_counter() - tick) * 1000
                violations = audit(snap, proposal)
                validate_revision(snap, proposal, NOW)
                rows.append(
                    {
                        "scenario": name,
                        "seed": seed,
                        "repeat": repeat + 1,
                        "tasks": len(snap.steps),
                        "method": method,
                        "engine": engine,
                        "status": status,
                        "proven_levels": proven,
                        **schedule_metrics(snap, proposal, NOW),
                        "constraint_violations": len(violations),
                        "runtime_ms": round(elapsed, 3),
                        "solver_runtime_ms": round(solver_ms, 3),
                        "time_limit_s": time_limit,
                    }
                )
                if violations:
                    raise AssertionError((name, method, violations))
        print(f"Evaluated {name} (seed {seed})", flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--time-limit", type=float, default=1.0)
    parser.add_argument("--csv", type=Path, default=Path("docs/optimizer-benchmark.csv"))
    args = parser.parse_args()
    rows = evaluate(args.repeats, args.time_limit)
    with args.csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} measurements to {args.csv}")


if __name__ == "__main__":
    main()
