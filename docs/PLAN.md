# Project plan — November 11–27, 2026

## Recommendation and feasibility

Proceed with a single-user Streamlit application, SQLite persistence, and a
deterministic daily allocation algorithm. At about 45 combined hours, a good
MVP is plausible if the two students keep the contracts small, integrate early,
and reserve time for correctness and the demonstration. This is an estimate,
not a guarantee. At 30 hours, simplify the interface and cut enhancements; at
60 hours, improve tests, explanations, and polish before adding new features.

The project is stronger than a styled task list because the planner produces a
capacity-constrained allocation, explains what could not fit, and has explicit
correctness properties. The academic claim is reliable engineering, not an
optimal scheduling algorithm or artificial intelligence.

## Course fit: resolve before the feature sprint

The public page for course 20875 is headed 2026–2027 but explicitly says its
content refers to 2025–2026. It mentions lecturer approval of project scope,
practical open-source projects, and an in-class presentation. This supports
checking the proposal early; it does not establish the current assignment rubric.

Obtain the current assignment brief and confirm whether a new standalone app
qualifies, or whether contribution to an existing project is required. Verify
submission files, presentation length, deadline time and timezone, collaboration
rules, and any rules about assistance. Do not assume this plan covers unspecified
grading criteria. November 27 comes from your brief, not the public page.

The attached material mentions a UI screenshot, but the screenshot was not
available for this setup. The current layout follows the written description;
fine visual matching is deferred until the image is supplied.

## Locked MVP

| Requirement | Acceptance condition |
| --- | --- |
| Task management | Create, edit, delete with confirmation, complete, and reopen a task; data survives restart. |
| Task fields | Title, one category label, optional deadline, low/medium/high priority, estimated minutes, and remaining minutes. |
| Availability | Save minutes for each date in the current Monday–Sunday week; past days are not schedulable. Today's number means time still available today. |
| Automatic plan | Distribute incomplete work over today through Sunday; allow a task to span days; respect capacities and valid deadlines. |
| Capacity feedback | Show overdue tasks and unallocated minutes with clear reasons. This is core correctness, not an optional enhancement. |
| Dashboard | Open task count, total remaining work, completion ratio for tasks due this week, today's allocations, upcoming deadlines, one workload chart, and one derived insight. |
| Integration | Saving a task or availability immediately updates the derived plan and dashboard. |
| Engineering | Validation, isolated temporary-database tests, deterministic planner tests, documented setup, and a reproducible demo. |

"Projects" means one category field on tasks, such as University, Personal, or
Work. There is no separate project entity, project lifecycle, or nesting.

No authentication, cloud hosting, calendar integrations, collaboration inside
the app, drag-and-drop, chatbot, recurrence, habits, notifications, streaks,
time-of-day appointments, or optimization solver. No plan-history subsystem.

## Stack decisions

| Choice | Decision and tradeoff |
| --- | --- |
| Python 3.12 | One shared interpreter version. Built-in dataclasses, datetime, and sqlite3 are sufficient. |
| Streamlit | Good fit for the time budget and a Python team. Native navigation, forms, columns, containers, and theme settings keep the UI maintainable. Accept its standard widget structure rather than promise pixel-perfect custom frontend behavior. |
| SQLite | Prefer over JSON: transactions, queries, and explicit constraints suit editing and progress calculations. No database server or ORM. Both students use their own local data. |
| Plotly | Use for one readable daily capacity-versus-allocation chart. No additional charting framework. |
| pytest | Test business behavior separately from UI; use temporary databases for integration tests. |
| Ruff | One small tool for linting and formatting. No extra type-checking framework in this MVP. |
| Git/GitHub | Short feature branches, peer review, early merges, and a test workflow once real tests exist. |

Use supported Streamlit theme options first. Avoid generated CSS class selectors
and extensive HTML overrides. The current scaffold contains no custom CSS.

## How the sections connect

Tasks & Projects owns task editing. Smart Planner owns daily availability and
shows the current allocations. Dashboard summarizes the same saved data and
the same pure planning result. It never keeps a separate copy of task state.

The planner recalculates after changes and when the calendar day changes.
It does not save allocations as another source of truth. At this scale,
recomputing is cheap; persistent plans and cache invalidation would add work.

## UI layout

| Area | Contents |
| --- | --- |
| Sidebar | Working title and only three navigation items. |
| Dashboard header | Page title and current week once real dates are connected. |
| First row | Three quiet metric cards: open tasks, remaining work, due-this-week completion. |
| Main left column | Up to three tasks allocated today; below them, one daily workload chart. |
| Main right column | Upcoming deadlines and one concise insight derived from current data. |
| Task page | Add/edit form, category and status filters, simple list, explicit completion and delete actions. |
| Planner page | Seven daily availability inputs, disabled past dates, allocation list grouped by date, and an unallocated/overdue section. |

