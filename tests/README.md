# Meaningful tests to add with each feature

No automated feature tests are included in the setup-only starter. Add the
following tests alongside their implementation, using pytest. Keep dates fixed
and use tmp_path for every test database; never use a personal database in tests.

| Area | Essential behavior |
| --- | --- |
| Validation | Trim valid input; reject blank titles, negative/non-integer durations, invalid priority, and contradictory completion state. |
| Persistence | Task create/read/edit/delete; survive a closed and reopened connection; preserve date and timestamp fields; initialize twice without data loss. |
| Completion | Completing sets remaining=0 and completed_at; reopening clears completed_at and restores explicitly entered positive remaining time. |
| Availability | Save and reload by actual date; updates replace only selected dates; missing date supplies zero capacity. |
| Planner empty/zero | Empty tasks and zero availability return valid results with no spurious allocations. |
| Planner splitting | A 90-minute task with 60+60 available receives 60+30 across days. |
| Planner deadline | Capacity after a deadline cannot satisfy work due earlier; a task due today may use today. |
| Planner priority | Same-deadline higher-priority task is allocated first; lower ID breaks remaining ties. |
| Planner residual | A partially allocated task reports its exact remaining minutes. |
| Planner exclusions | Completed tasks receive no allocation; overdue pending tasks are separately reported and not scheduled silently after the deadline. |
| Planner horizon | Sunday has one eligible day; Monday starts a new horizon; past days and out-of-week capacities are ignored. |
| Planner future work | Residual for later/undated tasks is backlog, not a claim of a missed future deadline. |
| Planner deterministic | Repeated calls and permuted task input give the same ordered output without mutating inputs. |
| Metrics | Exact due-this-week cohort; zero denominator gives N/A; overdue counts and remaining minutes agree with source tasks. |
| Integration | Create tasks + save capacity -> plan -> mark task complete -> replan; no ghost work remains and dashboard values change. |

For every valid planner scenario, check these invariants:

1. Every allocation has positive integer minutes and refers to a known pending task.
2. Allocation dates are within today through Sunday and no later than the deadline.
3. Sum of daily allocated minutes does not exceed that day's available minutes.
4. For each pending task, allocated minutes + unallocated minutes equals its
   remaining minutes exactly.
5. Completed tasks have no allocated or unallocated work; input records are unchanged.

Use small concrete fixtures, including the worked example in DESIGN.md, plus a
fixed-seed set of generated valid scenarios for invariants if time permits.
Do not add a property-testing dependency solely for this project.

Add a small Streamlit AppTest integration test when forms are connected. Test
create/complete/replan behavior, not exact card wording or column count. Also
manually inspect the three pages at normal laptop and narrow window sizes.

Before submission, install dependencies in a fresh virtual environment, run the
tests, and execute the demo from a clean checkout. Record the actual checks and
their results; do not claim test coverage for features that are not implemented.
