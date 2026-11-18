"""Personal Workspace: Home and Calendar, with advanced controls in-page."""

import streamlit as st

st.set_page_config(
    page_title="Personal Workspace",
    layout="wide",
    initial_sidebar_state="expanded",
)

with st.sidebar:
    st.title("Workspace")
    st.caption("Study and life, in one place.")

page = st.navigation(
    [
        st.Page("workspace/views/home.py", title="Home", default=True),
        st.Page("workspace/views/week.py", title="My Calendar"),
    ]
)
page.run()
