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

# Everyday navigation only. Advanced implementation remains available in source.
page = st.navigation(
    {
        "": [
            st.Page("workspace/views/home.py", title="Home", default=True, icon=":material/home:"),
            st.Page("workspace/views/week.py", title="Calendar", icon=":material/calendar_month:"),
            st.Page("workspace/views/task_board.py", title="Tasks", icon=":material/checklist:"),
            st.Page("workspace/views/settings.py", title="Settings", icon=":material/tune:"),
        ],
    },
    position="top",
)
page.run()
