"""Summarize comparable optimizer runs without cherry-picking scenarios.

Usage: python -m scripts.summarize_optimizer_benchmark --csv docs/optimizer-benchmark.csv
Run the evaluator again to populate new movement and short-session metrics.
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import median


def summarize(rows):
    """Report median metrics and per-scenario changes against greedy rebuild.

    No headline 'win' is claimed when a metric is tied or the method is a
    fallback. Every method is summarized across all scenarios and repeats.
    """
    by_method = defaultdict(list)
    by_scenario = defaultdict(lambda: defaultdict(list))
    for row in rows:
        by_method[row["method"]].append(row)
        by_scenario[row["scenario"]][row["method"]].append(row)
    if not by_method:
        raise ValueError("No benchmark results found.")

    lines = [
        "Method | runs | median scheduled minutes | median due % | median runtime ms | violations"
    ]
    lines.append("--- | ---: | ---: | ---: | ---: | ---:")
    for method, entries in sorted(by_method.items()):

        def med(key):
            return median(float(r[key]) for r in entries)

        violations = sum(int(r["constraint_violations"]) for r in entries)
        lines.append(
            f"{method} | {len(entries)} | {med('scheduled_minutes'):g} | "
            f"{med('due_coverage_pct'):g} | {med('runtime_ms'):.1f} | {violations}"
        )

    lines.append("\nScheduled minutes by scenario (median difference from greedy_rebuild):")
    for scenario, methods in sorted(by_scenario.items()):
        if "greedy_rebuild" not in methods:
            continue
        baseline = median(float(r["scheduled_minutes"]) for r in methods["greedy_rebuild"])
        comparisons = []
        for method in sorted(methods):
            if method.startswith("greedy"):
                continue
            current = median(float(r["scheduled_minutes"]) for r in methods[method])
            comparisons.append(f"{method}: {current - baseline:+g} min")
        lines.append(f"- {scenario}: " + "; ".join(comparisons))
    lines.append("\nNote: scheduled minutes represent reserved time, not completed assignments.")
    lines.append("Runtime includes solution generation; feasibility audit is performed separately.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=Path("docs/optimizer-benchmark.csv"))
    args = parser.parse_args()
    with args.csv.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    print(summarize(rows))


if __name__ == "__main__":
    main()
