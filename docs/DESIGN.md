# Small technical contract

This document records the implemented MVP's design rules. The original
contracts were written before implementation; the current callable signatures
are documented below and in `MVP_IMPLEMENTATION.md`.

## Boundaries

`app.py` configures navigation. Files in `workspace/views/` render UI and call
small functions. `repository.py` contains SQLite access; `models.py` owns domain
data and validation; `planner.py` and `metrics.py` contain pure calculations.
Neither calculation module imports Streamlit or opens a database.

Do not add a web API, an ORM, abstract base classes, a dependency-injection
framework, or a service hierarchy for this project. Introduce another module
only if actual duplication or a clear new responsibility makes it useful.

## Data model

### Task

| Field | Python type / storage | Rule |
| --- | --- | --- |
| `id` | `int` / SQLite integer primary key | Database assigned; stable tie-breaker. |
| `title` | `str` / TEXT | Trimmed; 1–120 characters. |
| `category` | `str` / TEXT | One trimmed label, 1–40 characters; default Personal. |
| `deadline` | `date \| None` / ISO YYYY-MM-DD or NULL | Due by the end of this calendar date. |
| `priority` | `int` / INTEGER | 1=Low, 2=Medium, 3=High. |
| `estimate_minutes` | `int` / INTEGER | Positive whole minutes; original estimate. |
| `remaining_minutes` | `int` / INTEGER | 0 through estimate_minutes. Increase the estimate if extra work is discovered. |
| `status` | `str` / TEXT | `pending` or `completed`. |
| `created_at` | aware `datetime` / ISO TEXT | Recorded once when created. |
| `completed_at` | aware `datetime \| None` / ISO TEXT or NULL | Set only while completed. |

At creation, remaining equals estimate and status is pending. Completing sets
remaining to zero and records completion time. Reopening requires a positive
remaining estimate and clears completion time. Saving zero remaining means
completion; status and remaining must never contradict each other. A pending
task must have positive remaining time and no completion timestamp.

A task may be split across multiple days. There is no work log: users update
remaining work manually after a partial session. Planned minutes do not reduce
remaining minutes. Crossing into tomorrow does not imply yesterday's plan was
completed. The application should make this explicit near the remaining field.

Allow past deadlines to remain in the system; they identify overdue work rather
than being rejected during load. Deleting a task removes it from current metrics;
there is no historical audit trail in this version.

### Daily availability

| Field | Python type / storage | Rule |
| --- | --- | --- |
| `day` | `date` / ISO TEXT primary key | An actual calendar date, not a weekday name. |
| `available_minutes` | `int` / INTEGER | 0–1440. Missing date means zero availability. |

The UI edits the current Monday–Sunday week. Past dates are disabled and ignored
by scheduling. Today's entry is **remaining** work time available today, not a
full-day capacity automatically adjusted by a clock. Future entries are whole-day
capacity. Users update today's remaining availability when necessary. Store
actual dates so last week's availability cannot silently become next week's.

The app uses the local computer's calendar date. Compute `today` at the app
boundary and pass it explicitly into calculations; do not call the clock inside
the planner. Store completion timestamps with a timezone offset. A future hosted
or multi-timezone version would need an explicit user timezone setting.

### Derived results, not persisted tables

- `Allocation(task_id, day, minutes)` — positive integer minutes assigned to one
  task on one date.
- `Unallocated(task_id, minutes, reason)` — residual work and a reason such as
  `overdue`, `insufficient_capacity_before_deadline`, or `outside_current_plan`.
- `PlanResult(allocations, unallocated)` — every incomplete task's remaining
  minutes are accounted for exactly once across these results.

No allocations table, weekly snapshot, or saved progress percentage is needed.
Persist tasks and availability only. Recompute from the current saved records.

## Suggested function contracts

These signatures summarize the implemented API (see the code for exact defaults).

```python
initialize_database(db_path: Path) -> None
list_tasks(db_path: Path) -> list[Task]
create_task(db_path: Path, draft: TaskDraft) -> Task
update_task(db_path: Path, task_id: int, draft: TaskDraft, remaining_minutes: int) -> Task
delete_task(db_path: Path, task_id: int) -> None
load_availability(db_path: Path, start: date, end: date) -> dict[date, int]
save_availability(db_path: Path, values: dict[date, int]) -> None

generate_plan(
    tasks: list[Task],
    availability: dict[date, int],
    today: date,
) -> PlanResult

calculate_metrics(tasks: list[Task], plan: PlanResult, availability: dict[date, int], today: date) -> DashboardMetrics
```

TaskDraft omits database-generated identity and timestamps. Keep public
validation in `models.py`; repository functions validate inputs before writing.
Use parameterized SQL, transaction boundaries, and database CHECK constraints
for priorities, nonnegative minutes, and consistent completion state. Use an
explicit connection close or `contextlib.closing`; a sqlite3 transaction context
alone does not close the connection. Pass temporary paths in tests.

