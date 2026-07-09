from __future__ import annotations

import json
import time
from html import escape
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from services.image_reviewer import ImageReviewResult, review_image
from services.rewriter import (
    RewriteChange,
    build_rewrite_changes,
    build_rewrite_status_note,
    rewrite_all,
)
from services.rule_checker import (
    Finding,
    build_highlighted_text,
    build_risk_detail_rows,
    build_risk_summary,
    build_safe_term_hits,
    check_text,
    load_rules,
)


BASE_DIR = Path(__file__).resolve().parent
RULE_PATH = BASE_DIR / "data" / "rules.json"


@st.cache_data
def get_rules():
    return load_rules(RULE_PATH)


def reset_review() -> None:
    st.session_state["title_input"] = ""
    st.session_state["body_input"] = ""
    st.session_state["image_text_input"] = ""
    st.session_state["review_started"] = False
    st.session_state["is_reviewing"] = False
    st.session_state["uploader_key"] = st.session_state.get("uploader_key", 0) + 1


def get_risk_level(findings: list[Finding]) -> tuple[str, str, str]:
    if not findings:
        return "低风险", "未命中当前规则库疑似风险词。", "risk-low"

    high_count = sum(1 for item in findings if item.severity == "high")
    if high_count:
        return "高风险", build_risk_summary(findings), "risk-high"

    return "中风险", build_risk_summary(findings), "risk-mid"


def build_review_text(
    findings: list[Finding],
    rewritten_title: str,
    rewritten_body: str,
) -> str:
    finding_lines: list[str] = []
    seen_findings: set[tuple[str, str, str]] = set()
    for item in findings:
        suggestion = item.suggestion or "建议删除、弱化或重新表述"
        finding_key = (item.term, suggestion, item.reason)
        if finding_key in seen_findings:
            continue
        seen_findings.add(finding_key)
        finding_lines.append(
            f"- 原词：{item.term}｜建议：{suggestion}｜原因：{item.reason}"
        )

    if not finding_lines:
        finding_lines = ["- 未命中当前规则库中的疑似风险词"]

    return "\n".join(
        [
            "【审核意见】",
            "1. 疑似风险词：",
            *finding_lines,
            "",
            "2. 建议改写标题：",
            rewritten_title,
            "",
            "3. 建议改写正文：",
            rewritten_body,
        ]
    )


