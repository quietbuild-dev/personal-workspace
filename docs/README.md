# Technical documentation

The [main README](../README.md) shows what Personal Workspace does and how to run it. Here is the engineering behind it, starting with the planner.

## Start here

| Document | What it's about |
| --- | --- |
| [Optimizer model](GOAL_BASED_OPTIMIZER.md) | The CP-SAT model, hard constraints, five goals, and greedy fallback. |
| [Optimizer evaluation](OPTIMIZER_EVALUATION.md) | Synthetic benchmarks, results, and the trade-offs between goals. |
| [System design](DESIGN.md) | How Streamlit, the planning logic, and SQLite fit together. |
| [Tests](../tests/README.md) | What is checked automatically and how to run the tests. |

## Features worth a closer look

- [Personalization and deadlines](STUDY_DNA_AND_DEADLINE_PLANS.md) — Study preferences and required work.
- [Make Room for Life](MAKE_ROOM_FOR_LIFE.md) — Protect personal time without silently changing the timetable.
- [Schedule Lab, weekly replay, and calendar import](SCHEDULER_REPLAY_CALENDAR_IMPORT.md) — Inspect plans, review recorded work, and import `.ics` commitments.
- [Home briefing and deadlines](DAILY_BRIEFING_AND_DEADLINE_RUNWAY.md) — What the dashboard calculates from saved data.

## Running and reviewing the project

- [Windows desktop launcher](DESKTOP_LAUNCHER.md)
- [Sample workspace](PLAYGROUND_DESKTOP_DEMO.md)
- [Demo walkthrough](DEMO_WALKTHROUGH.md)
- [Testing and evaluation notes](TEST_REPORT.md)

The two CSV files contain measurements from the dated scheduling evaluations. They are evidence for those experiments, not live performance results.
