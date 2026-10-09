"""Bidirectional Streamlit custom component for the existing V2 workflow."""
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from services.forest_paper_v2 import REGISTRY

FRONTEND = Path(__file__).resolve().parents[1] / "components" / "forest_paper_v2"
component = components.declare_component("noteguard_forest_paper_v2", path=str(FRONTEND))


def render_forest_paper_v2(rules):
    # No public server or separate HTTP API: Streamlit owns component transport.
    work = st.session_state.get("forest_workspace")
    if work is None:
        work, _ = REGISTRY.acquire(None, rules)
        st.session_state["forest_workspace"] = work
    st.markdown("""<style>
      [data-testid="stMainBlockContainer"]{max-width:none;padding:0 0 0!important}
      [data-testid="stHeader"]{background:transparent}
      [data-testid="stSidebar"]{display:none}
    </style>""", unsafe_allow_html=True)
    event = component(model=work.snapshot(), resume_token=work.token,
                      ack=st.session_state.get("forest_ack", ""),
                      resume_message=st.session_state.get("forest_resume_message", ""),
                      key="forest_paper_component", default=None)
    if not event or not isinstance(event, dict):
        return
    eid = event.get("id")
    if not isinstance(eid, str) or eid == st.session_state.get("forest_ack"):
        return
    if event.get("action") == "navigate":
        pages = {"audit": "协作审核 V2", "notes": "招生笔记助手", "history": "历史与资产", "rules": "审核规则中心"}
        target = pages.get(event.get("page"))
        if target and st.session_state.get("forest_full_app"):
            st.session_state["forest_navigate_to"] = target
        else:
            work.error = "独立验收入口仅运行审核工作台；其他模块请从完整 V2 应用进入。"
    elif event.get("action") == "restore":
        restored, found = REGISTRY.acquire(event.get("token"), rules)
        st.session_state["forest_workspace"] = restored
        st.session_state["forest_resume_message"] = "" if found else (
            "会话已过期或服务重启，旧审核结果未恢复；请重新审核。" if event.get("token") else "")
    else:
        try:
            work.handle(event)
        except ValueError as exc:
            work.error = str(exc)
        except Exception:
            # Provider exception text is never returned to browser or logged.
            work.error = "审核服务未完成本次操作，请重试。"
            if work.final_status == "running":
                work.final_status = "failed"
                work.final_review = None
    st.session_state["forest_ack"] = eid
    st.rerun()
