# Milestone 1: create and persist a task

This update adds task validation, SQLite storage, a working task form/list, and
tests. Editing, completion, dashboard integration, and scheduling come later.
Earlier setup-only descriptions in README and SETUP_STATUS describe the original
starter; this document records the new milestone.

## Apply the update on Windows

1. Stop the running app with Ctrl+C in its PowerShell window.
2. In your existing project folder, run `git status`. If you have your own
   uncommitted code edits, preserve them before replacing files.
3. Run `git switch -c feat/task-persistence`.
4. Extract the update ZIP into a temporary folder. Copy its `workspace`, `tests`,
   and `docs` folders into your existing project folder (the one with app.py).
   Merge folders and replace workspace/views/tasks.py when prompted. Do not
   replace your entire project folder or create a nested workspace/workspace.
   This update contains no .git, .venv, or database files.
5. Run `.\.venv\Scripts\python.exe -m pytest` from your project folder.
6. Run `.\.venv\Scripts\python.exe -m streamlit run app.py`.

## Acceptance check

Open Tasks & Projects. Save a task titled Prepare SWE demo, category University,
priority High, estimated minutes 90, with the deadline checkbox selected and
date November 26, 2026. Confirm it appears in the table. Stop the app and restart
it using the same command; the task should still be present. Try saving an empty
title and confirm it shows an error without adding a row.

The Dashboard still has its original empty states. Its connection to saved task
data is a later step. The form retains entered values after submission, including
on errors. Press Save again only when you intend to create another task.

## Understand the change

- models.py defines TaskDraft (new input), Task (saved record), and input rules.
- repository.py creates data/workspace.db and owns parameterized SQL operations.
  Each operation closes its connection. Original and remaining minutes start equal.
- views/tasks.py collects input, calls storage, and renders saved records.
- tests/test_tasks.py checks persistence across connections, validation, optional
  deadlines, repeated initialization, text containing SQL characters, stable IDs,
  and database completion constraints using temporary databases.

The database is on your own computer and is excluded by the existing .gitignore.
Sharing the code does not share your personal tasks.

## Validation

Nine tests passed using Python's standard-library unittest, including 14 invalid
input subcases. Python syntax was checked. Streamlit browser behavior and pytest
execution still need to be checked on your computer because the preparation
environment cannot install those dependencies. The tests support both runners.

## Save the milestone after verification

```powershell
git add workspace/models.py workspace/repository.py workspace/views/tasks.py tests/test_tasks.py docs/MILESTONE_1_UPDATE.md
git commit -m "Add task creation and SQLite persistence"
git push -u origin feat/task-persistence
```

Review the branch with your teammate before merging. Next implement task editing
and completion on this same persistence foundation.
