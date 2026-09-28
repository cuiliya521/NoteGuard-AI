"""Streamlit presentation for the V2 human-in-the-loop workflow."""
from __future__ import annotations

from dataclasses import replace
import streamlit as st

from services.workflow_ai_v2 import make_draft, review_semantics
from services.workflow_v2 import WorkflowState, decide_workflow, start_workflow


EXAMPLE_TITLE = "30天保证提分50分！初二数学必看"
EXAMPLE_BODY = "初二数学线上1v1陪练，保证每位学员一个月提高50分。\n我们会结合错题复盘学习方法。"


def render_workflow_v2(rules: list) -> None:
    st.title("发布前协作审核 · V2 试验版")
    st.caption("规则检查 → 语义分析 → 按风险决定是否生成建议 → 人工确认 → 采用后复检。原文始终保留。")
    st.info("V2 位于独立开发分支；当前公开 V1 Demo 不受影响。无 API Key 时只进行规则检查，并清楚标记语义能力不可用。")
    st.write("**1 · 输入原始内容**")
    if st.button("填入示例内容", key="v2_example"):
        st.session_state["v2_title"] = EXAMPLE_TITLE
        st.session_state["v2_body"] = EXAMPLE_BODY
        st.session_state.pop("v2_state", None)
        st.rerun()
    title = st.text_input("标题", key="v2_title")
    body = st.text_area("正文", key="v2_body", height=180)
    if st.button("开始分析", type="primary", key="v2_start"):
        try:
            with st.spinner("正在检查规则与语义，按结果选择下一步…"):
                next_state = start_workflow(title, body, rules, review_semantics, make_draft)
                st.session_state["v2_state"] = next_state
                st.session_state["v2_candidate_title"] = next_state.suggestion.title if next_state.suggestion else ""
                st.session_state["v2_candidate_body"] = next_state.suggestion.body if next_state.suggestion else ""
        except ValueError as exc:
            st.error(str(exc))
    state: WorkflowState | None = st.session_state.get("v2_state")
    if state is None:
        return
    if (title, body) != (state.original_title, state.original_body):
        st.warning("输入已变化。下方是上一次分析的快照；请重新点击「开始分析」。")
    st.write("**2 · 发现问题与路径决策**")
    st.caption(state.decision_reason)
    if state.semantic.error:
        st.warning(f"语义分析不可用：{state.semantic.error}。不将规则未命中等同于完整通过。")
    if state.original_findings:
        for item in state.original_findings:
            st.write(f"- 规则 · {item.position}「{item.term}」 · {item.reason}（{item.severity}）")
    if state.semantic.issues:
        for item in state.semantic.issues:
            st.write(f"- 语义 · {item.location}「{item.excerpt}」 · {item.reason}（{item.severity}）")
    if state.path == "clear":
        st.success("未触发修改路径，保留原文。" if state.semantic.available else "规则未命中，保留原文；语义尚未验证。")
        return
    if state.path == "suggestion_unavailable":
        st.warning("发现问题，但没有可靠的建议稿。请人工处理后重新分析；原文未被覆盖。")
        return
    st.write("**3 · 原文与建议稿**")
    left, right = st.columns(2)
    with left:
        st.markdown("**原文（始终保留）**")
        st.text(state.original_title)
        st.text(state.original_body)
    with right:
        st.markdown("**建议稿（待人工决定）**")
        st.text(state.suggestion.title)
        st.text(state.suggestion.body)
        st.caption(f"来源：{state.suggestion.source}。{state.suggestion.reason}")
        if state.suggestion.error:
            st.warning("模型建议不可用，已降级为规则替代；请特别核对上下文。")
    if state.path == "needs_decision":
        st.write("**4 · 人工确认**")
        st.caption("可先修改建议稿。采用会复检下方实际确认的文本；保留原文会保留已发现的风险。系统不会自动发布或覆盖原输入。")
        candidate_title = st.text_input("确认版标题（可调整）", key="v2_candidate_title")
        candidate_body = st.text_area("确认版正文（可调整）", key="v2_candidate_body", height=180)
        accept, reject = st.columns(2)
        with accept:
            if st.button("采用修改并复检", type="primary", key="v2_accept"):
                if not (candidate_title.strip() or candidate_body.strip()):
                    st.error("确认版不能为空。")
                else:
                    candidate = replace(state.suggestion, title=candidate_title, body=candidate_body,
                                        reason="用户调整后确认；" + state.suggestion.reason)
                    with st.spinner("正在复检人工确认的内容…"):
                        st.session_state["v2_state"] = decide_workflow(
                            replace(state, suggestion=candidate), "accept", review_semantics)
                    st.rerun()
        with reject:
            if st.button("保留原文", key="v2_reject"):
                st.session_state["v2_state"] = decide_workflow(state, "reject", review_semantics)
                st.rerun()
        return
    st.write("**5 · 最终结果**")
    if state.path == "rejected":
        st.warning("用户保留原文。此前发现的问题仍在，不能标记为通过。")
    elif state.final_findings or (state.final_semantic and state.final_semantic.issues):
        st.error(state.decision_reason)
    elif state.final_semantic and not state.final_semantic.available:
        st.warning(state.decision_reason)
    else:
        st.success(state.decision_reason)
    st.text(state.final_title)
    st.text(state.final_body)
    if state.final_findings:
        for item in state.final_findings:
            st.write(f"- 复检规则仍命中 · {item.position}「{item.term}」 · {item.reason}")
    if state.final_semantic:
        for item in state.final_semantic.issues:
            st.write(f"- 复检语义仍提示 · {item.location}「{item.excerpt}」 · {item.reason}")
        if state.final_semantic.error:
            st.warning(f"语义复检不可用：{state.final_semantic.error}")