Derive the normal database path from the project location, not an arbitrary
current working directory. Create `data/` on first use. Database initialization
must be safe to repeat without deleting records. Do not store connections or
mutable task lists in a global Streamlit cache.

## Planning policy

Use a **deadline-first greedy allocation with priority tie-breaking**. Its
priority awareness is deliberately limited: an earlier deadline outranks a
higher-priority task with a later deadline. Make that behavior visible and
document it rather than presenting an opaque weighted importance score.

1. Build the dates from `today` through the current Sunday, inclusive.
2. Copy capacities for those dates; treat missing values as zero. Validate
   negative or invalid inputs instead of silently producing an impossible plan.
3. Exclude completed tasks. Report pending tasks with deadlines before today
   as overdue and leave their entire remaining work unallocated.
4. Sort the other pending tasks by `(deadline or date.max, -priority, id)`.
5. For each task, consider dates in chronological order through the earlier of
   its deadline and Sunday. Undated tasks may use every remaining date.
6. Assign `min(task_remaining, day_capacity_left)` positive minutes, then reduce
   the local remaining quantities. Continue across days until the task is fully
   allocated or eligible capacity runs out.
7. Return allocations and residual work. Residual on a task due this week is a
   deadline-capacity shortfall. Residual on an undated or later-due task is
   outside this week's plan; it is not proof the future deadline is infeasible.

An overdue task stays clearly visible. Do not quietly move its deadline or label
an after-deadline allocation as on time. The user can explicitly revise or clear
its deadline to include it in a new plan. This is a deliberate MVP limitation.

Splitting uses arbitrary positive whole minutes. There are no minimum session
lengths, appointments, start times, dependencies, or consecutive-day constraints.
On a Sunday there is only one eligible day. On the next Monday the horizon moves
to the new week; capacity does not automatically repeat.

This is a deterministic heuristic, not an optimal schedule or proof that all
unscheduled tasks can never be completed. Runtime is `O(n log n + n d)` and output
space is `O(n d)` in the worst case, with `d <= 7` and `n` tasks. Equal inputs,
including IDs and today, must yield equal output regardless of input list order.

### Worked example

Assume today is Wednesday, November 11, 2026. Available time is 60 minutes
Wednesday, 60 Thursday, and 60 Friday; Saturday and Sunday have zero capacity.

| Task | Deadline | Priority | Remaining |
| --- | --- | --- | ---: |
| A: assignment | Thu Nov 12 | Medium | 90 min |
| B: reading | Thu Nov 12 | Low | 45 min |
| C: preparation | Fri Nov 13 | High | 90 min |

Expected result:

| Date | Allocation | Total |
| --- | --- | ---: |
| Wed Nov 11 | A 60 min | 60 min |
| Thu Nov 12 | A 30 min + B 30 min | 60 min |
| Fri Nov 13 | C 60 min | 60 min |

B has 15 minutes and C has 30 minutes unallocated before their deadlines.
The plan reports a 45-minute shortfall. C's higher priority does not displace
the earlier-deadline tasks. No positive work is allocated to zero-capacity dates.

## Dashboard metrics

| Metric | Precise definition |
| --- | --- |
| Open tasks | Number of currently pending tasks, including overdue and undated work. |
| Remaining work | Sum of remaining_minutes for all pending tasks, displayed in hours/minutes. |
| Due this week · completed | Completed tasks whose deadline is within the current Monday–Sunday week divided by all retained tasks with a deadline in that same week. Display numerator and denominator; no denominator means N/A, not 100%. |
| Today's focus | The first three tasks with allocations today, in planner order. Show allocated minutes and a link to the full plan. |
| Upcoming deadlines | Pending tasks due today or later, sorted by deadline. Show overdue tasks separately. |
| Weekly workload | Planned minutes and remaining capacity per eligible day; past days are labeled past, not presented as a history of completed work. |
| Insight | Overdue work first; otherwise unmet work due this week; otherwise unallocated later/undated backlog; otherwise unused capacity. |

Do not label the completion ratio "percentage of everything completed this week":
its population is **tasks due this week**. Completed_at supports an optional
completion count later; it is not the numerator filter for this ratio. Edits to
deadlines or task deletion can change the cohort, so this is a current overview,
not a historical performance chart.

For capacity insights, aggregate planner residuals for relevant deadlines rather
than subtracting total weekly hours. Two spare hours on Sunday cannot repair a
shortfall for a task due Thursday. Show a concise explanation linking to the
tasks that did not fit.

## Mutation and replanning flow

Submit form -> validate -> write transaction -> rerun -> reload tasks and
availability -> compute plan and metrics -> render. On validation or database
failure, show an actionable error and do not claim the save succeeded. Keep
unsaved form contents available for correction when possible.

Stable task-ID-based widget keys prevent one task's edit state being applied to
another. Use session state for temporary form selection, not durable records.
Avoid caching calculations initially; there is no performance need for this
small dataset. No separate manual synchronization between the three pages.
