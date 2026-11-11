# Milestone 2: edit, complete, and reopen tasks

Prerequisite: milestone 1 is merged and your branch is feat/task-editing.
This update uses the existing SQLite schema and preserves your task database.

## Install on Windows

1. Stop Streamlit with Ctrl+C.
2. From your existing project folder, run `git branch --show-current` and
   confirm feat/task-editing. Run `git status` and preserve any of your own
   uncommitted edits before overwriting the updated files.
3. Download task-editing-update.zip, then right-click it and choose Extract All.
4. Copy its workspace, tests, and docs folders into your existing project folder
   containing app.py. Merge the folders and replace existing files when prompted.
   Downloading the archive alone does not install the update.
5. Check that `Test-Path .\tests\test_task_editing.py` returns True.
6. Run `.\.venv\Scripts\python.exe -m pytest`. Expect 21 passed: the original
   nine tests plus twelve editing tests. Seeing only nine means the new test file
   has not been copied to the correct location.
7. Run `.\.venv\Scripts\python.exe -m streamlit run app.py`.

## Browser acceptance walkthrough

Open Tasks & Projects. Your existing task should remain in the table. Below
the table, find Edit a task and select Prepare SWE demo. The task selector
includes its database ID so tasks with identical titles remain distinguishable.

| Action | Expected result |
| --- | --- |
| Change the title to Prepare final SWE demo; set remaining minutes to 60; Save changes. | Same task, updated title, 60 remaining, Pending. |
| Click Mark completed. | Remaining becomes 0, status becomes Completed. |
| Set remaining minutes to 30; Save changes. | Task reopens as Pending with 30 remaining. |
| Restart the app and return to Tasks & Projects. | Updated title and 30 remaining are still present. |
| With estimate 90, try remaining 100; Save changes. | Validation error; the saved table retains 30 remaining. Correct the field to continue. |
| Clear the deadline checkbox; Save changes. | The table shows No deadline. Restore the deadline if desired. |

Test switching between two tasks as well: editing one must leave the other
unchanged. The dashboard is still the original placeholder and is not the place
to check task storage. Deletion and dashboard integration are later milestones.

## How the code works

models.revise_task validates the new details and remaining minutes and returns
a new Task object. The original task is unchanged. Zero remaining means completed;
positive remaining means pending. Completing records a timestamp; editing an
already completed task preserves its timestamp; reopening clears it.

repository.update_task reads the current saved record and updates it in one
transaction. The ID and creation timestamp stay unchanged. Failed validation
rolls back the transaction. The function now accepts:

```python
update_task(db_path, task_id, draft, remaining_minutes) -> Task
```

This is the implemented update contract, superseding the preliminary update_task
signature in DESIGN.md. TaskDraft still describes the editable title, category,
deadline, priority, and total estimate; remaining time is supplied separately.

The task view has a selector outside the edit form. Widgets use task-specific
keys. After a successful write, the view reruns and reloads saved values so the
table and form agree. Invalid submissions keep the entered fields for correction.
Mark completed also saves the edited details currently in the form.

## Verification and limits

All 21 tests passed with Python's standard-library unittest runner; Python syntax
also passed. The tests cover storage across connections, existing data, field
changes, completion/reopening, timestamp preservation, invalid edit rollback,
nonexistent task IDs, and independent edits to tasks with duplicate titles.

Streamlit and pytest are unavailable in the preparation environment, so browser
interaction and execution with pytest must be checked on your computer. No
browser test success is claimed. The tests use temporary databases and do not
modify your personal task data.

The ZIP contains five files only: models.py, repository.py, views/tasks.py,
tests/test_task_editing.py, and this document. Keep the original tests/test_tasks.py.
There is no database, virtual environment, or Git metadata in the archive.

## Commit after checking

```powershell
git add workspace/models.py workspace/repository.py workspace/views/tasks.py tests/test_task_editing.py docs/MILESTONE_2_UPDATE.md
git commit -m "Add task editing completion and reopening"
git push -u origin feat/task-editing
```

Create a pull request for review before merging into main.
