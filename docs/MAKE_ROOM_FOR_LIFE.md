# Make Room for Life

Sometimes an evening should stay free. **Make Room for Life** lets you protect a personal time interval and preview what would happen to study blocks already on your calendar.

The tool treats the proposed personal event as unavailable time and asks the existing planner for an alternative schedule. The preview shows what would stay, move, or no longer fit. It does not shift lectures or other fixed commitments to make space.

## Safe by design

- **Preview first:** generating or dismissing the proposal doesn't write to SQLite.
- **Respect constraints:** the proposed time must be valid for the current week and can't overlap fixed commitments.
- **Check deadlines:** changes that would violate required deadline coverage are not accepted as valid alternatives.
- **Approve explicitly:** the personal event and its accompanying study-plan changes are saved together in one transaction.
- **Undo carefully:** Undo is available only if the saved calendar still matches the approved state. It restores the plan and removes the protected event together.

This is a **current-week, one-off** tool. It doesn't automatically reschedule future weeks or create recurring protected periods. A proposed study slot is not recorded as completed work.

Relevant code: `workspace/life_planning.py`, `workspace/views/life_time.py`, and `tests/test_life_planning.py`.
