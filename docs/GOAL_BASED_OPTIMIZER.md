# Goal-based weekly scheduling

Personal Workspace uses **Google OR-Tools CP-SAT** to find study sessions that fit around the user's week. It builds a *proposal*, not an automatic calendar update. The same `RevisionProposal` format is used by our greedy planner, so both approaches go through the same approval and validation process.

## 1. What the planner has to respect

The planner works from the current time to the end of the **Monday–Sunday week**. It schedules the remaining minutes of timed study steps, without counting the parent task's estimate twice. Checklist items have no duration; they can block dependent work, but aren't turned into study sessions.

A proposed schedule must:

- Stay inside the user's available study windows and daily limits. A zero-hour budget means a day off; a day without availability isn't assumed to be free.
- Fit **before each deadline**, never after it. Date-only deadlines allow work until the end of that day.
- Avoid overlaps with other sessions, fixed events, and previously completed study blocks.
- Allocate **no more than the work remaining** on each timed step. Anything not scheduled is shown as a shortfall.
- Respect **task dependencies**: prerequisite work must be planned first, and unchecked prerequisite checklists can block later tasks.

Already accepted but still *planned* sessions may be moved in a proposal. Completed sessions stay occupied. A preview changes neither the saved calendar nor recorded progress.

## 2. The CP-SAT model

We combine the user's available windows, subtract occupied time, and split the remaining space into candidate segments. Existing session boundaries are preserved, including times that don't fall on a five-minute grid.

For each timed step $i$ and eligible segment $g=[a_g,b_g)$, the model creates:

- $x_{ig}\in\{0,1\}$ — whether that step uses the segment.
- $s_{ig}$, $e_{ig}$ and $d_{ig}$ — its start, end and allocated minutes.

The main relationships are:

$$
e_{ig}=s_{ig}+d_{ig}, \qquad a_g\le s_{ig}\le e_{ig}\le b_g
$$

$$
x_{ig}=0\Rightarrow d_{ig}=0, \qquad
x_{ig}=1\Rightarrow 1\le d_{ig}\le\min(b_g-a_g,r_i)
$$

$$
\sum_g d_{ig}\le r_i, \qquad
\sum_{i,g\text{ on day }t}d_{ig}\le\max(0,B_t-C_t)
$$

Here $r_i$ is the step's remaining work, $B_t$ is the day's budget, and $C_t$ is time already completed that day. **`NoOverlap`** keeps study intervals from colliding. Exact deadline limits and dependency ordering add further constraints; the independent validator checks them again before approval.

This is a deliberately bounded interval model, not a claim to represent every possible real-world timetable.

## 3. Five goals, five different trade-offs

All five goals use **the same hard constraints**. What changes is the order of objectives. CP-SAT solves up to three levels in sequence, fixing an earlier level only when its optimum has been proved.

| Symbol | Meaning |
| --- | --- |
| $W$ | Total scheduled study minutes |
| $D$ | Deadline-weighted minutes (weight $8-\text{days until due}$ for work due this week) |
| $I$ | Priority-weighted minutes (low / medium / high: $1/3/9$) |
| $K$ | Existing accepted sessions kept exactly as they were |
| $F$ | Number of selected candidate intervals (a proxy for fragmentation) |
| $P$ | Peak daily workload, including completed work |
| $N$ | Number of candidate intervals |

| Planning goal | First | Second | Third |
| --- | --- | --- | --- |
| Meet my deadlines | $D$ | $W$ | $(N+1)K-F$ |
| Focus on important tasks | $I$ | $W$ | $(N+1)K-F$ |
| Keep my routine | $K$ | $W$ | $-F$ |
| Get as much done as possible | $W$ | $K$ | $-F$ |
| Balance my workload | $W$ | $-P$ | $-F$ |

The order matters. For example, **Balance my workload** first keeps as much work scheduled as possible, *then* reduces the busiest day's load. The weights are our chosen planning preferences, not objective measures of how valuable one task is.

## 4. Search limits and the greedy fallback

Each preview gets **two seconds of CP-SAT search** across the three objective levels. The greedy plan provides a starting solution and a safety check: if the solver's result scores worse for the chosen goal, we keep the greedy plan instead. Problems with more than **12,000 potential step/segment pairs** also use the greedy fallback.

- **`OPTIMAL`** means all three levels were proved optimal for this model.
- **`FEASIBLE`** means a valid plan was found without proving every level optimal.
- If the solver runs out of usable results, is unavailable, or hits a model/size limit, the app uses a **validated greedy proposal** and reports the reason.

The greedy fallback respects scheduling constraints, but doesn't implement all five CP-SAT objectives. A short search also means the app **doesn't guarantee a globally optimal week**.

## 5. Safe replanning

Before saving, the app checks that the tasks, calendar, dependencies, and other planning inputs still match the snapshot used to generate the proposal. It then validates the schedule again **inside the SQLite transaction**. Stale or conflicting proposals are rejected instead of overwriting newer changes.

Dependencies are stored in SQLite and checked for missing tasks or cycles. An accepted plan has a **guarded Undo**, available only while restoring it would still be safe. Task progress is kept separate from scheduling: changing a progress bar doesn't silently delete booked study time.

## Where to go next

- [`workspace/optimizer.py`](../workspace/optimizer.py) — CP-SAT model, search, and objectives.
- [`workspace/advanced_planner.py`](../workspace/advanced_planner.py) — greedy baseline and independent validation.
- [`workspace/advanced_repository.py`](../workspace/advanced_repository.py) — atomic approval, persistence, and Undo.
- [Optimizer evaluation](OPTIMIZER_EVALUATION.md) — test scenarios, benchmark results, and comparisons.

For a hands-on look, open the sample workspace in Calendar, try two different planning goals, compare the previews, and save a plan only when you're happy with it.