def render_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: #f6f7fb;
            color: #111827;
        }
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 1280px;
        }
        .hero {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 24px 28px;
            margin-bottom: 18px;
            box-shadow: 0 10px 30px rgba(15, 23, 42, 0.05);
        }
        .hero h1 {
            margin: 0;
            font-size: 34px;
            line-height: 1.15;
            color: #111827;
        }
        .hero p {
            margin: 8px 0 0;
            color: #4b5563;
            font-size: 16px;
        }
        .notice {
            margin-top: 14px;
            padding: 10px 12px;
            border-radius: 8px;
            background: #f9fafb;
            border: 1px solid #e5e7eb;
            color: #374151;
        }
        .section-card {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 10px;
            padding: 18px;
            margin-bottom: 14px;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
        }
        .section-card h3 {
            margin: 0 0 12px;
            font-size: 18px;
            color: #111827;
        }
        .risk-badge {
            display: inline-block;
            border-radius: 999px;
            padding: 6px 12px;
            font-weight: 700;
            margin-bottom: 8px;
        }
        .risk-high {
            background: #fef2f2;
            color: #b91c1c;
            border: 1px solid #fecaca;
        }
        .risk-mid {
            background: #fffbeb;
            color: #b45309;
            border: 1px solid #fde68a;
        }
        .risk-low {
            background: #ecfdf5;
            color: #047857;
            border: 1px solid #a7f3d0;
        }
        .highlighted-original {
            padding: 14px;
            border-radius: 8px;
            border: 1px solid #e5e7eb;
            background: #ffffff;
            line-height: 1.9;
            white-space: normal;
            word-break: break-word;
        }
        .highlighted-label {
            margin: 10px 0 6px;
            color: #374151;
            font-weight: 700;
        }
        .risk-highlight {
            display: inline;
            padding: 2px 5px;
            border-radius: 5px;
            background: #fecaca;
            color: #991b1b;
            font-weight: 700;
        }
        .rewrite-diff {
            padding: 14px;
            border-radius: 8px;
            border: 1px solid #e5e7eb;
            background: #ffffff;
            line-height: 2;
            word-break: break-word;
            margin: 6px 0 12px;
        }
        .diff-delete {
            padding: 2px 4px;
            border-radius: 5px;
            background: #fee2e2;
            color: #991b1b;
            text-decoration: line-through;
            font-weight: 700;
        }
        .diff-insert {
            padding: 2px 5px;
            border-radius: 5px;
            background: #bbf7d0;
            color: #166534;
            font-weight: 700;
            margin-left: 3px;
        }
        .change-reason {
            margin: 4px 0;
            color: #374151;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_copy_buttons(
    rewritten_title: str,
    rewritten_body: str,
    review_text: str,
) -> None:
    copy_items = [
        ("copy-title", "复制改写标题", rewritten_title, "改写标题已复制"),
        ("copy-body", "复制改写正文", rewritten_body, "改写正文已复制"),
        ("copy-review", "复制完整审核意见", review_text, "完整审核意见已复制"),
    ]
    buttons_html = "\n".join(
        f"""
        <button class="copy-button" id="{button_id}">
            {label}
        </button>
        """
        for button_id, label, _, _ in copy_items
    )
    copy_payload = json.dumps(
        {
            button_id: {"text": text, "status": status}
            for button_id, _, text, status in copy_items
        },
        ensure_ascii=False,
    )
    components.html(
        f"""
        <style>
        .copy-button {{
            width: 100%;
            height: 40px;
            border: 0;
            border-radius: 8px;
            background: #111827;
            color: #ffffff;
            font-size: 15px;
            cursor: pointer;
            margin-bottom: 8px;
        }}
        .copy-button:hover {{
            background: #1f2937;
        }}
        </style>
        {buttons_html}
        <div id="copy-status" style="
            margin-top: 2px;
            color: #047857;
            font-size: 13px;
            font-family: sans-serif;
        "></div>
        <script>
        const status = document.getElementById("copy-status");
        const copyPayload = {copy_payload};
        Object.entries(copyPayload).forEach(([buttonId, payload]) => {{
            const button = document.getElementById(buttonId);
            button.addEventListener("click", async () => {{
                await navigator.clipboard.writeText(payload.text);
                status.textContent = payload.status;
                setTimeout(() => status.textContent = "", 1800);
            }});
        }});
        </script>
        """,
        height=158,
    )


def build_rewrite_diff_html(text: str, findings: list[Finding], position: str) -> str:
    rewrite_findings = sorted(
        [
            item
            for item in findings
            if item.position == position and item.suggestion
        ],
        key=lambda item: item.start,
    )
    if not rewrite_findings:
        return escape(text or "无").replace("\n", "<br>")

    fragments: list[str] = []
    cursor = 0
    for finding in rewrite_findings:
        if finding.start < cursor:
            continue

        fragments.append(escape(text[cursor:finding.start]))
        fragments.append(
            '<span class="diff-delete">'
            f"{escape(text[finding.start:finding.end])}"
            "</span>"
        )
        fragments.append(
            '<span class="diff-insert">'
            f"{escape(finding.suggestion)}"
            "</span>"
        )
        cursor = finding.end

    fragments.append(escape(text[cursor:]))
    return "".join(fragments).replace("\n", "<br>")


