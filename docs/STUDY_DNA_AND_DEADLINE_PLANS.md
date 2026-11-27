# Personalization and deadline planning

A timetable shouldn't assume everyone studies the same way. **Settings** stores a small local study profile, while **Calendar** provides the concrete hours available on each day.

## Preferences

The profile covers when the user focuses best, preferred session length, whether study should be spread out or concentrated, and how flexible existing plans can be. Preferred breaks are also configurable. These are mostly **soft preferences**: a deadline, fixed event, or unavailable hour still takes precedence.

Study profiles are stored in the active SQLite database. They're not accounts, and they don't sync between machines. First-run setup can be skipped and preferences can be changed in Settings later.

## Required work and deadlines

Tasks with deadlines can be marked as required or flexible. A proposal that leaves required work due this week unscheduled needs an explicit acknowledgment before it can be approved. The app also surfaces possible deadline shortfalls instead of presenting an incomplete plan as if everything were covered.

**Deadline coverage refers to scheduled study minutes, not a completed assignment.** The planner cannot know whether an essay is finished just because there is time reserved for it. Likewise, a time-bounded search that hasn't found a complete proposal is not a proof that no possible schedule exists.

## How this fits the planner

The selected planning goal and study profile influence which valid timetable is preferred. Available hours, fixed events, deadline boundaries, and task dependencies remain real constraints. All suggested changes require review and approval.

Relevant code: `workspace/study_dna.py`, `workspace/deadline_guarantees.py`, `workspace/views/settings.py`, and `workspace/views/goal_preview.py`.

For the objective definitions, see [Goal-based scheduling](GOAL_BASED_OPTIMIZER.md).
