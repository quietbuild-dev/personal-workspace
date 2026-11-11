"""Dashboard layout and honest empty states for the initial scaffold."""

import streamlit as st

st.title("Your week, at a glance")
st.caption("Make room for what matters.")

for column, label in zip(
    st.columns(3),
    ("Open tasks", "Remaining work", "Due this week · completed"),
    strict=True,
):
    with column:
        with st.container(border=True):
            st.metric(label, "—")

left, right = st.columns([2, 1], gap="large")
with left:
    with st.container(border=True):
        st.subheader("Today’s focus")
        st.write("Your next steps will appear here once you add tasks and plan your week.")
        st.page_link("workspace/views/tasks.py", label="Go to tasks")
    with st.container(border=True):
        st.subheader("Weekly workload")
        st.caption("Set your availability to see how your work fits across the week.")
        st.page_link("workspace/views/planner.py", label="Open planner")

with right:
    with st.container(border=True):
        st.subheader("Upcoming deadlines")
        st.caption("No deadlines to show yet.")
    with st.container(border=True):
        st.subheader("Planning insight")
        st.caption("Add tasks and availability to find out whether your week has enough room.")
