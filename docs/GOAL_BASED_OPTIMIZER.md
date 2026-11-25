# Goal-based weekly scheduling

Implemented on `feat/goal-based-optimizer`, in the isolated worktree. The optimizer
is a pure function. It returns the same `RevisionProposal` type as the original
greedy planner and has no database connection. The calendar still requires an
explicit approval, with validation inside the existing SQLite transaction.

## Scope and constraints

The planning horizon is the remainder of the current Monday–Sunday week. Time is
represented as local calendar dates and integer minutes. A date-only deadline
means the end of that day; a deadline time is an inclusive upper bound on session
end. Aware datetimes are rejected, as in the existing calendar. This is a local
wall-clock planner, not a timezone conversion or daylight-saving-time system.

The authoritative schedulable work is the remaining duration of timed study
steps under open tasks. Quick tasks already link their estimates to a timed step.
The parent task estimate is not added again. Checklist steps have no duration;
they are not silently converted into timed work. Legacy tasks with no timed steps
still need the existing **Schedule this task** action to opt into scheduling.

Hard constraints:

- Every proposed minute is inside effective availability, after the current time,
  before its task deadline and inside the horizon.
- No proposed intervals overlap each other, fixed events or completed session
  intervals. Completed actual minutes also consume the day's budget. Historical
  excess cannot be undone; no new minutes are added to an exhausted budget.
- The sum allocated to each step is no greater than its remaining minutes. Every
  remaining minute appears either in a proposed interval or a shortfall.
- Budgets and focus preferences retain their existing semantics: a budget date
  uses its focus range (08:00–22:00 by default) instead of legacy explicit windows.
  A zero budget is a day off. Dates without a budget or explicit window have no
  automatic availability. Legacy windows without a budget are limited by their
  actual length.
- A pending prerequisite must have **all** remaining timed work planned before
  any dependent task begins. Unchecked prerequisite checklists and pending
  prerequisites without timed work block downstream planning.

Deadlines remain hard placement boundaries for backwards compatibility. The
planner does not propose late work. Overdue and unfinished work is reported as
shortfall, including work that falls outside this week's horizon. An empty plan
with correct shortfalls is feasible; an overloaded week does not normally make
the model infeasible. `INFEASIBLE` therefore indicates a model/search problem,
not a proof that the user's whole workload is impossible.

Accepted **planned** sessions are editable proposal inputs, not immovable events.
Preservation is an objective; the saved rows do not move until approval. The
explicit “reschedule this session” action forbids its previous interval. Completed
and missed history is retained; completed blocks remain occupied, while missed
blocks do not reserve future study time.

## Model

First merge availability and subtract occupied intervals. Split the free intervals
at accepted session boundaries, including off-grid boundaries such as 09:14.
For each timed step `i` and eligible free segment `g=[a,b)` create:

- `x_ig` in {0,1}: use this optional interval;
- integer start `s_ig`, end `e_ig`, and allocated minutes `d_ig`;
- `e_ig = s_ig + d_ig`, with `a <= s_ig <= e_ig <= b`;
- `x_ig=0 => d_ig=0`; `x_ig=1 => 1 <= d_ig <= min(b-a, remaining_i)`.

Clip `b` to the step's exact deadline where appropriate. Add `NoOverlap` per day,
`sum_g d_ig <= remaining_i`, and `sum_{i,g on day} d_ig <= max(0, budget-done)`.
One interval per step per segment bounds the model size. Instances with more than
12,000 potential step/segment pairs use the greedy fallback. This is a restricted
interval model; an optimal result proves optimality for this model and horizon,
not every possible real-world study arrangement.

For each accepted session, a preservation Boolean can be true only if the same
step fills every segment covering that exact interval. Its boundaries are kept
when reconstructing slots, so unchanged session IDs can survive approval. Adjacent
same-step intervals are coalesced except at preserved session boundaries.

For a dependency `parent -> child`, introduce task activity and task first/last
times. If the child has any planned minutes, every pending timed parent step must
be fully allocated and `first_child >= last_parent`. Actual completed prerequisites
need no new interval. The independent validator checks full prerequisite allocation
and ordering again without relying on the solver's variables.

## Goal objectives

The engine maximizes three objective levels in sequence. It fixes a level's value
only after CP-SAT proves that level optimal. This makes the trade-off order explicit
and avoids choosing arbitrary weights across minutes, block counts and daily loads.

Definitions:

- `W = sum d_ig`: total useful minutes.
- `D = sum u_i*d_ig` for work due between today and Sunday, where
  `u_i = 8 - days_until_deadline_i`. Work due today has weight 8; Sunday from
  Monday has weight 2. Undated and later work is considered in the next level.
- `I = sum p_i*d_ig`, with low/medium/high priority weights 1/3/9.
- `K`: exact accepted blocks preserved.
- `F = sum x_ig`: number of selected segment intervals (a fragmentation proxy).
- `P = max_day(done_minutes + planned_minutes)`: peak daily workload.
- `N`: number of candidate intervals. `(N+1)*K-F` makes preserving one more block
  dominate any possible fragmentation difference at that level.

| Goal | First maximize | Then maximize | Then maximize |
| --- | --- | --- | --- |
| Meet my deadlines | D | W | (N+1)K-F |
| Focus on important tasks | I | W | (N+1)K-F |
| Keep my routine | K | W | -F |
| Get as much done as possible | W | K | -F |
| Balance my workload | W | -P | -F |

