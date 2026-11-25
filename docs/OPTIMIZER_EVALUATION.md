# Optimizer evaluation — 25 November 2026

All data is synthetic. No personal SQLite database was opened for evaluation.

## Method

Fifteen scenarios: twelve hand-designed examples and three mixed workloads generated
with seeds 20875, 88 and 991. Each scenario runs both original greedy strategies and
all five optimizer profiles three times: 315 measurements in
[optimizer-benchmark.csv](optimizer-benchmark.csv). The workloads cover light, busy,
overloaded, competing-deadline, high-priority-later, routine, dependency-chain,
fragmented, greedy-suboptimal, greedy-already-good, off-grid and empty-capacity cases.

Environment: Python 3.12.13, Windows 11 (AMD64),
OR-Tools 9.15.6755, Streamlit 1.67.0. One solver worker,
solver seed 20875; one second shared across objective levels (the UI uses two).
Runtime is measured per call with perf_counter. End-to-end runtime includes greedy
construction, model building, search, coalescing, validation and any first import.
Solver runtime separately measures time spent inside solve calls. These are local
machine observations, not a latency guarantee or a statistical population study.

Each algorithm receives the same immutable snapshot and fixed local time, 16 November
2026 at 08:00. The greedy baseline retains its date-first ordering, with dependency
and completed-history safety checks applied to both engines. Results are checked by
the approval validator and an independent minute-occupancy audit that checks time,
availability, overlap, deadlines, budgets, work conservation and precedence.

## Aggregate results

The work columns sum the 15 scenarios, averaged over the three repeats. Runtime
columns are medians across the 45 calls for each method, not a sum of medians.

| Method | Work min | High-priority min | End-to-end median ms | Solver median ms | Proven / feasible |
| --- | ---: | ---: | ---: | ---: | --- |
| greedy_preserve | 4615 | 2040 | 0.26 | 0.00 | heuristic |
| greedy_rebuild | 4615 | 2040 | 0.18 | 0.00 | heuristic |
| deadlines | 4735 | 1890 | 49.77 | 36.05 | 30 / 15 |
| important | 4735 | 2190 | 51.79 | 37.61 | 30 / 15 |
| routine | 4675 | 1860 | 49.51 | 35.11 | 30 / 15 |
| throughput | 4735 | 1860 | 48.09 | 35.54 | 30 / 15 |
| balance | 4735 | 1860 | 146.18 | 133.36 | 30 / 15 |

Constraint violations: **0** across all 315 measurements.

The optimizer adds 120 scheduled minutes to the greedy total for deadlines, priority,
and throughput in this suite (4735 versus 4615, about 2.6%). The routine profile adds
60 minutes while preserving the deliberately conflicting accepted block. These are
scenario-specific differences, not an estimate of improvement on student workloads.

## Trade-offs visible in the examples

- **Greedy suboptimal:** the baseline sorts by deadline date, not the exact deadline
  time. Two one-hour tasks with 10:00/11:00 cutoffs fit only 60 minutes in the greedy
  ordering and 120 minutes with the optimizer. This isolates a real weakness in the
  existing implementation; it does not show that all greedy algorithms are weak.
- **Greedy already good:** ordering those same tasks by their times lets both methods
  schedule 120 minutes. Greedy is faster.
- **Important later:** with one available hour, deadlines schedules the earlier low
  priority task. The important profile schedules 60 high-priority minutes instead.
  It leaves the earlier task at risk; the extra priority coverage is not free.
- **Preserve routine:** routine preserves one accepted block and schedules 60 minutes.
  Throughput changes that block and schedules 120. This is an objective trade-off.
- **Light workload:** both greedy and throughput put 180 minutes on one day. Balance
  schedules the same 180 minutes with a peak of 36 minutes across five days. It uses
  more blocks, illustrating the trade-off between peak load and fragmentation.
- **Busy/overloaded/fragmented:** the final optimizer matches the greedy scheduled
  totals of 450/900/325 minutes. These cases finish with feasible incumbents, not
  complete optimality proofs. Greedy gives those totals at much lower runtime.

Across all scenarios, important schedules 2190 high-priority minutes versus 2040 for
greedy. Throughput schedules 1860: more total work does not imply more high-priority
work. The goal distinction matters, and no method dominates every metric.

## Metric definitions and limitations

- Useful work: sum of proposed minutes, capped by each step remaining duration.
- Before-deadline work: minutes for dated steps; all proposed blocks respect deadlines.
  Due coverage and shortfall use tasks due by Sunday, including overdue shortfalls.
  A task at risk is a unique parent task with a due shortfall, not an observed failure.
- Priority coverage: scheduled high-priority minutes divided by high-priority remaining
  minutes. A zero-demand category displays 100%. The CSV also records weighted
  priority and urgency scores, the actual first objectives of those profiles.
- Preservation: exact step/date/start/end match. Moved counts pair old-only/new-only
  blocks of the same step; unmatched old blocks count as removed. This is a reporting
  convention for split/merged blocks, not a claim that block identity survives a move.
- Balance: population standard deviation and peak daily load, including zero days
  from today through Sunday and already completed actual work. Only peak is optimized.
- Fragmentation: output block count and count below 25 minutes. The model minimizes
  selected segment intervals, a proxy that can differ after coalescing.

The examples are small and synthetic. They do not establish general superiority,
predict real user behavior, or measure cognitive switching costs. Wall-time limits
can produce different incumbents between runs. A proven result is specific to the
bounded interval model. The fallback deliberately favors a usable plan over an
unproven claim of improvement. Capacity explanations are per-task upper bounds,
not solver unsatisfiable cores and not checked counterfactual feasibility proofs.

## Validation

- `python -m ruff check .`: passed.
- `python -m ruff format --check .`: passed.
- `python -m pytest -q`: 209 passed, 58 subtests passed.
- `python -m scripts.check_ui`: Home and Calendar loaded on temporary data.
- `python -m scripts.check_optimizer_ui`: goal generation/comparison, approval, Undo
  and adding/removing prerequisites passed on a temporary database.
- A separate localhost Streamlit process was exercised through its agent API:
  Home, Calendar, goal generation and the five-row comparison returned ready.
  No new server warnings or exceptions appeared. The process was stopped afterward.

The AppTest runners emit the documented bare-mode Missing ScriptRunContext warning
on their main thread. This is not an application exception. The Windows desktop
launcher and visual/pixel layout were not manually tested in this upgrade.

## Reproduction

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_optimizer --repeats 3 --time-limit 1 --csv docs/optimizer-benchmark.csv
.\.venv\Scripts\python.exe -m scripts.check_optimizer_ui
```

The existing `scripts.evaluate_rescue` benchmark remains available for the original
greedy strategy comparison. No merge, push, deployment or personal-data migration
was performed during implementation.
