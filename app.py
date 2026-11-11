"""Streamlit entry point. Run from this folder with: python -m streamlit run app.py."""

import streamlit as st

st.set_page_config(
    page_title="Personal Workspace",
    layout="wide",
    initial_sidebar_state="expanded",
)

with st.sidebar:
    st.title("Workspace")
    st.caption("A little clarity for your week.")

page = st.navigation(
    [
        st.Page("workspace/views/dashboard.py", title="Dashboard", default=True),
        st.Page("workspace/views/tasks.py", title="Tasks & Projects"),
        st.Page("workspace/views/planner.py", title="Smart Planner"),
    ]
)
page.run()
