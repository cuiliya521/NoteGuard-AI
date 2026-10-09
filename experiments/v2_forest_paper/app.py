"""Run from repository root: streamlit run experiments/v2_forest_paper/app.py."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import streamlit as st
from services.rule_checker import load_rules, load_rule_records
from services.forest_paper_ui_v2 import render_forest_paper_v2

st.set_page_config(page_title="NoteGuard AI · Forest & Paper V2", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown("<style>[data-testid='stSidebar'],[data-testid='stHeader']{display:none}</style>",
            unsafe_allow_html=True)
rule_path = ROOT / "data" / "rules.json"
if not rule_path.is_file():
    st.error("规则库缺失，不能开始审核。")
    st.stop()
load_rule_records(rule_path)
rules = load_rules(rule_path)
if not rules:
    st.error("有效规则库为空，不能开始审核。")
    st.stop()
render_forest_paper_v2(rules)
