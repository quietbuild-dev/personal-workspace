# Setup verification — November 11, 2026 (historical starter record)

> This page describes the old setup-only scaffold, not the latest MVP. See
> `TEST_REPORT.md` for the current results.


## Completed in the preparation environment

- Created the project scaffold, documentation, dependency files, and dark theme.
- Parsed all six Python files successfully with Python 3.12.14.
- Parsed both TOML configuration files successfully.
- Initialized a local Git repository on `main` and verified that local databases
  and the virtual environment are ignored. The ZIP omits Git metadata; run the
  README Git commands after extraction. No remote repository was created.

## Not yet verified

The environment could not download packages from the Python Package Index
(HTTP 403). Streamlit, Plotly, pytest, and Ruff were not installed. Therefore
the Streamlit server, navigation, browser appearance, AppTest, pytest, and Ruff
have **not** been run. No dependency lock or claim of runtime compatibility has
been produced from an untested environment.

Run the README setup commands on a student computer, inspect all three screens,
run Ruff, and freeze the installed dependencies after the first successful launch.
Add the first meaningful tests while implementing task validation and persistence.

No feature implementation, test pass count, or GitHub publication is implied by
these syntax/configuration checks.
