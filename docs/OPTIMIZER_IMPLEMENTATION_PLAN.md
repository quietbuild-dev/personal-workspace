# Goal-based scheduling implementation plan

Work stays on `feat/goal-based-optimizer` in the isolated worktree. Tests and
benchmarks use synthetic snapshots or temporary databases only.

1. Add a pure CP-SAT engine beside `advanced_planner.make_revision`, retaining
   the greedy baseline. Use integer minutes, bounded optional intervals, daily
   budgets, fixed commitments and the existing independent proposal validator.
   Record solver status and fall back safely. Run core correctness tests.
2. Add five objective profiles and a goal selector to Rescue My Week, preserving
   Before/After, explicit transactional approval and guarded Undo. Compare actual
   metrics and test examples where goals choose different schedules.
3. Add a task dependency relation with foreign keys, cycle checks and snapshot
   fingerprinting. Enforce planned precedence without recording completion;
   unchecked checklist prerequisites block downstream planning. Extend both
   schedulers, approval validation and task controls; test migration and chains.
4. Calculate capacity and dependency explanations from the same snapshot, showing
   shortfalls without claiming a heuristic failure proves infeasibility.
5. Run reproducible scenarios for both greedy strategies and all five profiles,
   export CSV, document the model and measured trade-offs, and run lint, formatting,
   regression tests and the Streamlit smoke test.

Architecture inspected: `advanced_planner.py` is pure; `advanced_repository.py`
loads consistent snapshots, hashes inputs, validates approval under BEGIN IMMEDIATE,
retains unchanged row IDs and stores fingerprint-guarded Undo. Quick tasks link to
timed study steps; scheduling does not mark those steps complete. The calendar's
`week.py` owns Rescue previews; `planning_insights.py` currently compares two greedy
strategies. Existing deadlines are hard placement boundaries; retain that contract.
