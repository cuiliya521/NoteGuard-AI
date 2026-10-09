"""Opt-in presentation for the original notes workflow; no AI or persistence engine."""
import hashlib
import json
import os
from html import escape
from pathlib import Path

import streamlit as st

CSS = Path(__file__).resolve().parents[1] / "components" / "notes_forest_paper" / "visual.css"


def enabled() -> bool:
    return os.environ.get("NOTEGUARD_FOREST_PAPER_NOTES", "0") == "1"


def workflow_stage(state) -> int:
    """Match the existing material fingerprint; never present stale analysis as current."""
    title = str(state.get("content_lab_material_title") or "").strip()
    body = str(state.get("content_lab_material_body") or "").strip()
    ocr = str(state.get("content_lab_material_ocr_text") or state.get("content_lab_cover_text") or "").strip()
    image_hash = str(state.get("content_lab_material_image_hash") or "")
    has_material = bool(title or body or ocr or state.get("content_lab_material_image_bytes"))
    fingerprint = hashlib.sha256("\n".join((image_hash, title, body, ocr)).encode()).hexdigest()
    current = (has_material and fingerprint == state.get("content_lab_material_analysis_key")
               and isinstance(state.get("content_lab_material_suggestion"), dict))
    if not current:
        return 2 if has_material else 1
    if state.get("content_lab_material_error"):
        return 2
    return 4 if isinstance(state.get("content_lab_generated_draft"), dict) else 3


class NotesPresentation:
    @staticmethod
    def draft_fingerprint(draft):
        return hashlib.sha256(json.dumps(draft, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    def remember_draft_edits(self, draft, prefix):
        st.session_state["ngnotes_draft_edits"] = {
            "fingerprint": self.draft_fingerprint(draft),
            "title": st.session_state.get(f"{prefix}_selected_title", ""),
            "body": st.session_state.get(f"{prefix}_full_text", ""),
        }

    def restore_draft_edits(self, draft, prefix):
        saved = st.session_state.get("ngnotes_draft_edits", {})
        if saved.get("fingerprint") != self.draft_fingerprint(draft):
            return
        for suffix, value in (("selected_title", saved["title"]), ("full_text", saved["body"])):
            if f"{prefix}_{suffix}" not in st.session_state:
                st.session_state[f"{prefix}_{suffix}"] = value

    def header(self):
        stage = workflow_stage(st.session_state)
        st.markdown('<header class="ngn-heading"><span class="ngn-eyebrow">CONTENT STUDIO / 招生笔记助手</span>'
                    '<h1>从参考素材，到你的招生笔记。</h1>'
                    '<p>看懂内容结构，结合真实业务创作，再交给审核。</p></header>', unsafe_allow_html=True)
        labels = ("导入参考素材", "AI 拆解", "生成招生笔记", "审核发布")
        steps = ''.join(f'<li class="{"current" if n == stage else "previous" if n < stage else "upcoming"}" '
                        f'{"aria-current=step" if n == stage else ""}><span>{n:02}</span>{label}</li>'
                        for n, label in enumerate(labels, 1))
        st.markdown(f'<ol class="ngn-steps" aria-label="当前操作阶段">{steps}</ol>', unsafe_allow_html=True)
        if st.session_state.get("demo_mode"):
            st.info("Demo 模式 · 当前流程沿用原有演示数据与业务规则。")

    def breakdown(self, target_user, pain_point, selling_point, conversion, own_business, own_pain, title_direction):
        st.markdown("## 第二步 · 理解素材，提炼可借鉴的部分")
        with st.container(key="ngnotes-insights"):
            st.markdown(f'<div class="ngn-insights"><div><span>目标人群</span><h3>{escape(target_user)}</h3></div>'
                        f'<div><span>用户问题</span><h3>{escape(pain_point)}</h3></div></div>', unsafe_allow_html=True)
            st.write(f"**继续阅读理由：** {selling_point}")
            st.write(f"**原案例转化方式（仅作参考）：** {conversion}")
        with st.container(key="ngnotes-adaptation"):
            st.markdown("### 用于我的账号")
            st.write(f"围绕 **{own_business}**，先回应 **{own_pain}**。")
            st.write(f"**标题方向：** {title_direction}")
            st.caption("标题方向为现有流程的组合提示，不代表已生成完整笔记。")
            st.caption("现有生成结构：家长痛点 → 老师背书 → 方法证明 → 服务介绍 → 福利转化。这是通用创作结构，并非该素材的 AI 检测结论。")
        st.warning("不要复制原案例的老师身份、学员经历、成绩数据或未经验证的效果描述。")
        st.caption("只复制人群、痛点和内容结构；缺失信息不会被当作事实用于生成。")


def render_notes_forest_paper(profile, render_original):
    st.markdown(f"<style>{CSS.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
    with st.container(key="ngnotes"):
        rail, workspace = st.columns([1, 5.8], gap="large")
        with rail, st.container(key="ngnotes-rail"):
            st.markdown('<div class="ngn-brand">NoteGuard<span>FOREST & PAPER</span></div>', unsafe_allow_html=True)
            st.caption("内容工作空间")
            for label, target in (("内容审核", "协作审核 V2"), ("招生笔记", "招生笔记助手"),
                                  ("历史与资产", "历史与资产"), ("审核规则", "审核规则中心")):
                if st.button(label, key=f"ngnotes-nav-{target}", width="stretch", disabled=target == "招生笔记助手"):
                    st.session_state["forest_navigate_to"] = target
                    st.rerun()
            st.markdown('<div class="ngn-rail-note">创作有依据<br>发布前审核</div>', unsafe_allow_html=True)
        with workspace, st.container(key="ngnotes-workspace"):
            render_original(profile, presentation=NotesPresentation())