The priority weights express an explicit preference, not a claim that high-priority
minutes have objectively nine times the value. A sufficiently large amount of low
priority work can outweigh a small high priority amount. The balance goal protects
total work before reducing the peak; it does not intentionally discard work to
achieve a flatter graph. Standard deviation is reported as a descriptive metric,
not claimed to be the optimized balance objective. Coalescing can reduce the final
block count below `F`. Small positive sessions remain valid for legacy compatibility;
there is no enforced Pomodoro length or automatic break requirement.

## Search limits and fallback

The UI grants two seconds of solver search per preview, shared across three levels.
Each level gets the remaining time divided by remaining levels. Building the model,
validating and importing OR-Tools are additional overhead. Comparisons compute only
on request and store at most five goal previews per current input snapshot in the
user's Streamlit session. Inputs and timestamps are identical across compared goals.

The greedy proposal seeds the initial search. Proven incumbents seed subsequent
levels. A returned schedule is compared to the greedy baseline using the same
lexicographic objective units; a worse incumbent is replaced with the baseline.
This guard matters on short searches: the first benchmark during development
returned poor incumbents on larger examples before hints and the guard were added.

- `OPTIMAL`: all three objective levels proved optimal.
- `FEASIBLE`: a validated incumbent exists, but not all levels were proved. The
  previous incumbent survives a later search returning `UNKNOWN`.
- `UNKNOWN`, `INFEASIBLE`, `MODEL_INVALID`, `ERROR`, `UNAVAILABLE`, `SIZE_LIMIT`:
  return a validated greedy fallback with a clear message/status.
- `BASELINE_BETTER`: search found a plan but the baseline scores better for the goal.

The solver uses one worker and seed 20875. Wall-time stopping still depends on the
machine and system load. Reproducible input and seed do not guarantee bit-identical
incumbents or runtime on different machines. If OR-Tools is absent, core scheduling
continues with the greedy strategy. Its fallback does not implement all five goals.

## Dependencies and persistence

The additive `task_dependencies(task_id, prerequisite_id)` table uses a composite
primary key, a self-edge check and foreign keys with delete cascades. Editing the
set runs under `BEGIN IMMEDIATE`; missing IDs and cycles roll back the whole edit.
An iterative topological traversal avoids recursion limits. Deleting a task removes
its incident edges; dependencies are not automatically rewired to its parents.

The snapshot includes the dependency relation and all task completion states,
including tasks without steps. Dependency changes enter the existing fingerprint
and invalidate previews and Undo. Approval independently validates precedence in
the same transaction as the fingerprint check. Undo also rejects a previously saved
plan that became invalid after dependencies were introduced.

Actual prerequisite readiness means an explicitly completed parent, or represented
timed steps with zero remaining minutes and every checklist item checked. A pending
task with only checklists needs explicit completion. Reserving time changes none of
these facts. Recording a dependent session as done requires actual prerequisite
readiness; partially completing a prerequisite leaves that gate closed. Manual task
and progress edits remain explicit user statements about work, not scheduler writes.

The greedy baseline now schedules in topological order. For tasks without
dependencies its date-first ordering remains intact. Both engines and approval
validation now reserve completed calendar intervals; a pre-existing regression
test that reused a completed interval was corrected to expect a shortfall instead.

## Conflicts and comparison

`conflict_analysis.py` sums free time before each task's deadline after subtracting
fixed/completed blocks and applying daily limits. This is an **upper bound** for that
task: it ignores competition and dependency ordering. A task estimate greater than
that bound proves a calendar-capacity shortage of at least the difference. Otherwise,
the panel reports the selected proposal's shortfall without claiming infeasibility.
Suggested extra minutes are calculated from unused in-window capacity limited by
the daily budget, or free out-of-window time within 08:00–22:00 and the remaining
budget. The wording says “may help”, not that changing a setting guarantees a plan.

The new goal selector replaces the two strategy buttons: routine corresponds to
minimal change and throughput corresponds to finding more time. The old strategies
remain callable baselines; the quick lost-time simulation is explicitly labelled
as the original heuristic. Before/After, manual preview adjustments and explicit
approval are retained. Adjusted proposals are revalidated and their displayed
metrics are recalculated. Alternative-goal table rows describe the generated plans.

## Files and review

`optimizer.py` owns search; `dependencies.py` owns graph/precedence rules;
`advanced_planner.py` retains the baseline and independent approval validator;
`advanced_repository.py` owns additive storage and transactions; `planning_insights.py`
provides shared metrics; `conflict_analysis.py` calculates bounds. The calendar uses
`views/goal_preview.py`; task details in `views/home.py` provide dependency editing.
The theme, navigation and Windows desktop launcher were not redesigned.

See [OPTIMIZER_EVALUATION.md](OPTIMIZER_EVALUATION.md) for measurements and checks.
The solver status semantics follow the [official CP-SAT documentation](https://developers.google.com/optimization/cp/cp_solver).

From this worktree, review with synthetic data (the generator refuses to overwrite):

```powershell
.\.venv\Scripts\python.exe -m scripts.create_optimizer_demo --output data/optimizer-demo.db
$env:WORKSPACE_DB_PATH = Join-Path $PWD 'data/optimizer-demo.db'
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open Calendar → Rescue my week, choose a goal, generate and compare. Approve only
to save the selected preview; test Undo afterward. In Tasks → Details → Prerequisites,
edit the research/write relation. Clear the environment override when finished:
`Remove-Item Env:WORKSPACE_DB_PATH`. No personal database is needed for this review.

No automated test is a manual Windows desktop/pixel review. Browser rendering and
desktop launcher interactions still need a human check before submission.
