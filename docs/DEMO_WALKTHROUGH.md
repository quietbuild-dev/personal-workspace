# MVP demo walkthrough and manual acceptance checklist

## Preparation (safe demo, 3–4 minute presentation)

1. In PowerShell, enter the **existing** project folder.
2. Run `.\.venv\Scripts\python.exe -m scripts.create_demo_db`. It creates
   `data/demo-workspace.db`, not `data/workspace.db`. If it already exists,
   the script refuses to overwrite it; use a new `--output` filename.
3. Set `$env:WORKSPACE_DB_PATH = (Resolve-Path ".\data\demo-workspace.db").Path`.
4. Run `.\.venv\Scripts\python.exe -m streamlit run app.py` and open its URL.
5. At the end, Ctrl+C and run `Remove-Item Env:WORKSPACE_DB_PATH` to restore the
   default personal DB when you next launch the app.

## Suggested presentation narration

1. **Dashboard:** introduce open tasks, remaining workload and the precise
   cohort for due-week completion. Highlight today's focus and the chart.
2. **Tasks & Projects:** create a short new task with a deadline; demonstrate
   priority and category, filter by status, edit remaining minutes, and mark
   completed. The task persists in SQLite and later views are recalculated.
3. **Planner:** show the current Monday–Sunday dates, enter remaining minutes
   for today and capacities for future dates, save, and explain the allocation
   ranking: deadline first, higher priority on ties, stable ID at the end.
4. **Capacity feedback:** point out the overdue, due-week-shortfall and
   later/undated backlog sections; demonstrate that Sunday capacity cannot
   repair a Thursday deadline if the task did not fit before Thursday.
5. **Return to Dashboard:** confirm metrics and chart reflect the changed task
   and saved availability. Explain that planned work is never auto-completed.
6. **Deletion:** select a disposable demo task, explicitly check confirmation,
   delete it, then show it disappears from plan and dashboard.
7. **Engineering:** mention pure deterministic algorithm, SQLite constraints,
   additive migration, temporary-DB integration tests and Git collaboration.

## Local UI test checklist (must be completed by a student)

- [ ] All three navigation entries load without traceback in a browser.
- [ ] Empty task database: dashboard N/A for due-week completion; planner and
  tasks pages show sensible empty states; chart does not crash.
- [ ] Create a task with/without deadline; invalid title and invalid remaining
  minutes show errors, do not write partial records.
- [ ] Edit several different tasks in sequence; form fields do not leak values
  from one task ID to another.
- [ ] Complete a task, then reopen with positive remaining minutes; verify the
  completed date and status in the database if needed.
- [ ] Change status/category filters, including a filter with no matches;
  selection and task controls remain consistent.
- [ ] Deletion button disabled until its per-task confirmation is checked;
  selecting another task requires new confirmation; deleted task vanishes.
- [ ] Enter today's remaining available minutes and future days' capacity,
  save and refresh; values persist. Past days are disabled.
- [ ] A task spanning two days is split; priority tie-breaking and due-date
  inclusiveness are visible with controlled demo tasks.
- [ ] Overdue work remains unscheduled; deadline shortfalls and later backlog
  are visibly distinct.
- [ ] Dashboard chart has readable labels on normal laptop and narrow width;
  all colors and background match the dark theme.
- [ ] Save task changes, switch pages and refresh/restart app: plan and metrics
  recalculate from saved data, without changing remaining minutes on their own.
- [ ] Run `python -m scripts.check_ui` with local `.venv`; capture results.
- [ ] Test with a copy of an older real database, never the only copy.
- [ ] Test install in a fresh Python 3.12 environment and record dependency
  versions; run full pytest and Ruff checks.

## Collaboration and final Git actions

Do not delete or reset `.git` or `data/workspace.db`. Work on a feature branch.
After applying the update, verifying tests and UI, use:

```powershell
git status -sb
git add README.md workspace tests scripts docs
git commit -m "Complete weekly planner dashboard and task deletion MVP"
git push -u origin feat/mvp-integration
```

Then open a PR on GitHub, have the teammate review it, and merge after checks.
Do not claim the PR or merge has occurred until you actually do it.

Before submission, **confirm the 2026 project requirements and lecturer approval**
on Blackboard/course materials; the public page includes older-year wording.
