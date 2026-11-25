# Rescue My Week - Technical milestone (17 November 2026)

This document records the original greedy milestone. For the current goal-based
engine, see [GOAL_BASED_OPTIMIZER.md](GOAL_BASED_OPTIMIZER.md).

## The problem addressed

The application stores unfinished assignments, deadlines, accepted study blocks,
classes, appointments and user-selected planning hours. When a new lecture or
missed session disrupts the timetable, an ordinary calendar shows a conflict
but does not suggest a safe repair. Our contribution is a **reviewable schedule
repair** with a comparison of disruption and deadline coverage.

## Two strategies, one set of constraints

In Calendar, the **Rescue my week** panel compares:

1. **Keep my plans:** Preserve eligible accepted sessions, then fill remaining
   gaps deadline-first. Invalidated sessions can be replaced.
2. **Rebuild my week:** Ignore the accepted plan during construction, then
   schedule all remaining timed work deadline-first into eligible gaps.

Both use the same pure deterministic scheduling engine, fixed-event exclusions,
daily study budgets, preferred study periods, deadline dates/times and remaining
work. Neither strategy is claimed optimal. Both outputs are validated by the
same independent constraints on acceptance.

For each proposal, we show **minutes placed**, **existing blocks moved/removed**
and **unscheduled work due this week**. Later-deadline work left outside the week
is not incorrectly counted as an immediate deadline risk. Risks are grouped by
parent assignment; multiple study steps of one assignment do not create
separate misleading alerts. An at-risk warning means *the heuristic could not
place the work under the saved constraints*, not that the problem is impossible.

## Read-only what-if simulation

The **What if I lose study time?** control adds an in-memory unavailable period
(morning, afternoon, evening, or whole day). It computes a hypothetical
revision, compares it against the normal preview, and highlights assignments
whose deadlines become harder to meet. It does **not** modify SQLite.
A scenario has a synthetic fingerprint which cannot be accepted against
actual saved user data. This is tested, in addition to atomic acceptance of
real proposals and stale-preview rejection.

## Implementation and interesting engineering decisions

- Pure Python algorithm and assessment code are independent of Streamlit/SQLite.
- SQLite saves accepted sessions transactionally, retaining unchanged row IDs.
- Optimistic fingerprint checks make previews stale after schedule inputs change.
- Scenario modifications are immutable (`dataclasses.replace`), never database writes.
- Compare the same snapshot with `preserve_existing=True` vs `False`, separating
  scheduling coverage from disruption to prior commitments.
- The baseline is a **full greedy reschedule**, not a mathematically optimal solver.
- The input has finite, date-specific study budgets, distinguishing free time
  from consented study time.

## Demonstration (five minutes)

1. Create two assignments with deadlines and schedule a couple of study blocks.
2. Add a conflicting lecture. Show the existing calendar is not silently changed.
3. Open **Rescue my week**. Compare the two alternatives' placement, deadline
   shortfall and number of disrupted blocks.
4. Use **What if I lose study time?** to block an afternoon; show the impact
   on at-risk work without changing saved data.
5. Accept a real strategy, restart the app, confirm persistence, then show
   automatic regression tests and the scaling benchmark.

## Reproducible experiment

Run from the project root:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_rescue --repeats 30 --csv docs\rescue-benchmark-local.csv
```

This generates synthetic workloads of 8, 16, 32 and 64 timed assignments;
each includes lectures, accepted sessions and a newly introduced class
conflict. For each strategy it reports work placed, deadline-risk minutes,
disrupted sessions and median computation time. It does not open the personal
database. Compare metrics for **the same workload size**, and repeat on the
actual Windows computer before quoting timings in the report.

### Limitations to state openly

- Greedy allocation is not a global optimizer, so an unplaced step does not
  demonstrate mathematical infeasibility.
- Planning proposals currently cover the remainder of the **current week**.
- The what-if simulator models one extra unavailable period; it does not
  forecast long-term habits or learn productivity from private behavior.
- Changing dates/preferences may require approving new times; nothing is
  moved without a deliberate user action.
- A Streamlit browser walkthrough is still necessary beyond unit/smoke tests.

## Course submission reminder

The Fall 2026 guidelines call for code, a one-page **interesting-problems**
report and relevant material by **Friday 27 November 2026 at 23:59**;
presentations are short (aim for approximately ten minutes). The report should
emphasize noteworthy hurdles and design decisions, **not** function-by-function
instructions or generic product marketing. The demonstrations and benchmark
are supporting evidence, not substitutes for the required report.
