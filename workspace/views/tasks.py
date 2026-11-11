"""Task screen placeholder. The next milestone adds the first persistent task."""

import streamlit as st

st.title("Tasks & Projects")
st.caption("Keep your commitments in one place.")

with st.container(border=True):
    st.subheader("A clear starting point")
    st.write("Task management is coming next.")
    st.caption("Each task will have a title, category, priority, time estimate, and optional deadline.")
