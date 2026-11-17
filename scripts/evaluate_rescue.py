"""Repeatable scale test for the two Rescue My Week scheduling strategies.

Usage:
    python -m scripts.evaluate_rescue --repeats 25 --csv results.csv

Synthetic data only. Never opens a user's database. Median milliseconds are
machine-specific and not a claim of optimality or general performance.
"""

import argparse
import csv
import statistics
from dataclasses import replace
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
    make_revision,
    validate_revision,
)
from workspace.planning_insights import compare_plans

NOW = datetime(2026, 11, 17, 8, 0)


def example_snapshot(task_count: int) -> PlannerSnapshot:
    """Deterministic workload with fixed lectures and one new timetable conflict."""
    if type(task_count) is not int or task_count < 1:
        raise ValueError("task_count must be positive.")
    days = tuple(NOW.date() + timedelta(days=i) for i in range(6))
    steps = tuple(
        StudyStep(
            id=i + 1,
            task_id=i + 1,
            task_title=f"Assignment {i + 1}",
            title="Study",
            kind="timed",
            estimate_minutes=90,
            remaining_minutes=90,
            checked=False,
            deadline=days[3] if i % 3 == 0 else days[-1],
            priority=3 - (i % 3),
            parent_completed=False,
        )
        for i in range(task_count)
    )
    budgets = tuple(DayBudget(day, 240) for day in days)
    preferences = tuple(DayPreference(day, 540, 1020) for day in days)
    lectures = tuple(
        FixedEvent(i + 1, f"Class on {day:%a}", day, 720, 780, "Lecture")
        for i, day in enumerate(days)
    )
    initial = PlannerSnapshot(
        steps=steps,
        windows=(),
        events=lectures,
        sessions=(),
        fingerprint=f"synthetic:{task_count}:initial",
        budgets=budgets,
        preferences=preferences,
    )
    accepted = make_revision(initial, NOW)
    sessions = tuple(
        SavedSession(i + 1, slot.step_id, slot.day, slot.start, slot.end, "planned", 0)
        for i, slot in enumerate(accepted.slots)
    )
    # Unexpected lecture forces at least one accepted session to move, if present.
    new_lecture = FixedEvent(10000, "Unexpected class", days[0], 540, 660, "Lecture")
    return replace(
        initial,
        events=(*lectures, new_lecture),
        sessions=sessions,
        fingerprint=f"synthetic:{task_count}:interrupted",
    )


def evaluate(sizes: tuple[int, ...], repeats: int = 20) -> list[dict]:
    if not sizes or any(type(n) is not int or n < 1 for n in sizes):
        raise ValueError("Supply positive task counts.")
    if type(repeats) is not int or repeats < 1:
        raise ValueError("repeats must be positive.")
    results = []
    for size in sizes:
        snapshot = example_snapshot(size)
        comparison = compare_plans(snapshot, NOW)
        timings: dict[str, list[float]] = {"preserve": [], "rebuild": []}
        for strategy, keep in (("preserve", True), ("rebuild", False)):
            for _ in range(repeats):
                tick = perf_counter()
                proposal = make_revision(snapshot, NOW, preserve_existing=keep)
                timings[strategy].append((perf_counter() - tick) * 1000)
            validate_revision(snapshot, proposal, NOW)
        for strategy, assessment in (
            ("preserve", comparison.preserve),
            ("rebuild", comparison.rebuild),
        ):
            results.append(
                {
                    "tasks": size,
                    "events": len(snapshot.events),
                    "strategy": strategy,
                    "scheduled_minutes": assessment.scheduled_minutes,
                    "at_risk_minutes": assessment.due_shortfall_minutes,
                    "blocks_moved_or_removed": assessment.moved_or_removed,
                    "unchanged_blocks": assessment.revision.unchanged,
                    "median_runtime_ms": round(statistics.median(timings[strategy]), 4),
                }
            )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[8, 16, 32, 64])
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()
    rows = evaluate(tuple(args.sizes), args.repeats)
    print("Synthetic scaling study; no personal data or database modifications.")
    print("tasks | events | strategy | placed min | risk min | moved | median ms")
    for row in rows:
        print(
            f"{row['tasks']:>5} | {row['events']:>6} | {row['strategy']:<8} | "
            f"{row['scheduled_minutes']:>10} | {row['at_risk_minutes']:>8} | "
            f"{row['blocks_moved_or_removed']:>5} | {row['median_runtime_ms']:>9.4f}"
        )
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"CSV saved: {args.csv}")
    print("Caution: the heuristic is not globally optimal; results depend on the example inputs.")


if __name__ == "__main__":
    main()