Use a nearly black background, dark gray cards, soft white text, muted sage
accent, subtle borders, and generous spacing. Use amber/red only for actionable
deadline or capacity problems. Put text alongside status color. Prefer readable
lists over cramped seven-column task cards on smaller windows. Empty states
explain the next useful action; do not display fictional demo statistics.

## Development schedule

All hours below are **combined person-hours**, including review and integration.
This budget assumes ordinary university workload, not two full-time developers.

| Dates | Deliverable | Student A | Student B | Combined | Exit condition |
| --- | --- | ---: | ---: | ---: | --- |
| Nov 11–12 | Scope, course-fit check, setup, shared contract | 2 | 2 | 4 | Both machines launch the same shell; repository shared; current brief checked. |
| Nov 13–15 | Complete task management and SQLite | 5 | 4 | 9 | Create/edit/delete/complete/reopen survive restart; validation and persistence tests pass. |
| Nov 16–18 | Planning algorithm, availability, core tests | 6 | 4 | 10 | A deterministic allocation works through the UI; capacity and deadline invariants pass. |
| Nov 19–21 | Connected dashboard, metrics, one chart | 3 | 5 | 8 | A change in tasks or availability updates every relevant view. |
| Nov 22–24 | Integration, edge cases, visual refinement | 3.5 | 3.5 | 7 | End-to-end demo works; fixes complete; no new features after Nov 24. |
| Nov 25–26 | README/report, demo data, rehearsal, fresh install | 2 | 3 | 5 | Both can run and explain the project from a clean checkout. |
| Nov 27 | Final check, packaging, submission buffer | 1 | 1 | 2 | Required files submitted before the official cut-off. |
| **Total** | | **22.5** | **22.5** | **45** | |

These are working role labels; the two students can swap them.

- **Student A:** models, validation, repository, planner, and related unit tests.
- **Student B:** Streamlit forms/navigation, dashboard/metric functions, charts,
  UI integration, and related tests.
- **Both:** agree contracts, review each other's work, write documentation for
  their modules, and rehearse explaining the other person's main contribution.

Student B can design forms against the agreed Task contract while Student A
implements persistence. Then Student B connects availability and rendering while
Student A implements the pure planner. Merge the first working path early.

## Highest risks and responses

| Risk | Response |
| --- | --- |
| Course expects contribution to an existing project | Verify the current brief immediately; the public page cannot settle this. |
| UI work absorbs the available time | Keep the native layout. Timebox cosmetic refinement within Nov 22–24. |
| Work already planned is mistaken for work completed | Track remaining minutes explicitly. An allocation is a suggestion and never reduces remaining work automatically. |
| Deadline semantics cause misleading plans | Use calendar dates, an inclusive deadline day, and explicit overdue handling; test today and week boundaries. |
| Stale state after Streamlit reruns | Read saved data after a successful write, use stable widget keys, and recompute derived values; avoid caching mutable task lists. |
| Separate branches drift apart | Agree names and data types first; merge and review small changes daily. |
| New tasks change a progress percentage | Define the metric as the current tasks-due-this-week cohort and label it accurately. It is not a historical productivity score. |

## Scope protection

If time slips, cut category filters, extra insights, secondary charts, and
advanced styling first. Keep the task-category field, the single workload chart,
basic capacity warnings, data persistence, planner correctness, and the demo.

At 30 combined hours, target 3 setup, 8 task management, 7 planning, 4 dashboard,
5 testing/integration, and 3 documentation/demo. Use the starter layout with
minimal cosmetic work and no enhancements. Review feasibility if course
requirements impose additional work.

If all essentials are stable with time left, choose **one** enhancement:
category filtering, richer explanations, or a small FIFO-baseline comparison.
Do not add a new subsystem. The deadline and feature freeze do not move.

## Academic evidence to prepare

1. Link each core requirement to a test or demo step.
2. Explain the planner ordering, constraints, complexity, and failure cases.
3. Show a feasible example, an overloaded example, an overdue task, and a
   replan after completing or shortening work.
4. Explain the choice of SQLite, pure functions, integer minutes, and derived plans.
5. Show relevant tests, peer-reviewed commits, and a fresh-checkout run.
6. State the heuristic's limitations honestly: no optimization guarantee,
   no minimum work-session size, no appointments, and no hidden assumption that
   planned work has actually been done.

An optional FIFO comparison should use identical inputs and measure minutes
allocated before deadlines and unallocated work. Deadline-first is not claimed
to outperform every baseline on every objective. No invented performance gains.

## Sources checked on November 11, 2026

- [Bocconi 20875 public course page](https://didattica.unibocconi.eu/ts/tsn_anteprima.php?IdPag=8228&anno=2027&cod_ins=20875)
  — explicitly carries a prior-year-content warning.
- [Streamlit configuration](https://docs.streamlit.io/develop/api-reference/configuration/config.toml)
  — project-local theme configuration.
- [Streamlit navigation](https://docs.streamlit.io/develop/api-reference/navigation)
  — pages and the application entry point.
- [Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest)
  — behavior checks without relying only on manual browser inspection.
