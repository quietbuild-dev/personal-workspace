# MVP architecture and algorithm — implementation notes

## Responsibilities and data flow

1. `workspace/views/tasks.py` validates user input using `TaskDraft`, then calls
   `repository.py` to create, edit, complete, reopen, or delete task records.
2. `workspace/views/planner.py` saves capacities by **actual calendar date**
   through `save_availability`, then loads the shared overview again.
3. Both planner and dashboard call `load_overview(db_path, today)`, which loads
   saved tasks and date capacities, computes a pure `PlanResult`, and derives
   dashboard metrics. **Allocations are not stored**: recomputation avoids stale
   schedule rows when records change.
4. Browser reruns use local `date.today()` once per page execution. The planner
   and metrics functions receive this date explicitly, for deterministic tests.

SQLite stores tasks in the **unchanged** existing `tasks` table and availability
in a new table:

```sql
CREATE TABLE IF NOT EXISTS daily_availability (
    day TEXT PRIMARY KEY,
    available_minutes INTEGER NOT NULL CHECK(available_minutes BETWEEN 0 AND 1440)
);
```

Initialization uses `CREATE TABLE IF NOT EXISTS`; there are no drops or updates
to existing task rows. Availability entries are upserted atomically with
parameterized SQL, with validation **before any write**. Missing days have
capacity zero. Dates from a previous week do not populate the new week.

The default DB is `data/workspace.db` relative to the project; developers may
set `WORKSPACE_DB_PATH` **before starting Streamlit** to view an isolated demo DB.

## Deterministic deadline-first scheduler

Inputs: `tasks`, `availability`, and `today` (a real `datetime.date`). Output:
`PlanResult(allocations, unallocated)`, represented by immutable dataclasses.

1. Determine Monday–Sunday of `today`. Eligible dates are `today` through
   Sunday inclusive; past weekdays have no eligible slots. Today's entered
   availability is the **time remaining today**.
2. Ignore completed tasks. Mark any pending task due before today as **overdue**;
   none of its minutes are scheduled unless the deadline is manually changed.
3. Sort the other pending tasks by `(deadline or date.max, -priority, id)`.
   Earliest deadline wins; higher priority only breaks deadline ties. ID gives
   a stable final ordering regardless of the original list order.
4. For each task, visit eligible dates in chronological order, **through its
   deadline inclusive**, with the week horizon as an upper bound.
5. Allocate `min(task_minutes_left, capacity_left_on_day)`. Update local
   counters, not the task record. Work may span days. Never allocate negative
   or zero minutes.
6. Any leftover minutes due **by this Sunday** are a
   `insufficient_capacity_before_deadline` shortfall. Later-due or undated
   leftovers are `outside_current_plan` and not a claim about feasibility
   next week. Overdue tasks have a separate `overdue` reason.

For `n` tasks and `d <= 7` days the algorithm takes `O(n log n + n*d)` time and
`O(n*d)` output space. It is a transparent, cheap **heuristic**, not an optimal
solution to a general constraint optimization problem. Arbitrary positive
integer-minute splits are allowed; no time-of-day appointments, minimum session
length, task dependencies, or extra days beyond Sunday are modelled.

### Correctness invariants checked by tests

- Every allocation has a known pending task, a positive integer number of
  minutes, and a date between today and Sunday no later than its deadline.
- The sum scheduled on each day does not exceed saved availability for that date.
- For each pending task, scheduled + residual minutes exactly equals its saved
  remaining minutes, so work is not duplicated or lost.
- Completed tasks do not appear anywhere in plan output.
- Sorting and result order are stable under permutations of the task input.
- Calculation does not mutate task objects or database records.

Fixed-date tests cover splitting, inclusive deadlines, priority ordering, zero
capacity, overdue tasks, last day of week, Monday rollover, and 200
reproducible randomized scenarios with the main invariants.

## Definitions for dashboard metrics

- **Open tasks:** count of all pending tasks, including undated and overdue.
- **Remaining work:** sum of `remaining_minutes` over all pending tasks.
- **Due this week · completed:** count of completed tasks whose current deadline
  is Monday–Sunday inclusive / all retained tasks due in that week. Show
  numerator and denominator; display N/A when denominator is zero. The
  completion timestamp is **not** used to determine the weekly cohort.
- **Today's focus:** first three allocations scheduled today, in planner order.
- **Deadlines:** pending tasks before today are overdue; pending dated tasks
  today onward are upcoming. Earlier deadline then priority determines order.
- **Workload chart:** planned minutes vs saved available minutes for today
  through Sunday. It is **not** a chart of completed historical work.
- **Planning insight:** show overdue work first, otherwise unallocated work due
  this week, otherwise later/undated backlog, otherwise spare time. Due-week
  shortfalls use deadline-eligible capacity, **not** total weekly capacity.

## Constraints and known limitations

- The local machine's calendar day is authoritative. Time zones for future
  cloud/multi-user service would require explicit user settings.
- No history/audit log for deletions or completed sessions; deleted tasks leave
  the current metrics. The completion ratio reflects the **current** task set.
- Users explicitly update remaining work after working. A plan does not imply
  that work was completed.
- Streamlit's native layout is retained for maintainability; no custom web
  front end, extensive CSS overrides, or animation system.
- Dashboard and planner UI still require browser verification on the students'
  installed Streamlit version; see `docs/TEST_REPORT.md`.
