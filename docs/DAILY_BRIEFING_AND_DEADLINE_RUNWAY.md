# Home briefing and upcoming deadlines

Home is meant to answer two practical questions: **what matters today?** and **what's coming up?** These panels use saved local data rather than a chatbot or a separate online service.

## Daily briefing

The briefing summarizes today's agenda and upcoming work. It reads the saved events, study sessions, and tasks; viewing it doesn't complete tasks or accept a new schedule.

## What's due next

The deadline list can show the next **7, 14, or 30 days**. It initially displays three items, with an option to see more. The list highlights the task's priority and deadline alongside relevant progress or study-time information.

For work represented by timed steps, remaining work means actual **unfinished minutes**, not booked calendar time. A future reserved session doesn't subtract minutes until progress is recorded. Available capacity is shared across tasks, so a simple estimate isn't proof that every deadline can be met.

The planner still handles feasibility and conflicts. Home is a quick overview, not a second scheduling engine.

Relevant code: `workspace/views/home_briefing.py`, `workspace/home_view_logic.py`, and `workspace/views/home.py`.
