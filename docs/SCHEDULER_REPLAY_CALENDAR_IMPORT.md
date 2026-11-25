# Schedule Lab, Weekly Replay and Calendar Import

This is an additive update to the local Personal Workspace. It uses the existing Streamlit, SQLite and CP-SAT/greedy scheduling infrastructure. No account, external API, cloud integration or new page is required. Your planner's original optimizer objective functions remain unchanged.

## Schedule Lab — Calendar

Open **Calendar → Schedule Lab · stress test and explain decisions** (current week).

- **Plan health** checks accepted calendar conflicts, estimates currently unreserved work due this week, and flags successive study sessions with less than a ten-minute gap. This is diagnostic; it does not allocate time or assert global feasibility.
- **What if I lose time?** simulates an unavailable window and runs the existing validated optimizer via the Make Room for Life preview function. It shows blocks that leave and enter the proposed schedule, a deadline-preservation verdict, and any fallback message. It NEVER saves the simulated plan. To make the change real, use **Make Room for Life** with a fresh preview and separate approval.
- **Why this session?** shows inputs that materially affect planning (deadline, priority, prerequisites, preferred hours, fixed commitments). These are factual constraints, not a fabricated causal explanation of the solver's internal decision.

Existing accepted time blocks and Undo are unchanged. The optimizer's greedy fallback is not a proof of infeasibility or global optimality. No automatic breaks are inserted; the new health check flags gaps under ten minutes.

## Weekly Replay — Home

Open **Home → Weekly replay · planned vs recorded** and select **Last week** or **This week**. It shows total session bookings **currently retained in the database**, actual minutes marked complete, missed blocks, unfinished blocks and study time grouped by task. The bar measures actual completed time against retained bookings (not guaranteed productivity).

**Honesty about historic data:** before this feature, accepted replanning could replace older planned sessions without an immutable history record. The historical original plan and count of replans are therefore not reconstructible. Replay does not invent those numbers. Choose **Track future plan changes** to opt in to a small local audit log. From that moment onward it counts accepted plans and how many replaced existing blocks. These counts exclude past changes, and they are not the same as every individual session edit. The audit triggers attach to the existing accepted-plan/Undo transaction, including Make Room for Life and energy-mode approvals. Nothing is tracked automatically before you opt in.

## Calendar .ics Import — Calendar

Open **Calendar → Import commitments · .ics file**. Choose an exported `.ics` file from Google Calendar, Apple Calendar or Outlook. Review event times, warnings and eligibility, select events, choose a category, then explicitly import. Nothing is written during the preview. A selected batch is committed in one transaction after rechecking the current calendar fingerprint and conflicts.

Supported: single-day floating-local, UTC and IANA-TZID timed events, plus one-day all-day events. UTC and IANA times are converted to the computer's local timezone. A `tzdata` dependency was added to `requirements.txt` for reliable IANA zones on Windows.

Not supported in this release: recurring `RRULE`/`RECURRENCE-ID`/`RDATE`/`EXDATE`, overnight or multi-day events, and files larger than 1.5 MB or containing more than 200 events. Unsupported events are reported and skipped, never silently assumed to be one-time events. Recurring calendars should be exported as individual occurrences first. Import is one-way; it does not create live sync. Existing events and accepted study sessions cannot be overlapped by imported items. Items with matching UID or exact event details are treated as duplicates; UID receipts are deleted if an imported event is subsequently deleted.

Imported events are normal, editable fixed commitments. They may change study feasibility; any later replanning is separate and requires a preview/approval.

## Demo and rollback

`python -m scripts.create_scheduler_lab_demo --output <new-path>.db` creates a **new, isolated** demo database and a corresponding `.ics` file. This demo includes one completed 55-minute study session last week, future study time and a lecture, plus two importable fixed commitments. Set `WORKSPACE_DB_PATH` to the demo database only in the test terminal before starting Streamlit; clear the variable before opening your real desktop shortcut.

The installer creates timestamped backups of `home.py`, `week.py` and `requirements.txt` in `Downloads/personal-workspace-feature-backups`. The patch does not modify your real database during installation. The optional audit log adds a SQLite table and triggers only after an explicit button click; calendar importing writes only after a separate confirmation. To revert before committing, use `git restore workspace/views/home.py workspace/views/week.py requirements.txt` and remove the new files; do not delete the user's database. Git branches/pull requests are preferred for safe rollback.
