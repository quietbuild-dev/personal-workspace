"""Repeatable, controlled greedy baseline comparison (no UI, no personal database)."""

import argparse
import statistics
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from time import perf_counter

from workspace.advanced_planner import make_revision
from workspace.advanced_repository import (
    accept_revision,
    add_fixed_event,
    add_step,
    add_window,
    initialize_advanced,
    load_snapshot,
    record_session,
)
from workspace.models import TaskDraft
from workspace.repository import create_task


def benchmark(repeats: int = 100) -> dict[str, float | int]:
    if type(repeats) is not int or repeats < 1:
        raise ValueError("Repetitions must be positive.")
    monday = date(2026, 11, 16)
    tuesday = monday + timedelta(days=1)
    wednesday = monday + timedelta(days=2)
    friday = monday + timedelta(days=4)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "evaluation.db"
        initialize_advanced(path)
        for day in (tuesday, wednesday, friday):
            add_window(path, day, 9 * 60, 18 * 60)
        add_fixed_event(path, "Statistics lecture", tuesday, 11 * 60, 13 * 60)
        for index in range(12):
            task = create_task(
                path,
                TaskDraft(f"University task {index + 1}", "University", friday, 3 - index % 3, 120),
            )
            add_step(path, task.id, f"Review unit {index + 1}", "timed", 120)
        start = datetime(2026, 11, 17, 8, 0)
        proposal = make_revision(load_snapshot(path), start)
        accept_revision(path, proposal, start)
        # Simulate a legitimately missed session. The accepted plan remains saved.
        first = min(
            (s for s in load_snapshot(path).sessions if s.day == tuesday),
            key=lambda s: (s.start, s.id),
        )
        record_session(path, first.id, "missed", now=datetime(2026, 11, 17, 18, 0))
        snapshot = load_snapshot(path)
        now = datetime(2026, 11, 18, 8, 0)
        times = {True: [], False: []}
        outputs = {}
        for preserve in (True, False):
            for _ in range(repeats):
                tick = perf_counter()
                result = make_revision(snapshot, now, preserve_existing=preserve)
                times[preserve].append((perf_counter() - tick) * 1000)
            outputs[preserve] = result
        stable, baseline = outputs[True], outputs[False]
        return {
            "preserved_work_minutes": stable.planned_minutes,
            "baseline_work_minutes": baseline.planned_minutes,
            "preserved_unchanged_sessions": stable.unchanged,
            "baseline_unchanged_sessions": baseline.unchanged,
            "preserved_changed_sessions": stable.removed_or_changed,
            "baseline_changed_sessions": baseline.removed_or_changed,
            "preserved_shortfall_minutes": sum(s.minutes for s in stable.shortfalls),
            "baseline_shortfall_minutes": sum(s.minutes for s in baseline.shortfalls),
            "preserved_runtime_ms_median": round(statistics.median(times[True]), 4),
            "baseline_runtime_ms_median": round(statistics.median(times[False]), 4),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=100)
    args = parser.parse_args()
    print("Controlled benchmark: 12 study steps, lecture, missed session, fixed dates.")
    for name, value in benchmark(args.repeats).items():
        print(f"{name}: {value}")
    print("Greedy allocation is not a proof of optimality or infeasibility.")


if __name__ == "__main__":
    main()
