# Try the sample workspace (Windows)

Want to explore the app without creating a week's worth of tasks first? The sample workspace gives you example assignments, fixed commitments, and study sessions in a **separate SQLite database**.

## Quick start

After installing the project, run `Launch Sample Workspace.bat` from the repository folder. It creates or opens a sample workspace using the demo launch path rather than the normal personal database.

If you already have a generated demo database and want to open that specific copy in its own window, use:

```powershell
$demoDb = "$env:USERPROFILE\Downloads\your-sample-workspace.db"
.\.venv\Scripts\python.exe -m scripts.launch_playground_desktop --database "$demoDb"
```

Replace the example path with the **existing absolute path** to your sample `.db` file. Don't point this launcher at your personal database.

## Things to try

1. **Home:** Check today's focus, deadlines, workload, and weekly review.
2. **Tasks:** Create a disposable task, update its progress, and check off subtasks.
3. **Calendar:** Switch between day and week views, inspect booked study time, and try recurring events.
4. **Smart Planner:** Compare planning goals. Check what happens if the week is overloaded, then decide whether to accept a proposal.
5. **Make Room for Life:** Preview a protected interval; cancel it if you only want to see the result.
6. **Calendar import:** If the demo includes an `.ics` file, preview it before importing.

The sample data may contain repeated-looking appointments. The app also supports creating actual recurring events; these are separate from importing external `.ics` recurrence rules.

## Keep your data separate

The sample database is local. Changes you make during a demo stay in that sample file unless you generate a fresh one. The regular desktop shortcut opens your personal workspace.

Don't commit generated `.db` files or `.ics` exports containing personal data to GitHub.
