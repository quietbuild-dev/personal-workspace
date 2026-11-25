"""Personal Workspace entry point: shared theme and navigation only."""

import streamlit as st

from workspace.theme import apply_theme

st.set_page_config(
    page_title="Personal Workspace",
    page_icon=":material/event_available:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

apply_theme()

# Keep the simple everyday pages prominent, with original advanced controls
# available under one additional menu. No legacy setting is removed.
page = st.navigation(
    {
        "": [
            st.Page("workspace/views/home.py", title="Home", default=True, icon=":material/home:"),
            st.Page("workspace/views/week.py", title="Calendar", icon=":material/calendar_month:"),
            st.Page("workspace/views/task_board.py", title="Tasks", icon=":material/checklist:"),
            st.Page("workspace/views/settings.py", title="Settings", icon=":material/tune:"),
        ],
        "Advanced": [
            st.Page(
                "workspace/views/tasks.py",
                title="Detailed Task Editor",
                icon=":material/tune:",
            ),
            st.Page(
                "workspace/views/planner.py",
                title="Advanced Planning",
                icon=":material/settings:",
            ),
        ],
    },
    position="top",
)
page.run()