def render_change_reasons(changes: list[RewriteChange], empty_text: str) -> None:
    if not changes:
        st.caption(empty_text)
        return

    for change in changes:
        st.markdown(
            f"""
            <div class="change-reason">
                {escape(change.original)} → {escape(change.replacement)}<br>
                原因：{escape(change.reason)}
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_rewrite_changes(
    title: str,
    body: str,
    findings: list[Finding],
    title_changes: list[RewriteChange],
    body_changes: list[RewriteChange],
) -> None:
    title_diff = build_rewrite_diff_html(title, findings, "标题")
    body_diff = build_rewrite_diff_html(body, findings, "正文")

    st.markdown("#### 【修改记录】")

    st.markdown("**标题：**")
    st.markdown(
        f'<div class="rewrite-diff">{title_diff}</div>',
        unsafe_allow_html=True,
    )
    render_change_reasons(title_changes, "标题未发生规则替换。")

    st.markdown("**正文：**")
    st.markdown(
        f'<div class="rewrite-diff">{body_diff}</div>',
        unsafe_allow_html=True,
    )
    render_change_reasons(body_changes, "正文未发生规则替换。")


def render_image_review(image_review: ImageReviewResult, has_image: bool) -> None:
    if not has_image:
        st.info("未上传图片。")
        return

    st.caption("当前版本支持手动录入图片文字进行审核，OCR 自动识别将在后续版本接入。")

    if not image_review["enabled"]:
        st.info("已上传图片，但尚未输入图片文字。")
        return

    st.markdown("**图片文字**")
    st.text_area(
        "已审核的图片文字",
        value=image_review["image_text"],
        height=120,
        disabled=True,
    )

    if image_review["risk_items"]:
        st.warning("图片发现风险：")
        st.dataframe(
            [
                {
                    "风险词": item["word"],
                    "建议替换": item["suggestion"],
                    "原因": item["reason"],
                }
                for item in image_review["risk_items"]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success("图片未发现风险。")


def render_safe_term_hits(safe_terms: list[str]) -> None:
    if not safe_terms:
        st.info("未明显命中可用卖点词。")
        return

    st.write("命中的可用卖点词：")
    for term in safe_terms:
        st.write(f"- {term}")


def render_review_loading(progress_placeholder, completion_placeholder) -> None:
    review_steps = [
        "🤖 AI正在分析标题...",
        "🤖 AI正在分析正文...",
        "🤖 AI正在分析图片...",
        "🤖 AI正在生成审核建议...",
    ]

    for step in review_steps:
        with progress_placeholder.container():
            with st.spinner(step):
                time.sleep(0.35)
        progress_placeholder.empty()

    completion_placeholder.success("✅ 审核完成")
    time.sleep(2)
    completion_placeholder.empty()


def main() -> None:
    st.set_page_config(
        page_title="NoteGuard AI",
        page_icon=":material/rate_review:",
        layout="wide",
    )
    render_styles()

    if "review_started" not in st.session_state:
        st.session_state["review_started"] = False
    if "uploader_key" not in st.session_state:
        st.session_state["uploader_key"] = 0
    if "is_reviewing" not in st.session_state:
        st.session_state["is_reviewing"] = False

    st.markdown(
        """
        <div class="hero">
            <h1>NoteGuard AI</h1>
            <p>小红书教育内容AI初审助手</p>
            <div class="notice">AI仅提供初审提示，最终以人工审核为准。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    completion_placeholder = st.empty()
    progress_placeholder = st.empty()

    rules = get_rules()

    left, right = st.columns([0.9, 1.1], gap="large")
    with left:
        with st.container(border=True):
            st.markdown("### 输入区")
            title = st.text_input("标题输入", placeholder="请输入小红书标题", key="title_input")
            body = st.text_area(
                "正文/脚本输入",
                placeholder="请输入正文、视频脚本或封面文案",
                height=240,
                key="body_input",
            )
            uploaded_image = st.file_uploader(
                "图片上传与预览",
                type=["png", "jpg", "jpeg", "webp"],
                accept_multiple_files=False,
                key=f"image_upload_{st.session_state['uploader_key']}",
            )

            if uploaded_image:
                image_bytes = uploaded_image.getvalue()
                st.image(image_bytes, caption="图片预览", use_container_width=True)
                st.text_area(
                    "手动输入图片中的文字",
                    placeholder="请把封面图、海报图中的文字复制或手动输入到这里",
                    height=120,
                    key="image_text_input",
                )

            review_button_slot = st.empty()
            start_review = review_button_slot.button(
                "开始审核",
                type="primary",
                use_container_width=True,
                disabled=st.session_state["is_reviewing"],
                key="start_review_button",
            )
            if start_review:
                st.session_state["is_reviewing"] = True
                st.session_state["review_started"] = True
                review_button_slot.button(
                    "正在审核...",
                    type="primary",
                    use_container_width=True,
                    disabled=True,
                    key="reviewing_button",
                )
                render_review_loading(progress_placeholder, completion_placeholder)
                st.session_state["is_reviewing"] = False

            st.button("清空并审核下一条", use_container_width=True, on_click=reset_review)

    with right:
        if not st.session_state["review_started"]:
            with st.container(border=True):
                st.markdown("### 审核结果")
                st.info("输入标题或正文后，点击“开始审核”查看完整审核结果。")
            return

        image_text = st.session_state.get("image_text_input", "")

        if not title.strip() and not body.strip() and not uploaded_image:
            with st.container(border=True):
                st.markdown("### 审核结果")
                st.warning("请先输入标题、正文或上传图片。")
            return

        findings = check_text(title=title, body=body, rules=rules)
        rewrite_result = rewrite_all(title, body, findings)
        rewritten_title = rewrite_result.title
        rewritten_body = rewrite_result.body
        title_changes = build_rewrite_changes(findings, "标题")
        body_changes = build_rewrite_changes(findings, "正文")
        risk_level, risk_summary, risk_class = get_risk_level(findings)
        review_text = build_review_text(
            findings=findings,
            rewritten_title=rewritten_title,
            rewritten_body=rewritten_body,
        )
        highlighted_title = build_highlighted_text(title, findings, "标题")
        highlighted_body = build_highlighted_text(body, findings, "正文")
        risk_detail_rows = build_risk_detail_rows(findings)
        image_review = review_image(image_text if uploaded_image else "", rules)
        safe_term_hits = build_safe_term_hits(
            title=title,
            body=f"{body}\n{image_text if uploaded_image else ''}",
        )

        with st.container(border=True):
            st.markdown("### ① 整体风险等级")
            st.markdown(
                f'<span class="risk-badge {risk_class}">{risk_level}</span>',
                unsafe_allow_html=True,
            )
            st.write(risk_summary)

        with st.container(border=True):
            st.markdown("### ② 卖点提示")
            render_safe_term_hits(safe_term_hits)

        with st.container(border=True):
            st.markdown("### ③ 高亮后的原文")
            if title.strip():
                st.markdown('<div class="highlighted-label">标题</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="highlighted-original">{highlighted_title}</div>',
                    unsafe_allow_html=True,
                )
            if body.strip():
                st.markdown('<div class="highlighted-label">正文</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="highlighted-original">{highlighted_body}</div>',
                    unsafe_allow_html=True,
                )
            if not findings:
                st.caption("未命中风险词，原文无需高亮。")

        with st.container(border=True):
            st.markdown("### ④ 图片审核")
            render_image_review(image_review, uploaded_image is not None)

        with st.container(border=True):
            st.markdown("### ⑤ 风险详情")
            if risk_detail_rows:
                st.dataframe(risk_detail_rows, use_container_width=True, hide_index=True)
            else:
                st.success("未命中当前规则库中的疑似风险词。")

        with st.container(border=True):
            st.markdown("### ⑥ AI改写建议")
            st.caption(
                build_rewrite_status_note(
                    findings,
                    source=rewrite_result.source,
                    error=rewrite_result.error,
                )
            )
            st.text_input("改写后标题", value=rewritten_title)
            st.text_area("改写后正文", value=rewritten_body, height=170)
            render_rewrite_changes(title, body, findings, title_changes, body_changes)
            render_copy_buttons(rewritten_title, rewritten_body, review_text)


if __name__ == "__main__":
    main()
