# Energy Today + Smart Task Capture

Both additions use the existing local Streamlit/SQLite workspace. No account, internet service, third-party NLP model, or external health data is required.

## How to use

**Calendar -> How's your energy?** Select Low energy, Normal, or Deep focus, select a day in the current week, and click **Preview focus mode**. The application builds a normal deadline-constrained calendar proposal using the existing planner, then divides the chosen day's study sessions into roughly 25-, 50-, or 90-minute blocks. It retains exactly the same scheduled minutes and their times; there are no inserted breaks or invented free slots. Accepted sessions may be split, and unscheduled work may be proposed in the rest of the current week. Preview shows before and after and stays read-only. The **Apply focus blocks** button saves the proposal through the existing atomic revision and Undo machinery. Save is disabled when current-week deadline work cannot be covered. The selected mode is *not stored* as a long-term preference.

The app does not collect task difficulty ratings, so any "suggested starting focus" is an **optional ordering hint** based on deadline first, then remaining duration as a rough effort proxy. It does not falsely claim to know which subject is difficult; it does not reorder time slots without confirmation.

**Tasks -> Smart capture** Enter a sentence such as `Prepare for my algorithms exam, 6 hours, due December 3, high priority`. Select **Fill task details** to see an editable title, category, duration, deadline and priority. Edit any incorrect inference, then click **Confirm and save task**. This creates a normal quick task (with an optional schedulable step) using the current SQLite schema. Parsing by itself does **not** save anything. The limited offline parser handles named month/day, ISO dates, today/tomorrow, priority keywords and hour/minute durations. It is not a general-purpose natural-language AI.

## Safe installation and source control

Extract the patch archive into a clean feature branch based on current `origin/main`, then run `python scripts/install_energy_and_capture.py`. The installer checks all insertion points and required files *before* writing anything; it makes timestamped backups outside the repository in Downloads and can be rerun. It only edits `workspace/views/week.py` and `workspace/views/task_board.py`, injecting one import and one view call in each. It does not touch existing task data, calendars, theme, optimizer core, or desktop launcher. If source structure has changed, it aborts rather than replacing any file.

Run `ruff check .`, the pytest suite, and `python -m scripts.check_optimizer_ui` in the Windows virtual environment. Test on a disposable database by running `python -m scripts.create_energy_capture_demo --output PATH` and setting `WORKSPACE_DB_PATH=PATH` before starting Streamlit. Remove the environment variable when done; open the desktop launcher after merging to main.

## Boundaries

- The energy feature changes **focus block segmentation**, not available capacity or perceived task difficulty. Adjacent segments do not automatically reserve breaks.
- Energy mode applies to one selected date in the remaining current week, but the baseline planner may also suggest other unscheduled study work.
- The automatic planner remains a heuristic; a failed allocation is not proof that no feasible schedule exists.
- Smart capture uses literal patterns; phrases it does not understand should be edited manually. It does not infer exam dates from the internet.
