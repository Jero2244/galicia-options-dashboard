"""GGAL option analytics. Run with: conda run -n py4fi python -m streamlit run app.py"""
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

from dashboard_ui import run

st.set_page_config(page_title="Galicia | Options", page_icon=":material/show_chart:", layout="wide")
load_dotenv(Path(__file__).with_name(".env"))
run()
