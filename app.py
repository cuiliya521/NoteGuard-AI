from __future__ import annotations

from dataclasses import asdict
import json
import hashlib
import inspect
import time
from html import escape
from pathlib import Path
from uuid import uuid4

import streamlit as st
import streamlit.components.v1 as components

from services import note_generator as note_generator_service
from services.history import (
    create_history_record,
    load_recent_history,
    upsert_history_record,
)
from services.creator_profile import (
    PROFILE_FIELDS,
    load_creator_profile,
    save_creator_profile,
)
from services.image_reviewer import ImageReviewResult, review_image
from services.image_ocr import extract_text_details, extract_text_with_status, get_available_ocr_engine
from services.image_input import (
    ImageInputError,
    normalize_image_input,
    store_image_payload,
)
from services.clipboard_image import (
    PASTE_UNAVAILABLE_MESSAGE,
    extract_pasted_image,
    load_paste_image_button,
    log_paste_component_error,
)
from services.link_importer import (
    LinkImportError,
    download_public_image,
    import_public_page,
)
from services.note_generator import (
    CONTENT_DIRECTIONS,
    GENERATION_MODES,
    IMAGE_GENERATION_STRUCTURE,
    LENGTH_RANGES,
    build_image_source_context,
    build_generation_request_key,
    build_rule_constraints,
    can_generate_note,
    finalize_generated_note,
    get_structure_guidance,
)
from services.ocr_postprocessor import correct_ocr_text
from services.llm import (
    analyze_cover,
    analyze_note_image_source,
    analyze_viral_examples_for_generation,
    analyze_viral_image,
    analyze_viral_note,
    generate_pre_publish_report,
    generate_title_candidates,
    generate_xiaohongshu_note,
    get_last_error,
)
from services.rewriter import (
    FormatPreservingChange,
    LineReviewItem,
    RewriteChange,
    TitleCandidateReview,
    build_rewrite_changes,
    build_format_preserving_changes,
    build_line_review_items,
    build_rewrite_status_note,
    build_supplier_feedback,
    get_line_review_progress,
    rewrite_all,
    review_title_candidates,
    rewrite_with_local_rules,
)
from services.rule_checker import (
    Finding,
    Rule,
    add_rule_record,
    build_highlighted_text,
    build_risk_detail_rows,
    build_risk_summary,
    build_safe_term_hits,
    check_text,
    delete_rule_record,
    get_severity_label,
    load_rule_records,
    load_rules,
    update_rule_record,
)
from services.viral_analyzer import (
    IMAGE_INFERENCE_NOTICE,
    build_viral_image_context,
    can_analyze_viral_input,
    store_viral_image_payload,
)
from services.viral_examples import load_viral_examples


IMAGE_NOTE_MIN_CHARS = getattr(note_generator_service, "IMAGE_NOTE_MIN_CHARS", 800)
IMAGE_NOTE_MAX_CHARS = getattr(note_generator_service, "IMAGE_NOTE_MAX_CHARS", 1000)
IMAGE_NOTE_TITLE_COUNT = getattr(note_generator_service, "IMAGE_NOTE_TITLE_COUNT", 3)
_image_note_format_validator = getattr(
    note_generator_service,
    "validate_image_note_format",
    None,
)
_finalizer_supports_title_count = "expected_title_count" in inspect.signature(
    finalize_generated_note
).parameters


def validate_image_note_format(generated: dict) -> list[str]:
    if callable(_image_note_format_validator):
        return _image_note_format_validator(generated)
    return []


BASE_DIR = Path(__file__).resolve().parent
RULE_PATH = BASE_DIR / "data" / "rules.json"
CREATOR_PROFILE_PATH = BASE_DIR / "data" / "creator_profile.json"
DEMO_CREATOR_PROFILE_PATH = BASE_DIR / "data" / "creator_profile.demo.json"
VIRAL_EXAMPLES_PATH = BASE_DIR / "data" / "viral_examples.json"
EXPERIENCE_TITLE = "数学差生逆袭秘籍！30天提高50分"
EXPERIENCE_BODY = """孩子数学一直拖后腿，
我通过每天1小时线上1v1辅导，
帮助孩子找到适合自己的学习方法。
一个月后成绩提升明显，
很多家长都来咨询。"""


@st.cache_data
def get_rules():
    return load_rules(RULE_PATH)


def refresh_rule_cache(message: str) -> None:
    get_rules.clear()
    st.session_state["rule_manager_notice"] = message
    st.rerun()


def reset_review() -> None:
    st.session_state["title_input"] = ""
    st.session_state["body_input"] = ""
    st.session_state["image_text_input"] = ""
    st.session_state["draft_title"] = ""
    st.session_state["draft_body"] = ""
    st.session_state["draft_image_text"] = ""
    st.session_state.pop("uploaded_image_data", None)
    st.session_state.pop("current_image_source", None)
    st.session_state.pop("current_image_bytes", None)
    st.session_state.pop("current_image_hash", None)
    st.session_state.pop("current_image_preview", None)
    st.session_state.pop("last_seen_upload_hash", None)
    st.session_state.pop("last_seen_clipboard_hash", None)
    st.session_state.pop("image_input_error", None)
    st.session_state["confirm_clear_content"] = False
    st.session_state["review_started"] = False
    st.session_state["is_reviewing"] = False
    st.session_state.pop("safe_rewrite_key", None)
    st.session_state.pop("safe_rewrite_result", None)
    st.session_state.pop("line_review_key", None)
    st.session_state.pop("line_review_statuses", None)
    st.session_state.pop("title_generation_key", None)
    st.session_state.pop("title_candidates", None)
    st.session_state.pop("title_generation_error", None)
    st.session_state.pop("title_candidate_reviews", None)
    st.session_state.pop("cover_analysis_requested", None)
    st.session_state.pop("cover_analysis_key", None)
    st.session_state.pop("cover_analysis", None)
    st.session_state.pop("cover_analysis_error", None)
    st.session_state.pop("cover_ocr_lines", None)
    st.session_state.pop("cover_ocr_raw_lines", None)
    st.session_state.pop("cover_ocr_optimized_lines", None)
    st.session_state.pop("cover_ocr_confidence", None)
    st.session_state.pop("cover_ocr_corrections", None)
    st.session_state.pop("cover_ocr_requires_confirmation", None)
    st.session_state.pop("cover_ocr_attempt_key", None)
    st.session_state.pop("cover_ocr_error", None)
    st.session_state.pop("cover_ocr_status", None)
    st.session_state.pop("cover_auto_analysis_key", None)
    st.session_state.pop("cover_analysis_image_key", None)
    st.session_state.pop("cover_analysis_text_key", None)
    st.session_state.pop("cover_analysis_source", None)
    st.session_state.pop("note_generation_result", None)
    st.session_state.pop("note_generation_error", None)
    st.session_state.pop("note_generation_key", None)
    st.session_state.pop("note_regenerate_requested", None)
    st.session_state.pop("pre_publish_report_key", None)
    st.session_state.pop("pre_publish_report", None)
    st.session_state.pop("pre_publish_report_error", None)
    st.session_state.pop("review_run_id", None)
    st.session_state["uploader_key"] = st.session_state.get("uploader_key", 0) + 1


def load_experience_case() -> None:
    st.session_state["title_input"] = EXPERIENCE_TITLE
    st.session_state["body_input"] = EXPERIENCE_BODY
    st.session_state["image_text_input"] = ""
    st.session_state["draft_title"] = EXPERIENCE_TITLE
    st.session_state["draft_body"] = EXPERIENCE_BODY
    st.session_state["draft_image_text"] = ""
    st.session_state["review_started"] = True
    st.session_state["is_reviewing"] = False
    st.session_state.pop("safe_rewrite_key", None)
    st.session_state.pop("safe_rewrite_result", None)
    st.session_state.pop("line_review_key", None)
    st.session_state.pop("line_review_statuses", None)
    st.session_state.pop("title_generation_key", None)
    st.session_state.pop("title_candidates", None)
    st.session_state.pop("title_generation_error", None)
    st.session_state.pop("title_candidate_reviews", None)
    st.session_state.pop("cover_analysis_requested", None)
    st.session_state.pop("cover_analysis_key", None)
    st.session_state.pop("cover_analysis", None)
    st.session_state.pop("cover_analysis_error", None)
    st.session_state.pop("cover_ocr_lines", None)
    st.session_state.pop("cover_ocr_raw_lines", None)
    st.session_state.pop("cover_ocr_optimized_lines", None)
    st.session_state.pop("cover_ocr_confidence", None)
    st.session_state.pop("cover_ocr_corrections", None)
    st.session_state.pop("cover_ocr_requires_confirmation", None)
    st.session_state.pop("cover_ocr_attempt_key", None)
    st.session_state.pop("cover_ocr_error", None)
    st.session_state.pop("cover_ocr_status", None)
    st.session_state.pop("cover_auto_analysis_key", None)
    st.session_state.pop("cover_analysis_image_key", None)
    st.session_state.pop("cover_analysis_text_key", None)
    st.session_state.pop("cover_analysis_source", None)
    st.session_state.pop("note_generation_result", None)
    st.session_state.pop("note_generation_error", None)
    st.session_state.pop("note_generation_key", None)
    st.session_state.pop("note_regenerate_requested", None)
    st.session_state.pop("pre_publish_report_key", None)
    st.session_state.pop("pre_publish_report", None)
    st.session_state.pop("pre_publish_report_error", None)
    st.session_state["review_run_id"] = uuid4().hex
    st.session_state["uploader_key"] = st.session_state.get("uploader_key", 0) + 1


def sync_content_draft() -> None:
    st.session_state["draft_title"] = st.session_state.get("title_input", "")
    st.session_state["draft_body"] = st.session_state.get("body_input", "")


def sync_cover_text_draft() -> None:
    st.session_state["draft_image_text"] = st.session_state.get("image_text_input", "")


def restore_last_input() -> None:
    snapshot = st.session_state.get("last_content_snapshot")
    if not snapshot:
        st.session_state["workspace_notice"] = "暂时没有可恢复的输入内容。"
        return

    st.session_state["draft_title"] = snapshot.get("title", "")
    st.session_state["draft_body"] = snapshot.get("body", "")
    st.session_state["draft_image_text"] = snapshot.get("image_text", "")
    st.session_state["title_input"] = st.session_state["draft_title"]
    st.session_state["body_input"] = st.session_state["draft_body"]
    st.session_state["image_text_input"] = st.session_state["draft_image_text"]
    st.session_state["workspace_notice"] = "已恢复最近一次输入。"


def get_risk_level(findings: list[Finding]) -> tuple[str, str, str]:
    if not findings:
        return "低风险", "未命中当前规则库疑似风险词。", "risk-low"

    high_count = sum(1 for item in findings if item.severity == "high")
    if high_count:
        return "高风险", build_risk_summary(findings), "risk-high"

    medium_count = sum(1 for item in findings if item.severity == "medium")
    if not medium_count:
        return "低风险", build_risk_summary(findings), "risk-low"

    return "中风险", build_risk_summary(findings), "risk-mid"


def get_content_safety_score(findings: list[Finding]) -> tuple[int, str]:
    penalties = {
        "high": 20,
        "medium": 10,
        "low": 5,
    }
    score = max(0, 100 - sum(penalties.get(item.severity, 0) for item in findings))

    if score >= 90:
        return score, "🟢 内容较安全"
    if score >= 70:
        return score, "🟡 建议优化"
    return score, "🔴 风险较高"


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
        :root {
            --ng-primary: #d94b57;
            --ng-primary-hover: #c53f4c;
            --ng-primary-soft: #fff1f2;
            --ng-text: #1f2937;
            --ng-muted: #667085;
            --ng-subtle: #98a2b3;
            --ng-canvas: #f7f8fa;
            --ng-surface: #ffffff;
            --ng-border: #e5e7eb;
            --ng-success: #22c55e;
            --ng-warning: #f59e0b;
            --ng-danger: #ef4444;
        }
        .stApp {
            background: var(--ng-canvas);
            color: var(--ng-text);
        }
        .block-container {
            padding-top: 2rem;
            padding-right: 2rem;
            padding-bottom: 3.5rem;
            padding-left: 2rem;
            max-width: 1180px;
        }
        .hero {
            padding: 4px 2px 22px;
            margin-bottom: 10px;
            border-bottom: 1px solid var(--ng-border);
        }
        .hero h1 {
            margin: 0;
            font-size: 32px;
            line-height: 1.2;
            color: var(--ng-text);
            letter-spacing: 0;
            font-weight: 720;
        }
        .hero p {
            margin: 8px 0 0;
            color: var(--ng-muted);
            font-size: 17px;
            font-weight: 500;
        }
        .notice {
            margin-top: 7px;
            color: var(--ng-muted);
            font-size: 14px;
            line-height: 1.6;
        }
        .step-indicator {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin: 4px 0 20px;
            color: var(--ng-muted);
            font-size: 13px;
            font-weight: 600;
        }
        .step-indicator span {
            padding: 5px 10px;
            border: 1px solid var(--ng-border);
            border-radius: 8px;
            background: var(--ng-surface);
        }
        .step-indicator .active {
            color: #a93240;
            border-color: #f3c8cd;
            background: var(--ng-primary-soft);
        }
        [data-testid="stSidebar"] {
            width: 276px !important;
            min-width: 276px !important;
            background: #ffffff;
            border-right: 1px solid var(--ng-border);
        }
        [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            padding: 1.2rem 0.9rem;
        }
        [data-testid="stSidebar"] h2 {
            margin: 0 0 2px;
            color: var(--ng-text);
            font-size: 21px;
            font-weight: 750;
        }
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
            color: var(--ng-muted);
            font-size: 13px;
        }
        [data-testid="stSidebar"] [role="radiogroup"] {
            gap: 4px;
            margin-top: 18px;
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"] {
            position: relative;
            min-height: 42px;
            margin: 0;
            padding: 0 12px;
            border-radius: 9px;
            color: var(--ng-muted);
            transition: background-color 120ms ease, color 120ms ease;
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"] > div:first-child {
            display: none;
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"] p {
            color: inherit;
            font-size: 14px;
            font-weight: 560;
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"]:hover {
            background: #f7f7f8;
            color: var(--ng-text);
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) {
            background: var(--ng-primary-soft);
            color: var(--ng-text);
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked)::before {
            position: absolute;
            left: 0;
            top: 9px;
            bottom: 9px;
            width: 3px;
            border-radius: 3px;
            background: var(--ng-primary);
            content: "";
        }
        .sidebar-note {
            color: var(--ng-muted);
            font-size: 13px;
            line-height: 1.55;
            margin: 2px 2px 10px;
        }
        .experience-card {
            margin: 8px 0 14px;
            padding: 13px 14px;
            border: 1px solid #f1dadd;
            border-radius: 12px;
            background: #fff7f8;
        }
        .experience-card strong {
            display: block;
            margin-bottom: 4px;
            color: #a93240;
            font-size: 15px;
        }
        .experience-card p {
            margin: 0;
            color: var(--ng-muted);
            font-size: 14px;
            line-height: 1.5;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid var(--ng-border);
            border-radius: 14px;
            background: var(--ng-surface);
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.025);
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            padding: 0.85rem 1rem;
        }
        .module-eyebrow {
            color: #b03644;
            font-size: 13px;
            font-weight: 700;
            margin-bottom: 5px;
        }
        .module-title {
            margin: 0 0 14px;
            font-size: 22px;
            line-height: 1.35;
            color: var(--ng-text);
            font-weight: 700;
        }
        .risk-badge {
            display: inline-block;
            border-radius: 999px;
            padding: 4px 9px;
            font-size: 13px;
            font-weight: 650;
            margin-bottom: 8px;
        }
        .risk-high {
            background: #fef2f2;
            color: #b91c1c;
        }
        .risk-mid {
            background: #fffbeb;
            color: #b45309;
        }
        .risk-low {
            background: #ecfdf5;
            color: #047857;
        }
        .highlighted-original {
            padding: 14px 16px;
            border-radius: 10px;
            border: 1px solid var(--ng-border);
            background: #fcfcfd;
            line-height: 1.85;
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
            padding: 14px 16px;
            border-radius: 10px;
            border: 1px solid var(--ng-border);
            background: #fcfcfd;
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
        .diagnostic-note {
            color: var(--ng-muted);
            font-size: 14px;
            line-height: 1.6;
        }
        [data-testid="stMetric"] {
            min-height: 88px;
            padding: 13px 15px;
            border: 1px solid var(--ng-border);
            border-radius: 12px;
            background: #ffffff;
        }
        [data-testid="stMetricLabel"] {
            color: var(--ng-muted);
            font-size: 13px;
        }
        [data-testid="stMetricValue"] {
            color: var(--ng-text);
            font-size: 25px;
            font-weight: 700;
        }
        [data-baseweb="input"],
        [data-baseweb="textarea"],
        [data-baseweb="select"] > div {
            border-color: var(--ng-border) !important;
            border-radius: 10px !important;
            background: #ffffff !important;
            box-shadow: none !important;
        }
        [data-baseweb="input"]:focus-within,
        [data-baseweb="textarea"]:focus-within,
        [data-baseweb="select"] > div:focus-within {
            border-color: var(--ng-primary) !important;
            box-shadow: 0 0 0 2px rgba(217, 75, 87, 0.10) !important;
        }
        [data-testid="stTextInput"] label,
        [data-testid="stTextArea"] label,
        [data-testid="stSelectbox"] label {
            color: #344054;
            font-size: 14px;
            font-weight: 600;
        }
        textarea, input {
            color: var(--ng-text) !important;
            font-size: 15px !important;
        }
        textarea::placeholder, input::placeholder {
            color: var(--ng-subtle) !important;
            opacity: 1 !important;
        }
        button {
            letter-spacing: 0 !important;
        }
        button[kind="primary"] {
            min-height: 42px;
            border-radius: 10px !important;
            background: var(--ng-primary) !important;
            border-color: var(--ng-primary) !important;
            color: #ffffff !important;
            box-shadow: none !important;
            font-weight: 650 !important;
        }
        button[kind="primary"]:hover {
            background: var(--ng-primary-hover) !important;
            border-color: var(--ng-primary-hover) !important;
        }
        button[kind="secondary"] {
            min-height: 40px;
            border: 1px solid #d0d5dd !important;
            border-radius: 10px !important;
            background: #ffffff !important;
            color: #344054 !important;
            box-shadow: none !important;
            font-weight: 600 !important;
        }
        button[kind="secondary"]:hover {
            border-color: #98a2b3 !important;
            background: #f9fafb !important;
            color: var(--ng-text) !important;
        }
        .st-key-request_clear_content button,
        .st-key-confirm_clear_content_button button {
            border-color: #fecaca !important;
            background: #ffffff !important;
            color: #c2414d !important;
        }
        .st-key-request_clear_content button:hover,
        .st-key-confirm_clear_content_button button:hover {
            background: #fff1f2 !important;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 18px;
            overflow-x: auto;
            overflow-y: hidden;
            scrollbar-width: thin;
            border-bottom: 1px solid var(--ng-border);
        }
        .stTabs [data-baseweb="tab"] {
            flex: 0 0 auto;
            height: 42px;
            padding: 0 2px;
            color: var(--ng-muted);
            font-size: 14px;
            font-weight: 600;
            white-space: nowrap;
        }
        .stTabs [aria-selected="true"] {
            color: var(--ng-primary) !important;
            border-bottom-color: var(--ng-primary) !important;
            border-bottom-width: 2px !important;
        }
        [data-testid="stAlert"] {
            border-radius: 10px;
            border-width: 1px;
            box-shadow: none;
        }
        [data-testid="stDataFrame"] {
            overflow: hidden;
            border: 1px solid var(--ng-border);
            border-radius: 10px;
        }
        [data-testid="stExpander"] {
            border: 1px solid var(--ng-border);
            border-radius: 10px;
            background: #ffffff;
        }
        [data-testid="stExpander"] summary {
            display: flex;
            min-height: 48px;
            padding: 0.7rem 1rem;
            align-items: center;
            line-height: 1.5;
        }
        [data-testid="stExpander"] summary p {
            margin: 0;
            line-height: 1.5;
            overflow-wrap: anywhere;
        }
        [data-testid="stExpander"] summary svg,
        [data-testid="stExpander"] summary [data-testid="stIconMaterial"] {
            flex: 0 0 auto;
        }
        [data-testid="stExpanderDetails"] {
            padding: 0.4rem 1rem 0.9rem;
            line-height: 1.65;
        }
        [data-testid="stHorizontalBlock"] {
            align-items: flex-start;
        }
        [data-testid="column"] {
            min-width: 0;
        }
        [data-testid="stMarkdownContainer"] {
            min-width: 0;
            overflow-wrap: anywhere;
        }
        p, li {
            line-height: 1.65;
        }
        h1, h2, h3, h4 {
            color: var(--ng-text);
            letter-spacing: 0;
            line-height: 1.35;
            overflow-wrap: anywhere;
        }
        h3 {
            font-size: 22px;
        }
        h4 {
            font-size: 17px;
        }
        [data-testid="stCaptionContainer"] {
            color: var(--ng-muted);
            font-size: 13px;
            line-height: 1.55;
        }
        .st-key-pre_publish_report [data-testid="stVerticalBlock"] {
            gap: 0.8rem;
        }
        .st-key-pre_publish_report [data-testid="stMarkdownContainer"] p {
            margin: 0.15rem 0 0.45rem;
            line-height: 1.7;
        }
        .st-key-pre_publish_report [data-testid="stMetric"] {
            margin-bottom: 0.25rem;
        }
        @media (max-width: 1024px) {
            .block-container {
                padding-right: 1.5rem;
                padding-left: 1.5rem;
            }
            [data-testid="stMetricValue"] {
                font-size: 22px;
            }
        }
        @media (max-width: 700px) {
            .block-container {
                padding: 1.25rem 1rem 2.5rem;
            }
            .hero {
                padding-bottom: 18px;
            }
            .hero h1 {
                font-size: 28px;
            }
            .hero p {
                font-size: 16px;
            }
            .module-title {
                font-size: 20px;
            }
            .stTabs [data-baseweb="tab-list"] {
                gap: 16px;
            }
            button[kind="primary"], button[kind="secondary"] {
                width: 100%;
            }
            [data-testid="stMetric"] {
                min-height: 80px;
            }
            div[data-testid="stVerticalBlockBorderWrapper"] > div {
                padding: 0.7rem 0.75rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_copy_buttons(
    rewritten_title: str,
    rewritten_body: str,
    rewrite_reason: str,
) -> None:
    safe_rewrite_text = "\n".join(
        [
            "安全版标题：",
            rewritten_title,
            "",
            "安全版正文：",
            rewritten_body,
            "",
            "修改原因：",
            rewrite_reason or "已根据审核风险完成安全改写。",
        ]
    )
    copy_items = [
        ("copy-title", "复制标题", rewritten_title, "安全版标题已复制"),
        ("copy-body", "复制正文", rewritten_body, "安全版正文已复制"),
        ("copy-all", "复制全部内容", safe_rewrite_text, "安全版内容已复制"),
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
            border: 1px solid #d0d5dd;
            border-radius: 10px;
            background: #ffffff;
            color: #344054;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            margin-bottom: 8px;
        }}
        .copy-button:hover {{
            border-color: #98a2b3;
            background: #f9fafb;
            color: #1f2937;
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


def render_clipboard_button(
    text: str,
    element_id: str,
    label: str,
    success_label: str,
) -> None:
    payload = json.dumps(text, ensure_ascii=False)
    components.html(
        f"""
        <button id="{element_id}" style="
            width:100%;height:38px;border:1px solid #d0d5dd;border-radius:10px;
            background:#fff;color:#344054;cursor:pointer;font-size:14px;font-weight:600;
        ">{escape(label)}</button>
        <script>
        const button = document.getElementById("{element_id}");
        button.addEventListener("click", async () => {{
            await navigator.clipboard.writeText({payload});
            button.textContent = {json.dumps(success_label, ensure_ascii=False)};
        }});
        </script>
        """,
        height=44,
    )


def render_line_review_mode(
    items: list[LineReviewItem],
    statuses: dict[str, str],
) -> None:
    total, handled, unhandled = get_line_review_progress(items, statuses)
    total_col, handled_col, pending_col = st.columns(3)
    total_col.metric("共发现", f"{total} 条")
    handled_col.metric("已处理", f"{handled} 条")
    pending_col.metric("暂未处理", f"{unhandled} 条")

    if not items:
        st.success("当前未发现需要逐条修改的问题。")
        return

    supplier_feedback = build_supplier_feedback(items)
    render_clipboard_button(
        supplier_feedback,
        "copy-supplier-feedback",
        "复制审核反馈",
        "审核反馈已复制",
    )

    for index, item in enumerate(items, start=1):
        status = statuses.get(item.item_id, "pending")
        status_label = {
            "handled": "已处理",
            "deferred": "暂不处理",
            "pending": "待处理",
        }.get(status, "待处理")
        with st.container(border=True):
            header_left, header_right = st.columns([4, 1])
            header_left.markdown(f"**问题 {index} · {escape(item.context)}**")
            header_right.caption(status_label)
            st.markdown(f"**原文片段：** {escape(item.original_text)}")
            detail_left, detail_right = st.columns(2)
            detail_left.write(f"风险类型：{item.category}")
            detail_right.write(f"风险等级：{get_severity_label(item.severity)}")
            st.write(f"修改原因：{item.reason}")
            st.markdown(f"**推荐替换文本：** {escape(item.replacement_text)}")

            copy_left, copy_right = st.columns(2)
            with copy_left:
                render_clipboard_button(
                    item.replacement_text,
                    f"copy-replacement-{item.item_id}",
                    "复制替换文本",
                    "替换文本已复制",
                )
            with copy_right:
                feedback = (
                    f"原句：{item.original_text}\n"
                    f"建议修改为：{item.replacement_text}"
                )
                render_clipboard_button(
                    feedback,
                    f"copy-feedback-{item.item_id}",
                    "复制“原句 → 建议”反馈",
                    "单条反馈已复制",
                )

            action_left, action_right = st.columns(2)
            if action_left.button(
                "标记已处理",
                key=f"line_review_handle_{item.item_id}",
                use_container_width=True,
                disabled=status == "handled",
            ):
                st.session_state["line_review_statuses"][item.item_id] = "handled"
                st.rerun()
            if action_right.button(
                "暂不处理",
                key=f"line_review_defer_{item.item_id}",
                use_container_width=True,
                disabled=status == "deferred",
            ):
                st.session_state["line_review_statuses"][item.item_id] = "deferred"
                st.rerun()


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


def render_format_preserving_changes(changes: list[FormatPreservingChange]) -> None:
    st.markdown("#### 修改前后对比")
    if not changes:
        st.caption("未发生文本修改。")
        return

    for change in changes:
        with st.container(border=True):
            st.caption(change.location)
            st.markdown(f"**原句：** {escape(change.original)}")
            st.markdown(f"**修改后：** {escape(change.replacement)}")


def render_image_review(image_review: ImageReviewResult, has_image: bool) -> None:
    if not has_image:
        st.info("未上传图片。")
        return

    if not image_review["enabled"]:
        st.info("当前未成功识别图片文字，请手动补充后继续分析。")
        return

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


def render_cover_analysis(
    has_image: bool,
    ocr_lines: list[str],
    analysis: dict | None,
    error: str,
) -> None:
    st.markdown("#### 封面图片AI分析")
    if not has_image:
        st.info("上传封面图片后，可点击“AI分析封面”获取封面优化建议。")
        return

    if error:
        st.warning(f"封面分析未完成：{error}")
        return

    if not analysis:
        st.caption("点击左侧“AI分析封面”后，将展示 OCR 文字和封面优化建议。")
        return

    if ocr_lines:
        st.caption("识别文字已同步到“快速开始”的可编辑封面文字框，可修正后重新分析。")
    st.metric("封面评分", f"{analysis['score']}/100")
    attraction = int(analysis["attraction"])
    st.write(f"点击吸引力：{'⭐' * attraction}{'☆' * (5 - attraction)}")

    st.markdown("**分析**")
    dimension_labels = {
        "title_attraction": "标题吸引力",
        "parent_pain": "家长痛点",
        "information_density": "信息量",
        "marketing_risk": "营销风险",
        "core_selling_point": "核心卖点",
        "visual_hierarchy": "字号和层级建议",
        "mobile_readability": "手机端阅读体验",
    }
    for key, label in dimension_labels.items():
        st.write(f"{label}：{analysis['dimensions'].get(key) or '未提供'}")

    st.markdown("**存在问题**")
    if analysis["issues"]:
        for index, issue in enumerate(analysis["issues"], start=1):
            st.write(f"{index}. {issue}")
    else:
        st.write("暂无明显问题。")

    st.markdown("**优化建议**")
    if analysis["suggestions"]:
        for index, suggestion in enumerate(analysis["suggestions"], start=1):
            st.write(f"{index}. {suggestion}")
    else:
        st.write("当前封面已具备基础信息。")

    st.markdown("**推荐封面文案**")
    st.write(analysis["recommended_copy"])


def render_safe_term_hits(safe_terms: list[str]) -> None:
    if not safe_terms:
        st.info("未明显命中可用卖点词。")
        return

    st.write("命中的可用卖点词：")
    for term in safe_terms:
        st.write(f"- {term}")


def render_title_candidates(titles: list[str]) -> None:
    title_types = [
        "🔥 痛点型",
        "👀 好奇型",
        "📚 干货型",
        "👩‍🏫 老师经验型",
        "💬 家长共鸣型",
    ]
    for title_type, title in zip(title_types, titles, strict=True):
        st.markdown(f"**{title_type}：**")
        st.write(title)


def render_title_copy_button(title: str, index: int, label: str = "复制标题") -> None:
    payload = json.dumps(title, ensure_ascii=False)
    button_label = escape(label)
    components.html(
        f"""
        <button id="copy-title-{index}" style="width:100%;height:38px;border:1px solid #d0d5dd;border-radius:10px;background:#fff;color:#344054;cursor:pointer;font-weight:600;">{button_label}</button>
        <script>
        document.getElementById("copy-title-{index}").addEventListener("click", async () => {{
            await navigator.clipboard.writeText({payload});
            document.getElementById("copy-title-{index}").textContent = "已复制";
        }});
        </script>
        """,
        height=42,
    )


def render_title_candidate_reviews(reviews: list[TitleCandidateReview]) -> None:
    title_types = ["痛点型", "好奇型", "干货型", "老师经验型", "家长共鸣型"]
    for index, review in enumerate(reviews, start=1):
        title_type = title_types[index - 1] if index <= len(title_types) else "标题候选"
        with st.container(border=True):
            st.caption(f"{index}. {title_type}")
            status = "🟢 安全" if review.status == "安全" else "🔴 有风险"
            st.markdown(f"**{status}**")
            st.markdown(f"**最终推荐标题：** {review.safe_title}")
            if review.original_title != review.safe_title:
                st.caption(f"原始标题：{review.original_title}")
            if review.risk_terms:
                st.write(f"命中风险词：{'、'.join(review.risk_terms)}")
            st.caption(f"修改说明：{review.change_note}")
            render_title_copy_button(review.safe_title, index)


def request_note_regeneration() -> None:
    st.session_state["note_regenerate_requested"] = True


def render_note_image_analysis(analysis: dict | None) -> None:
    if not analysis:
        return
    with st.expander("查看图片内容分析", expanded=True):
        st.write(f"封面主题：{analysis['cover_theme']}")
        st.write(f"目标人群：{analysis['target_audience']}")
        st.write(f"卖点方向：{analysis['selling_direction']}")
        st.write(f"内容类型：{analysis['content_type']}")
        if analysis.get("visual_elements"):
            st.write("已确认的视觉/文字元素：")
            for item in analysis["visual_elements"]:
                st.write(f"- {item}")
        st.caption(
            analysis.get("analysis_basis")
            or "分析基于 OCR、用户修正文字、图片尺寸和已有封面分析。"
        )


def render_generated_note(note: dict) -> None:
    result_key = note.get("request_key", "generated")[:12]
    title_result_tab, body_result_tab, audit_result_tab, publish_result_tab = st.tabs(
        ["标题候选", "完整正文", "审核结果", "复制发布版"]
    )

    with title_result_tab:
        if not note["titles"]:
            st.warning("本次没有标题通过二次审核，请重新生成。")
        for index, review in enumerate(note["title_reviews"], start=1):
            with st.container(border=True):
                st.caption(f"标题 {index}")
                st.markdown(f"**{review['safe_title']}**")
                st.write(f"审核状态：{'🟢 安全' if review['status'] == '安全' else '🔴 有风险'}")
                if review["original_title"] != review["safe_title"]:
                    st.caption(f"生成原稿：{review['original_title']}")
                st.caption(f"修改说明：{review['change_note'] or '已通过当前规则审核。'}")
                if review["status"] == "安全":
                    render_title_copy_button(review["safe_title"], 200 + index)

    with body_result_tab:
        st.caption(f"正文共 {note['body_char_count']} 字，已按所选范围控制且不超过 1000 字。")
        st.text_area(
            "最终安全正文",
            value=note["body"],
            height=360,
            disabled=True,
            key=f"generated_note_body_{result_key}",
        )
        st.markdown("**行动引导**")
        st.write(note["action"])
        st.markdown("**建议标签**")
        st.write(" ".join(note["tags"]))

    with audit_result_tab:
        if note["risk_items"]:
            st.warning(f"初次审核命中 {len(note['risk_items'])} 项，已进行最小修改。")
            risk_rows = [
                {
                    "位置": item["scope"],
                    "风险词": item["term"],
                    "风险等级": get_severity_label(item["severity"]),
                    "分类": item["category"],
                    "原因": item["reason"],
                    "建议": item["suggestion"],
                }
                for item in note["risk_items"]
            ]
            st.dataframe(risk_rows, use_container_width=True, hide_index=True)
        else:
            st.success("生成原稿未命中当前规则风险项。")

        st.markdown("**修改说明**")
        if note["modifications"]:
            for item in note["modifications"]:
                st.write(f"- {item}")
        else:
            st.caption("无需规则替换。")

        if note["passed_second_review"]:
            st.success("标题、正文、行动引导和标签均已通过二次审核。")
        else:
            st.error("仍有内容未通过二次审核，仅建议使用标记为安全的结果。")

    with publish_result_tab:
        st.text_area(
            "可复制发布版",
            value=note["publish_text"],
            height=420,
            disabled=True,
            key=f"generated_publish_text_{result_key}",
        )
        copy_title, copy_body, copy_all = st.columns(3)
        with copy_title:
            render_clipboard_button(
                note["titles"][0] if note["titles"] else "",
                f"copy-generated-title-{result_key}",
                "复制标题",
                "标题已复制",
            )
        with copy_body:
            render_clipboard_button(
                note["publish_body"],
                f"copy-generated-body-{result_key}",
                "复制正文",
                "正文已复制",
            )
        with copy_all:
            render_clipboard_button(
                note["publish_text"],
                f"copy-generated-all-{result_key}",
                "复制完整发布版",
                "发布版已复制",
            )
        st.button(
            "重新生成",
            type="primary",
            use_container_width=True,
            key="note_regenerate_button",
            on_click=request_note_regeneration,
        )


def render_creator_profile_editor(profile: dict[str, str]) -> None:
    labels = {
        "name": "创作者姓名/称呼",
        "subjects": "教授科目",
        "target_grades": "目标年级",
        "target_students": "目标学生类型",
        "teaching_format": "教学形式",
        "session_duration": "单次时长",
        "pricing": "价格信息",
        "teaching_features": "教学特点",
        "personal_experience": "个人经历",
        "public_cases": "可以公开的数据或案例",
        "do_not_invent": "禁止模型虚构的信息",
        "desired_action": "希望用户采取的行动",
        "writing_style": "常用表达方式",
    }
    text_area_fields = {
        "teaching_features",
        "personal_experience",
        "public_cases",
        "do_not_invent",
        "desired_action",
        "writing_style",
    }
    sections = {
        "基本身份": ("name", "subjects", "target_grades", "target_students"),
        "服务信息": ("teaching_format", "session_duration", "pricing", "teaching_features"),
        "内容风格与禁用信息": (
            "personal_experience",
            "public_cases",
            "do_not_invent",
            "desired_action",
            "writing_style",
        ),
    }
    updated_profile: dict[str, str] = {}
    with st.form("creator_profile_form"):
        for index, (section_name, fields) in enumerate(sections.items()):
            with st.expander(section_name, expanded=index == 0):
                for field in fields:
                    if field in text_area_fields:
                        updated_profile[field] = st.text_area(
                            labels[field],
                            value=profile.get(field, ""),
                            height=80,
                            key=f"creator_{field}",
                        )
                    else:
                        updated_profile[field] = st.text_input(
                            labels[field],
                            value=profile.get(field, ""),
                            key=f"creator_{field}",
                        )
        saved = st.form_submit_button("保存创作者资料", type="primary", use_container_width=True)
    if saved:
        save_creator_profile(CREATOR_PROFILE_PATH, updated_profile)
        st.session_state["creator_profile_notice"] = "创作者资料已保存，后续 AI 生成将只参考已填写内容。"
        st.rerun()


def render_viral_note_analysis(
    analysis: dict | None,
    image_analysis: dict | None,
) -> None:
    if analysis:
        st.metric("爆款评分", f"{analysis['score']}/100")
    title_tab, opening_tab, structure_tab, image_tab, method_tab = st.tabs(
        ["标题拆解", "开头钩子", "正文结构", "图片拆解", "可复用方法"]
    )
    with title_tab:
        if not analysis:
            st.caption("尚未生成文字拆解。")
        else:
            title_analysis = analysis["title_analysis"]
            st.write(f"- 是否有痛点：{title_analysis['pain_point']}")
            st.write(f"- 是否有目标人群：{title_analysis['target_audience']}")
            st.write(f"- 是否有点击吸引力：{title_analysis['click_attraction']}")
    with opening_tab:
        if analysis:
            st.write(analysis["structure_analysis"]["opening"])
        else:
            st.caption("尚未生成开头钩子分析。")
    with structure_tab:
        if analysis:
            structure = analysis["structure_analysis"]
            st.write(f"- 中段：{structure['middle']}")
            st.write(f"- 结尾：{structure['ending']}")
        else:
            st.caption("尚未生成正文结构分析。")
    with image_tab:
        st.info(IMAGE_INFERENCE_NOTICE)
        if not image_analysis:
            st.caption("添加图片并开始拆解后，这里会展示基于 OCR 和基础图片信息的分析。")
        else:
            st.markdown("**吸引点**")
            for item in image_analysis["attraction_points"]:
                st.write(f"- {item}")
            st.markdown("**版式结构（推断或建议）**")
            layout = image_analysis["layout_structure"]
            for key, label in (
                ("headline_position", "主标题位置"),
                ("text_hierarchy", "文字层级"),
                ("information_density", "信息密度"),
                ("visual_focus", "视觉焦点"),
                ("element_relationship", "人物/文字/背景关系"),
            ):
                st.write(f"- {label}：{layout.get(key) or '现有信息不足'}")
            st.markdown("**文案结构**")
            copy_structure = image_analysis["copy_structure"]
            for key, label in (
                ("target_audience", "目标人群"),
                ("pain_point", "痛点"),
                ("credibility", "老师或课程背书"),
                ("service_information", "价格、时长、1V1等服务信息"),
            ):
                st.write(f"- {label}：{copy_structure.get(key) or '现有文字未体现'}")
            st.markdown("**风险点**")
            for item in image_analysis["risk_points"] or ["未发现明确风险表达。"]:
                st.write(f"- {item}")
            st.markdown("**不建议照搬内容**")
            for item in image_analysis["avoid_copying"] or ["暂无。"]:
                st.write(f"- {item}")
    with method_tab:
        if analysis:
            st.markdown("**爆款原因**")
            for index, reason in enumerate(analysis["viral_reasons"], start=1):
                st.write(f"{index}. {reason}")
            st.markdown("**可复制模板**")
            st.text_area("可复制模板", value=analysis["copyable_template"], height=150, disabled=True)
            st.markdown("**优化建议**")
            for index, suggestion in enumerate(analysis["suggestions"], start=1):
                st.write(f"{index}. {suggestion}")
        if image_analysis:
            st.markdown("**图片可复用元素**")
            for item in image_analysis["reusable_elements"]:
                st.write(f"- {item}")


def render_pre_publish_report(report: dict) -> None:
    with st.container(key="pre_publish_report"):
        _render_pre_publish_report_content(report)


def _render_pre_publish_report_content(report: dict) -> None:
    st.metric("① 综合评分", f"{report['score']}/100")

    st.markdown("**② 标题分析**")
    title_analysis = report["title_analysis"]
    for label, items in (
        ("优点", title_analysis["strengths"]),
        ("问题", title_analysis["problems"]),
        ("修改建议", title_analysis["suggestions"]),
    ):
        st.write(f"{label}：")
        for item in items:
            st.write(f"- {item}")

    st.markdown("**③ 正文分析**")
    body_analysis = report["body_analysis"]
    st.write(f"- 结构：{body_analysis['structure']}")
    st.write(f"- 用户痛点：{body_analysis['user_pain']}")
    st.write(f"- 营销风险：{body_analysis['marketing_risk']}")

    st.markdown("**④ 封面分析**")
    cover_analysis = report["cover_analysis"]
    st.write(f"- 点击吸引力：{cover_analysis['click_attraction']}")
    st.write(f"- 信息量：{cover_analysis['information_density']}")
    st.write("优化建议：")
    for suggestion in cover_analysis["suggestions"]:
        st.write(f"- {suggestion}")

    st.markdown("**⑤ 最终发布建议**")
    for index, advice in enumerate(report["final_advice"], start=1):
        st.write(f"{index}. {advice}")


def render_rule_management() -> None:
    render_page_hero(
        "规则管理",
        "维护动态审核规则",
        "新增、编辑或停用规则后，内容审核会在下一次运行时自动读取最新规则库。",
    )

    notice = st.session_state.pop("rule_manager_notice", "")
    if notice:
        st.success(notice)

    try:
        records = load_rule_records(RULE_PATH)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        st.error(f"规则库读取失败：{error}")
        return

    with st.container(border=True):
        st.markdown('<div class="module-eyebrow">当前规则库</div>', unsafe_allow_html=True)
        st.markdown('<div class="module-title">审核规则</div>', unsafe_allow_html=True)
        enabled_count = sum(record["enabled"] for record in records)
        summary_left, summary_right = st.columns(2)
        summary_left.metric("规则总数", len(records))
        summary_right.metric("启用规则", enabled_count)
        table_rows = [
            {
                "关键词": record["term"],
                "等级": get_severity_label(record["severity"]),
                "分类": record["category"],
                "修改建议": record["suggestion"] or "建议删除、弱化或重新表述",
                "启用状态": "启用" if record["enabled"] else "停用",
            }
            for record in records
        ]
        st.dataframe(table_rows, use_container_width=True, hide_index=True)

    with st.container(border=True):
        st.markdown('<div class="module-eyebrow">规则操作</div>', unsafe_allow_html=True)
        st.markdown('<div class="module-title">维护规则库</div>', unsafe_allow_html=True)
        add_tab, edit_tab, delete_tab = st.tabs(["新增规则", "编辑规则", "删除规则"])

        with add_tab:
            with st.form("add_rule_form", clear_on_submit=True):
                term = st.text_input("关键词", placeholder="例如：保证提分")
                severity = st.selectbox(
                    "风险等级",
                    options=["high", "medium", "low"],
                    format_func=get_severity_label,
                )
                category = st.text_input("分类", placeholder="例如：效果承诺")
                reason = st.text_area("原因", placeholder="说明该表达可能带来的审核风险", height=100)
                suggestion = st.text_input("建议替换", placeholder="例如：调整表达")
                enabled = st.checkbox("启用状态", value=True)
                submitted = st.form_submit_button("新增规则", type="primary", use_container_width=True)
            if submitted:
                try:
                    add_rule_record(
                        RULE_PATH,
                        {
                            "term": term,
                            "severity": severity,
                            "category": category,
                            "reason": reason,
                            "suggestion": suggestion,
                            "enabled": enabled,
                        },
                    )
                except ValueError as error:
                    st.error(str(error))
                except OSError as error:
                    st.error(f"规则保存失败：{error}")
                else:
                    refresh_rule_cache(f"已新增规则“{term.strip()}”，审核将立即使用新规则。")

        with edit_tab:
            if not records:
                st.info("当前没有可编辑的规则。")
            else:
                rule_terms = [record["term"] for record in records]
                selected_term = st.selectbox(
                    "选择要编辑的规则",
                    rule_terms,
                    format_func=lambda value: next(
                        record["term"] + f" · {get_severity_label(record['severity'])}"
                        for record in records
                        if record["term"] == value
                    ),
                )
                selected_record = next(
                    record for record in records if record["term"] == selected_term
                )
                with st.form(f"edit_rule_form_{selected_term}"):
                    edited_term = st.text_input(
                        "关键词",
                        value=selected_record["term"],
                        key=f"edit_term_{selected_term}",
                    )
                    severity_options = ["high", "medium", "low"]
                    edited_severity = st.selectbox(
                        "风险等级",
                        options=severity_options,
                        index=severity_options.index(selected_record["severity"]),
                        format_func=get_severity_label,
                        key=f"edit_severity_{selected_term}",
                    )
                    edited_category = st.text_input(
                        "分类",
                        value=selected_record["category"],
                        key=f"edit_category_{selected_term}",
                    )
                    edited_reason = st.text_area(
                        "原因",
                        value=selected_record["reason"],
                        height=100,
                        key=f"edit_reason_{selected_term}",
                    )
                    edited_suggestion = st.text_input(
                        "建议替换",
                        value=selected_record["suggestion"],
                        key=f"edit_suggestion_{selected_term}",
                    )
                    edited_enabled = st.checkbox(
                        "启用状态",
                        value=selected_record["enabled"],
                        key=f"edit_enabled_{selected_term}",
                    )
                    updated = st.form_submit_button("保存修改", type="primary", use_container_width=True)
                if updated:
                    try:
                        update_rule_record(
                            RULE_PATH,
                            selected_term,
                            {
                                "term": edited_term,
                                "severity": edited_severity,
                                "category": edited_category,
                                "reason": edited_reason,
                                "suggestion": edited_suggestion,
                                "enabled": edited_enabled,
                            },
                        )
                    except ValueError as error:
                        st.error(str(error))
                    except OSError as error:
                        st.error(f"规则保存失败：{error}")
                    else:
                        refresh_rule_cache("规则已更新，审核将立即使用最新配置。")

        with delete_tab:
            if not records:
                st.info("当前没有可删除的规则。")
            else:
                delete_term = st.selectbox("选择要删除的规则", [record["term"] for record in records])
                confirmed = st.checkbox(
                    f"我确认删除规则“{delete_term}”",
                    key=f"confirm_delete_{delete_term}",
                )
                if st.button("删除规则", use_container_width=True):
                    if not confirmed:
                        st.warning("请先确认删除操作。")
                    else:
                        try:
                            delete_rule_record(RULE_PATH, delete_term)
                        except (OSError, ValueError) as error:
                            st.error(f"规则删除失败：{error}")
                        else:
                            refresh_rule_cache(f"规则“{delete_term}”已删除。")


def render_history_section() -> None:
    history_records = load_recent_history(10)

    with st.container(border=True):
        st.markdown("### 我的记录")
        if not history_records:
            st.info("暂无审核历史。完成一次审核后，记录会自动保存在本地。")
            return

        def record_type(record: dict) -> str:
            if record.get("cover_analysis"):
                return "含封面分析"
            if record.get("title_candidates"):
                return "含标题生成"
            return "内容审核"

        available_types = ["全部", *sorted({record_type(record) for record in history_records})]
        selected_type = st.selectbox("按功能筛选", available_types, key="history_type_filter")
        filtered_records = [
            record
            for record in history_records
            if selected_type == "全部" or record_type(record) == selected_type
        ]

        for record in filtered_records:
            columns = st.columns([3, 1.2, 1.2, 1])
            title_summary = str(record.get("title") or "未填写标题")[:36]
            columns[0].markdown(f"**{title_summary}**")
            columns[0].caption(f"{record_type(record)} · {record.get('time', '')}")
            columns[1].write(f"评分：{record.get('safety_score', 0)}/100")
            columns[2].write(str(record.get("risk_level", "未知")))
            if columns[3].button("查看详情", key=f"history_view_{record.get('id')}"):
                st.session_state["selected_history_id"] = record.get("id")

        selected_history_id = st.session_state.get("selected_history_id")
        selected_record = next(
            (
                record
                for record in filtered_records
                if record.get("id") == selected_history_id
            ),
            None,
        )
        if not selected_record:
            return

        st.markdown("#### 历史详情")
        st.markdown("**原内容**")
        st.write(f"标题：{selected_record.get('title', '')}")
        st.write(f"正文：{selected_record.get('body', '')}")
        image_ocr_text = selected_record.get("image_ocr_text", "")
        if image_ocr_text:
            st.write(f"图片识别文字：{image_ocr_text}")

        st.markdown("**风险分析**")
        st.write(
            f"内容安全评分：{selected_record.get('safety_score', 0)}/100"
            f"｜风险等级：{selected_record.get('risk_level', '未知')}"
        )
        risk_items = selected_record.get("risk_items", [])
        if risk_items:
            st.dataframe(risk_items, use_container_width=True, hide_index=True)
        else:
            st.success("未命中风险项。")

        line_review_items = selected_record.get("line_review_items", [])
        line_review_statuses = selected_record.get("line_review_statuses", {})
        if line_review_items:
            st.markdown("**逐条审校记录**")
            for index, item in enumerate(line_review_items, start=1):
                status = line_review_statuses.get(item.get("item_id", ""), "pending")
                status_label = "已处理" if status == "handled" else "暂未处理"
                with st.expander(f"问题 {index} · {status_label}"):
                    st.write(f"原句：{item.get('original_text', '')}")
                    st.write(f"修改原因：{item.get('reason', '')}")
                    st.write(f"建议修改为：{item.get('replacement_text', '')}")

        st.markdown("**AI安全版**")
        st.write(f"标题：{selected_record.get('safe_title', '')}")
        st.write(f"正文：{selected_record.get('safe_body', '')}")

        title_candidates = selected_record.get("title_candidates", [])
        if title_candidates:
            st.markdown("**爆款标题结果**")
            render_title_candidates(title_candidates)

        cover_analysis = selected_record.get("cover_analysis")
        if cover_analysis:
            st.markdown("**封面分析结果**")
            st.write(f"封面评分：{cover_analysis.get('score', 0)}/100")
            attraction = int(cover_analysis.get("attraction", 0))
            if attraction:
                st.write(f"点击吸引力：{'⭐' * attraction}{'☆' * (5 - attraction)}")
            if cover_analysis.get("recommended_copy"):
                st.write(f"推荐封面文案：{cover_analysis['recommended_copy']}")


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


def render_page_hero(title: str, subtitle: str, description: str) -> None:
    st.markdown(
        f"""
        <div class="hero">
            <h1>{escape(title)}</h1>
            <p>{escape(subtitle)}</p>
            <div class="notice">{escape(description)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def ensure_cover_ocr(
    image_bytes: bytes,
    creator_profile: dict[str, str] | None = None,
) -> tuple[list[str], str]:
    image_key = hashlib.sha256(image_bytes).hexdigest()
    profile_key = hashlib.sha256(
        json.dumps(creator_profile or {}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    attempt_key = f"{image_key}:{get_available_ocr_engine()}:{profile_key}"
    if st.session_state.get("cover_ocr_attempt_key") != attempt_key:
        for key in (
            "cover_analysis",
            "cover_analysis_error",
            "cover_analysis_key",
            "cover_analysis_image_key",
            "cover_analysis_text_key",
            "cover_analysis_source",
            "cover_auto_analysis_key",
        ):
            st.session_state.pop(key, None)
        st.session_state["image_text_input"] = ""
        st.session_state["draft_image_text"] = ""
        extraction = extract_text_details(image_bytes)
        raw_text = "\n".join(extraction.lines)
        correction = correct_ocr_text(
            raw_text,
            creator_profile=creator_profile,
            confidence=extraction.average_confidence,
        )
        optimized_lines = [
            line.strip()
            for line in correction.optimized_text.splitlines()
            if line.strip()
        ]
        st.session_state["cover_ocr_attempt_key"] = attempt_key
        st.session_state["cover_ocr_raw_lines"] = extraction.lines
        st.session_state["cover_ocr_optimized_lines"] = optimized_lines
        st.session_state["cover_ocr_lines"] = optimized_lines
        st.session_state["cover_ocr_confidence"] = extraction.average_confidence
        st.session_state["cover_ocr_corrections"] = list(correction.changes)
        st.session_state["cover_ocr_requires_confirmation"] = correction.requires_confirmation
        st.session_state["cover_ocr_error"] = extraction.error
        st.session_state["cover_ocr_status"] = "success" if optimized_lines else "failed"
        if optimized_lines:
            recognized_text = "\n".join(optimized_lines)
            st.session_state["image_text_input"] = recognized_text
            st.session_state["draft_image_text"] = recognized_text
    return (
        st.session_state.get("cover_ocr_lines", []),
        st.session_state.get("cover_ocr_error", ""),
    )


def get_current_image_bytes() -> bytes:
    return st.session_state.get(
        "current_image_bytes",
        st.session_state.get("uploaded_image_data", b""),
    )


def analyze_cover_text(
    image_bytes: bytes,
    cover_text: str,
    rules: list[Rule],
    source: str,
) -> dict | None:
    image_key = hashlib.sha256(image_bytes).hexdigest()
    normalized_text = cover_text.strip()
    text_key = hashlib.sha256(
        f"{image_key}:{normalized_text}".encode("utf-8")
    ).hexdigest()
    if not normalized_text:
        st.session_state["cover_analysis"] = None
        st.session_state["cover_analysis_error"] = "请先补充封面文字后再分析。"
        return None

    title = st.session_state.get("draft_title", "")
    body = st.session_state.get("draft_body", "")
    findings = check_text(title=title, body=body, rules=rules)
    analysis = analyze_cover(normalized_text, findings)
    st.session_state["cover_analysis"] = analysis
    st.session_state["cover_analysis_error"] = "" if analysis else (
        get_last_error() or "封面分析暂时不可用。"
    )
    st.session_state["cover_analysis_image_key"] = image_key
    st.session_state["cover_analysis_text_key"] = text_key
    st.session_state["cover_analysis_source"] = source
    return analysis


def auto_analyze_cover_once(image_bytes: bytes, rules: list[Rule]) -> None:
    image_key = hashlib.sha256(image_bytes).hexdigest()
    if st.session_state.get("cover_auto_analysis_key") == image_key:
        return

    st.session_state["cover_auto_analysis_key"] = image_key
    if st.session_state.get("cover_ocr_status") != "success":
        return

    cover_text = st.session_state.get("draft_image_text", "")
    with st.spinner("已识别封面文字，正在自动完成封面分析..."):
        analyze_cover_text(image_bytes, cover_text, rules, source="automatic")


def process_image_input(
    image: object,
    source: str,
    rules: list[Rule],
    creator_profile: dict[str, str] | None = None,
) -> bool:
    try:
        payload = normalize_image_input(image, source)
    except ImageInputError as error:
        st.session_state["image_input_error"] = str(error)
        return False

    seen_key = f"last_seen_{source}_hash"
    if st.session_state.get(seen_key) == payload.image_hash:
        return False

    st.session_state[seen_key] = payload.image_hash
    st.session_state.pop("image_input_error", None)
    is_new_image = store_image_payload(st.session_state, payload)
    if is_new_image:
        ensure_cover_ocr(payload.image_bytes, creator_profile)
        auto_analyze_cover_once(payload.image_bytes, rules)
    return is_new_image


def render_cover_diagnosis_page(
    rules: list[Rule],
    creator_profile: dict[str, str],
) -> None:
    render_page_hero(
        "封面诊断",
        "上传封面并分析文字与点击吸引力",
        "上传图片后会自动尝试识别文字；识别失败时仍可手动补充并继续分析。",
    )
    upload_tab, clipboard_tab = st.tabs(["上传图片", "粘贴图片"])
    with upload_tab:
        uploaded_image = st.file_uploader(
            "上传封面图片",
            type=["png", "jpg", "jpeg", "webp"],
            key=f"cover_page_upload_{st.session_state['uploader_key']}",
        )
        if uploaded_image:
            process_image_input(uploaded_image, "upload", rules, creator_profile)

    with clipboard_tab:
        st.markdown("**请先复制图片，然后点击此区域并按 Command/Ctrl + V。**")
        paste_button, component_error = load_paste_image_button()
        if paste_button is None:
            st.warning(component_error)
        else:
            try:
                paste_result = paste_button(
                    label="粘贴剪贴板图片",
                    key=f"cover_clipboard_paste_{st.session_state['uploader_key']}",
                    text_color="#ffffff",
                    background_color="#ef4f5f",
                    hover_background_color="#dc3f50",
                    errors="ignore",
                )
                pasted_image, paste_message = extract_pasted_image(paste_result)
                if pasted_image is not None:
                    process_image_input(pasted_image, "clipboard", rules, creator_profile)
                    if not st.session_state.get("image_input_error"):
                        st.success("图片已粘贴，可继续识别和分析。")
                else:
                    st.caption(paste_message)
            except Exception as error:
                log_paste_component_error(error, "cover diagnosis")
                st.warning(PASTE_UNAVAILABLE_MESSAGE)
        st.caption("系统仅处理你主动粘贴的图片，不读取剪贴板中的其他内容。")

    image_input_error = st.session_state.get("image_input_error", "")
    if image_input_error:
        st.warning(image_input_error)

    image_bytes = get_current_image_bytes()
    if not image_bytes:
        st.info("先上传或粘贴封面，也可以从创作工作台带入已上传的封面。")
        return

    ocr_lines, ocr_error = ensure_cover_ocr(image_bytes, creator_profile)
    auto_analyze_cover_once(image_bytes, rules)
    st.image(image_bytes, caption="封面预览", use_container_width=True)
    if "image_text_input" not in st.session_state:
        st.session_state["image_text_input"] = st.session_state.get("draft_image_text", "")
    image_review = review_image(st.session_state.get("draft_image_text", ""), rules)
    analysis = st.session_state.get("cover_analysis")
    analysis_error = st.session_state.get("cover_analysis_error", "")
    if analysis and st.session_state.get("cover_analysis_source") == "automatic":
        st.success("已自动识别并完成分析。可修改文字后重新分析。")
    elif ocr_error:
        st.info("当前未成功识别图片文字，请手动补充后继续分析。")

    ocr_tab, risk_tab, attraction_tab, suggestion_tab = st.tabs(
        ["文字识别", "风险检测", "封面吸引力", "优化建议"]
    )
    with ocr_tab:
        if ocr_error:
            st.warning(ocr_error)
        elif ocr_lines:
            st.caption("OCR 已自动填充以下文字。")
        raw_ocr_text = "\n".join(st.session_state.get("cover_ocr_raw_lines", []))
        if raw_ocr_text:
            st.text_area(
                "原始识别文本",
                value=raw_ocr_text,
                height=120,
                disabled=True,
                key=f"cover_ocr_raw_display_{st.session_state.get('current_image_hash', '')}",
            )
        corrections = st.session_state.get("cover_ocr_corrections", [])
        if corrections:
            st.caption("已优化：" + "；".join(corrections))
        if st.session_state.get("cover_ocr_requires_confirmation") and raw_ocr_text:
            confidence = st.session_state.get("cover_ocr_confidence")
            confidence_label = f"（平均置信度 {confidence:.0f}%）" if confidence is not None else ""
            st.warning(f"OCR 置信度较低或未知{confidence_label}，未强制纠错，请人工确认。")
        cover_text = st.text_area(
            "优化后文本（可编辑）",
            placeholder="补充封面或海报中的文字",
            height=180,
            key="image_text_input",
            on_change=sync_cover_text_draft,
        )
        if st.button("重新分析", type="primary", use_container_width=True, key="cover_page_analyze_button"):
            with st.spinner("正在根据修正后的文字重新分析封面..."):
                analyze_cover_text(image_bytes, cover_text, rules, source="manual")
            st.rerun()
    with risk_tab:
        st.write(f"安全状态：{image_review['risk_level']}")
        render_image_review(image_review, True)
    with attraction_tab:
        if analysis_error:
            st.warning(analysis_error)
        elif not analysis:
            st.caption("完成封面分析后，这里会展示评分、核心卖点和信息层级。")
        else:
            st.metric("封面评分", f"{analysis['score']}/100")
            attraction = int(analysis["attraction"])
            st.write(f"点击吸引力：{'⭐' * attraction}{'☆' * (5 - attraction)}")
            for key, label in (
                ("title_attraction", "标题吸引力"),
                ("parent_pain", "家长痛点"),
                ("information_density", "信息量"),
                ("core_selling_point", "核心卖点"),
                ("visual_hierarchy", "字号和层级建议"),
                ("mobile_readability", "手机端阅读体验"),
            ):
                st.write(f"{label}：{analysis['dimensions'].get(key) or '未提供'}")
    with suggestion_tab:
        if not analysis:
            st.caption("分析完成后，这里会给出可直接使用的封面优化建议。")
        else:
            st.markdown("**存在问题**")
            for index, issue in enumerate(analysis["issues"] or ["暂无明显问题。"], start=1):
                st.write(f"{index}. {issue}")
            st.markdown("**优化建议**")
            for index, suggestion in enumerate(analysis["suggestions"] or ["当前封面已具备基础信息。"], start=1):
                st.write(f"{index}. {suggestion}")
            st.markdown("**推荐封面文案**")
            st.write(analysis["recommended_copy"])


def clear_viral_import_state() -> None:
    for key in (
        "imported_link_content",
        "link_import_error",
        "viral_original_url",
        "viral_final_url",
        "viral_link_status",
        "viral_extracted_title",
        "viral_extracted_body",
        "viral_extracted_images",
        "viral_selected_image_url",
        "viral_note_analysis",
        "viral_note_analysis_error",
        "viral_text_analysis_key",
        "viral_image_analysis",
        "viral_image_analysis_error",
        "viral_image_analysis_key",
    ):
        st.session_state.pop(key, None)
    if st.session_state.get("viral_image_source") == "link":
        for key in (
            "viral_image_source",
            "viral_image_bytes",
            "viral_image_hash",
            "viral_image_preview",
            "viral_image_format",
            "viral_image_width",
            "viral_image_height",
            "viral_image_ocr_lines",
            "viral_image_ocr_error",
            "viral_image_text",
            "viral_image_description",
        ):
            st.session_state.pop(key, None)


def process_viral_image_input(image: object, source: str) -> bool:
    normalize_source = source if source in {"upload", "clipboard"} else "upload"
    try:
        payload = normalize_image_input(image, normalize_source)
    except ImageInputError as error:
        st.session_state["viral_image_input_error"] = str(error)
        return False

    seen_key = f"viral_last_seen_{source}_hash"
    if st.session_state.get(seen_key) == payload.image_hash:
        return False
    st.session_state[seen_key] = payload.image_hash
    st.session_state.pop("viral_image_input_error", None)
    is_new_image = store_viral_image_payload(st.session_state, payload)
    st.session_state["viral_image_source"] = source
    if not is_new_image:
        return False

    ocr_lines, ocr_error = extract_text_with_status(payload.image_bytes)
    st.session_state["viral_image_ocr_lines"] = ocr_lines
    st.session_state["viral_image_ocr_error"] = ocr_error
    st.session_state["viral_image_text"] = "\n".join(ocr_lines)
    return True


def render_viral_image_input_controls(prefix: str) -> None:
    upload_column, paste_column = st.columns(2)
    with upload_column:
        uploaded_image = st.file_uploader(
            "上传拆解图片",
            type=["png", "jpg", "jpeg", "webp"],
            key=f"{prefix}_viral_image_upload",
        )
        if uploaded_image:
            process_viral_image_input(uploaded_image, "upload")
    with paste_column:
        paste_button, component_error = load_paste_image_button()
        if paste_button is None:
            st.caption(component_error)
        else:
            try:
                paste_result = paste_button(
                    label="粘贴拆解图片",
                    key=f"{prefix}_viral_image_paste",
                    text_color="#ffffff",
                    background_color="#ef4f5f",
                    hover_background_color="#dc3f50",
                    errors="ignore",
                )
                pasted_image, paste_message = extract_pasted_image(paste_result)
                if pasted_image is not None:
                    process_viral_image_input(pasted_image, "clipboard")
                else:
                    st.caption(paste_message)
            except Exception as error:
                log_paste_component_error(error, "viral image input")
                st.caption(PASTE_UNAVAILABLE_MESSAGE)
        st.caption("仅处理你主动粘贴的图片，不读取剪贴板文本。")


def run_viral_analysis(title: str, body: str, rules: list[Rule]) -> None:
    normalized_title = title.strip()
    normalized_body = body.strip()
    if can_analyze_viral_input(normalized_title, normalized_body):
        text_key = hashlib.sha256(
            f"{normalized_title}\n{normalized_body}".encode("utf-8")
        ).hexdigest()
        if st.session_state.get("viral_text_analysis_key") != text_key:
            analysis = analyze_viral_note(normalized_title, normalized_body)
            st.session_state["viral_note_analysis"] = analysis
            st.session_state["viral_note_analysis_error"] = "" if analysis else get_last_error()
            if analysis:
                st.session_state["viral_text_analysis_key"] = text_key

    image_bytes = st.session_state.get("viral_image_bytes", b"")
    if image_bytes:
        image_text = st.session_state.get("viral_image_text", "")
        image_review = review_image(image_text, rules)
        image_context = build_viral_image_context(
            st.session_state,
            risk_items=image_review["risk_items"],
        )
        image_key = hashlib.sha256(
            json.dumps(image_context, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        if st.session_state.get("viral_image_analysis_key") != image_key:
            image_analysis = analyze_viral_image(image_context)
            st.session_state["viral_image_analysis"] = image_analysis
            st.session_state["viral_image_analysis_error"] = "" if image_analysis else get_last_error()
            if image_analysis:
                st.session_state["viral_image_analysis_key"] = image_key


def render_viral_workspace(rules: list[Rule]) -> None:
    render_page_hero(
        "爆款拆解",
        "通过公开链接或手动图文素材分析优秀笔记",
        "公开内容会尽量读取；遇到登录、动态加载、验证码或访问限制时，可立即切换手动输入。",
    )

    analysis_requested = False
    link_tab, manual_tab = st.tabs(["粘贴链接", "手动输入"])
    with link_tab:
        import_url = st.text_input(
            "公开网页链接",
            placeholder="支持短分享链接、完整笔记链接和带查询参数的公开链接",
            key="viral_import_url",
        )
        if st.button("读取链接内容", type="primary", use_container_width=True, key="link_import_button"):
            normalized_url = import_url.strip()
            if normalized_url != st.session_state.get("viral_last_import_url", ""):
                clear_viral_import_state()
                st.session_state["viral_last_import_url"] = normalized_url
            try:
                imported = import_public_page(normalized_url)
                st.session_state["imported_link_content"] = imported
                st.session_state["link_import_error"] = ""
                st.session_state["viral_original_url"] = imported["original_url"]
                st.session_state["viral_final_url"] = imported["final_url"]
                st.session_state["viral_link_status"] = imported["status"]
                st.session_state["viral_extracted_title"] = imported["title"]
                st.session_state["viral_extracted_body"] = imported["body"]
                st.session_state["viral_extracted_images"] = imported["image_urls"]
                st.session_state["viral_import_title_edit"] = imported["title"]
                st.session_state["viral_import_body_edit"] = imported["body"]
            except LinkImportError as error:
                st.session_state["imported_link_content"] = None
                st.session_state["link_import_error"] = str(error)

        imported_content = st.session_state.get("imported_link_content")
        import_error = st.session_state.get("link_import_error", "")
        if imported_content:
            if imported_content["status"] == "success":
                st.success(imported_content["status_message"])
            else:
                st.warning(imported_content["status_message"])
            preview_one, preview_two = st.columns(2)
            preview_one.write(f"原始链接：{imported_content['original_url']}")
            preview_one.write(f"最终链接：{imported_content['final_url']}")
            preview_two.write(f"导入状态：{imported_content['status']}")
            preview_two.write(f"已提取图片：{len(imported_content['image_urls'])} 张")
            st.caption(f"页面描述：{imported_content.get('description') or '未提取到'}")
            imported_title = st.text_input("导入标题", key="viral_import_title_edit")
            imported_body = st.text_area("导入正文", height=180, key="viral_import_body_edit")
            st.caption(f"正文摘要：{(imported_body[:180] + '…') if len(imported_body) > 180 else (imported_body or '待手动补充')}")

            selected_image_url = ""
            image_urls = imported_content["image_urls"]
            if image_urls:
                selected_index = st.selectbox(
                    "选择一张公开图片作为主图",
                    range(len(image_urls)),
                    format_func=lambda index: f"图片 {index + 1}",
                    key="viral_selected_image_index",
                )
                selected_image_url = image_urls[selected_index]
                st.caption(selected_image_url)
                st.session_state["viral_selected_image_url"] = selected_image_url
            render_viral_image_input_controls("link")

            if st.button(
                "确认导入并开始拆解",
                type="primary",
                use_container_width=True,
                key="confirm_viral_import_button",
            ):
                st.session_state["viral_note_title"] = imported_title
                st.session_state["viral_note_body"] = imported_body
                if selected_image_url:
                    try:
                        process_viral_image_input(
                            download_public_image(selected_image_url),
                            "link",
                        )
                    except LinkImportError as error:
                        st.session_state["viral_image_input_error"] = (
                            f"公开图片暂时无法读取：{error} 可继续上传或粘贴图片。"
                        )
                analysis_requested = True
        elif import_error:
            st.warning(import_error)
            st.info("链接暂时无法自动读取，你仍可以手动粘贴标题、正文和图片继续拆解。")
            render_viral_image_input_controls("link")
        else:
            st.caption("读取公开链接后可确认标题、正文和候选图片；也可以先手动添加图片。")
            render_viral_image_input_controls("link")

    with manual_tab:
        viral_title = st.text_input("拆解标题", placeholder="粘贴爆款笔记标题", key="viral_note_title")
        viral_body = st.text_area(
            "拆解正文",
            placeholder="粘贴爆款笔记正文",
            height=180,
            key="viral_note_body",
        )
        render_viral_image_input_controls("manual")
        if st.button("开始爆款拆解", type="primary", use_container_width=True, key="viral_analysis_button"):
            analysis_requested = True

    image_input_error = st.session_state.get("viral_image_input_error", "")
    if image_input_error:
        st.warning(image_input_error)
    image_bytes = st.session_state.get("viral_image_bytes", b"")
    if image_bytes:
        st.image(image_bytes, caption="当前拆解主图", use_container_width=True)
        ocr_error = st.session_state.get("viral_image_ocr_error", "")
        if ocr_error:
            st.caption(f"OCR：{ocr_error} 可在下方手动补充图片文字。")
        st.text_area(
            "图片 OCR 文字（可编辑）",
            key="viral_image_text",
            height=130,
            placeholder="OCR失败时可手动输入图片中的文字",
        )
        st.text_area(
            "图片补充描述（可选）",
            key="viral_image_description",
            height=90,
            placeholder="只填写你能确认的画面信息，例如人物、背景或排版重点",
        )
        st.info(IMAGE_INFERENCE_NOTICE)

    if analysis_requested:
        if not can_analyze_viral_input(viral_title, viral_body) and not image_bytes:
            st.warning("请先提供标题、正文或图片。")
        else:
            with st.spinner("正在拆解文字结构与图片信息..."):
                run_viral_analysis(viral_title, viral_body, rules)

    viral_analysis = st.session_state.get("viral_note_analysis")
    image_analysis = st.session_state.get("viral_image_analysis")
    text_error = st.session_state.get("viral_note_analysis_error", "")
    image_error = st.session_state.get("viral_image_analysis_error", "")
    if viral_analysis or image_analysis:
        render_viral_note_analysis(viral_analysis, image_analysis)
    if text_error:
        st.warning(f"文字拆解暂时不可用：{text_error}")
    if image_error:
        st.warning(f"图片拆解暂时不可用：{image_error}")


def render_creator_profile_page(profile: dict[str, str]) -> None:
    render_page_hero(
        "创作者资料",
        "管理个人身份、服务和内容风格",
        "AI只会使用你确认保存的资料，不会主动虚构经历和数据。",
    )
    notice = st.session_state.pop("creator_profile_notice", "")
    if notice:
        st.success(notice)
    render_creator_profile_editor(profile)


def main() -> None:
    st.set_page_config(
        page_title="NoteGuard AI",
        page_icon=":material/rate_review:",
        layout="wide",
    )
    render_styles()

    for key, default in (
        ("review_started", False),
        ("uploader_key", 0),
        ("is_reviewing", False),
        ("draft_title", ""),
        ("draft_body", ""),
        ("draft_image_text", ""),
    ):
        if key not in st.session_state:
            st.session_state[key] = default

    navigation_descriptions = {
        "创作工作台": "审核、改写、生成与发布检查",
        "封面诊断": "上传封面并分析文字与点击吸引力",
        "爆款拆解": "通过链接或手动内容分析优秀笔记",
        "历史记录": "查看过去的审核与生成结果",
        "规则管理": "维护动态审核规则",
        "创作者资料": "管理个人身份、服务和内容风格",
    }
    navigation_icons = {
        "创作工作台": "⌂",
        "封面诊断": "▧",
        "爆款拆解": "◇",
        "历史记录": "◷",
        "规则管理": "⚙",
        "创作者资料": "◎",
    }
    with st.sidebar:
        st.markdown("## NoteGuard AI")
        st.caption("教育内容运营助手")
        workspace_page = st.radio(
            "导航",
            list(navigation_descriptions),
            format_func=lambda page: f"{navigation_icons[page]}  {page}",
            label_visibility="collapsed",
            key="workspace_page",
        )
        st.markdown(
            f'<div class="sidebar-note">{escape(navigation_descriptions[workspace_page])}</div>',
            unsafe_allow_html=True,
        )
        with st.expander("查看功能说明", expanded=False):
            for item, description in navigation_descriptions.items():
                st.markdown(
                    f'<div class="sidebar-note"><strong>{escape(item)}</strong><br>{escape(description)}</div>',
                    unsafe_allow_html=True,
                )

rules = get_rules()
try:
    creator_profile = load_creator_profile(
        CREATOR_PROFILE_PATH,
        fallback_path=DEMO_CREATOR_PROFILE_PATH,
    )
except Exception:
    creator_profile = load_creator_profile(DEMO_CREATOR_PROFILE_PATH)

if workspace_page == "规则管理":
    render_rule_management()
    return

if workspace_page == "封面诊断":
    render_cover_diagnosis_page(rules, creator_profile)
    return

if workspace_page == "爆款拆解":
    render_viral_workspace(rules)
    return

if workspace_page == "历史记录":
    render_page_hero("历史记录", "查看过去的审核与生成结果", "最近 10 条记录保存在本地，可按已有结果类型筛选和展开查看。")
    render_history_section()
    return

if workspace_page == "创作者资料":
    render_creator_profile_page(creator_profile)
    return
except Exception:
    creator_profile = load_creator_profile(DEMO_CREATOR_PROFILE_PATH)

if workspace_page == "规则管理":
    render_rule_management()
    return

if workspace_page == "封面诊断":
    render_cover_diagnosis_page(rules, creator_profile)
    return

if workspace_page == "爆款拆解":
    render_viral_workspace(rules)
    return

if workspace_page == "历史记录":
    render_page_hero("历史记录", "查看过去的审核与生成结果", "最近 10 条记录保存在本地，可按已有结果类型筛选和展开查看。")
    render_history_section()
    return

if workspace_page == "创作者资料":
    render_creator_profile_page(creator_profile)
    return
    render_page_hero(
        "NoteGuard AI",
        "教育内容智能审核与优化助手",
        "帮助教育创作者检测内容风险、优化表达，并完成发布前检查。",
    )
    st.markdown(
        '<div class="step-indicator"><span class="active">① 准备内容</span><span>② 内容诊断</span><span>③ AI优化</span><span>④ 发布检查</span></div>',
        unsafe_allow_html=True,
    )
    completion_placeholder = st.empty()
    progress_placeholder = st.empty()

    workspace_notice = st.session_state.pop("workspace_notice", "")
    if workspace_notice:
        st.info(workspace_notice)

    with st.container(border=True):
        st.markdown('<div class="module-eyebrow">① 准备内容</div>', unsafe_allow_html=True)
        st.markdown('<div class="module-title">输入一条准备发布的内容</div>', unsafe_allow_html=True)
        if "title_input" not in st.session_state:
            st.session_state["title_input"] = st.session_state["draft_title"]
        if "body_input" not in st.session_state:
            st.session_state["body_input"] = st.session_state["draft_body"]
        input_left, input_right = st.columns([1.35, 0.85], gap="large")
        with input_left:
            title = st.text_input(
                "标题",
                placeholder="请输入小红书标题",
                key="title_input",
                on_change=sync_content_draft,
            )
            body = st.text_area(
                "正文/脚本",
                placeholder="请输入正文、视频脚本或封面文案",
                height=180,
                key="body_input",
                on_change=sync_content_draft,
            )
        with input_right:
            st.markdown(
                """
                <div class="experience-card">
                    <strong>✨ 新手体验</strong>
                    <p>不知道从哪里开始？一键加载教育内容示例，体验完整审核流程。</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.button(
                "✨ 一键体验案例",
                use_container_width=True,
                on_click=load_experience_case,
                key="load_experience_case_button",
            )
            uploaded_image = st.file_uploader(
                "上传封面图片（可选）",
                type=["png", "jpg", "jpeg", "webp"],
                accept_multiple_files=False,
                key=f"image_upload_{st.session_state['uploader_key']}",
            )
            if uploaded_image:
                process_image_input(uploaded_image, "upload", rules, creator_profile)
            active_image_bytes = get_current_image_bytes()
            if active_image_bytes:
                st.image(active_image_bytes, caption="封面已添加，可在“封面诊断”继续处理", use_container_width=True)
                if st.session_state.get("cover_analysis"):
                    st.caption("封面文字已自动识别并完成分析，可在“封面诊断”查看详情。")
                else:
                    st.caption("封面文字识别与 AI 分析已移至“封面诊断”。")

        action_left, action_right = st.columns([2, 1])
        with action_left:
            review_button_slot = st.empty()
            start_review = review_button_slot.button(
                "开始内容诊断",
                type="primary",
                use_container_width=True,
                disabled=st.session_state["is_reviewing"],
                key="start_review_button",
            )
        with action_right:
            if st.button("清空内容", use_container_width=True, key="request_clear_content"):
                st.session_state["confirm_clear_content"] = True
            if st.session_state.get("confirm_clear_content"):
                st.warning("确认后会清空当前输入、封面和本次结果。")
                confirm_left, cancel_right = st.columns(2)
                confirm_left.button(
                    "确认清空",
                    key="confirm_clear_content_button",
                    on_click=reset_review,
                )
                if cancel_right.button("取消", key="cancel_clear_content_button"):
                    st.session_state["confirm_clear_content"] = False
            st.button("恢复最近一次输入", use_container_width=True, on_click=restore_last_input)
        if start_review:
            st.session_state["last_content_snapshot"] = {
                "title": title,
                "body": body,
                "image_text": st.session_state.get("draft_image_text", ""),
            }
            st.session_state["is_reviewing"] = True
            st.session_state["review_started"] = True
            st.session_state["review_run_id"] = uuid4().hex
            review_button_slot.button(
                "正在诊断...",
                type="primary",
                use_container_width=True,
                disabled=True,
                key="reviewing_button",
            )
            render_review_loading(progress_placeholder, completion_placeholder)
            st.session_state["is_reviewing"] = False

    image_text = st.session_state.get("draft_image_text", "")
    active_image_bytes = get_current_image_bytes()
    has_image = bool(active_image_bytes)
    has_review = st.session_state["review_started"] and bool(
        title.strip() or body.strip() or has_image
    )
    findings: list[Finding] = []
    cover_analysis = None
    if has_image:
        active_image_key = hashlib.sha256(active_image_bytes).hexdigest()
        if st.session_state.get("cover_analysis_image_key") == active_image_key:
            cover_analysis = st.session_state.get("cover_analysis")

    if has_review:
        findings = check_text(title=title, body=body, rules=rules)
        rewrite_key = json.dumps(
            {
                "title": title,
                "body": body,
                "risk_items": [
                    (item.term, item.position, item.severity, item.suggestion)
                    for item in findings
                ],
            },
            ensure_ascii=False,
        )
        if st.session_state.get("safe_rewrite_key") == rewrite_key:
            rewrite_result = st.session_state["safe_rewrite_result"]
        else:
            rewrite_result = rewrite_with_local_rules(title, body, findings)
        if st.session_state.get("title_generation_key") == rewrite_key:
            title_candidates = st.session_state.get("title_candidates", [])
            title_candidate_reviews = st.session_state.get("title_candidate_reviews", [])
            title_generation_error = st.session_state.get("title_generation_error", "")
        else:
            title_candidates = []
            title_candidate_reviews = []
            title_generation_error = ""
        rewritten_title = rewrite_result.title
        rewritten_body = rewrite_result.body
        title_changes = build_rewrite_changes(findings, "标题")
        body_changes = build_rewrite_changes(findings, "正文")
        format_changes = build_format_preserving_changes(
            title,
            body,
            rewritten_title,
            rewritten_body,
        )
        risk_level, risk_summary, risk_class = get_risk_level(findings)
        safety_score, safety_status = get_content_safety_score(findings)
        highlighted_title = build_highlighted_text(title, findings, "标题")
        highlighted_body = build_highlighted_text(body, findings, "正文")
        risk_detail_rows = build_risk_detail_rows(findings)
        line_review_items = build_line_review_items(title, body, findings)
        if st.session_state.get("line_review_key") != rewrite_key:
            st.session_state["line_review_key"] = rewrite_key
            st.session_state["line_review_statuses"] = {
                item.item_id: "pending" for item in line_review_items
            }
        line_review_statuses = st.session_state.get("line_review_statuses", {})

        cover_analysis_error = ""
        cover_ocr_lines: list[str] = st.session_state.get("cover_ocr_lines", [])
        if has_image:
            image_bytes = active_image_bytes
            image_key = hashlib.sha256(image_bytes).hexdigest()
            if st.session_state.get("cover_analysis_image_key") == image_key:
                cover_analysis = st.session_state.get("cover_analysis")
                cover_analysis_error = st.session_state.get("cover_analysis_error", "")
                cover_ocr_lines = st.session_state.get("cover_ocr_lines", [])

        review_run_id = st.session_state.get("review_run_id") or uuid4().hex
        st.session_state["review_run_id"] = review_run_id
        upsert_history_record(
            create_history_record(
                record_id=review_run_id,
                title=title,
                body=body,
                safety_score=safety_score,
                risk_level=risk_level,
                risk_items=risk_detail_rows,
                rewritten_title=rewritten_title,
                rewritten_body=rewritten_body,
                image_ocr_text="\n".join(cover_ocr_lines),
                title_candidates=title_candidates,
                cover_analysis=cover_analysis,
                line_review_items=[asdict(item) for item in line_review_items],
                line_review_statuses=line_review_statuses,
            )
        )
        image_review = review_image(image_text if has_image else "", rules)
        safe_term_hits = build_safe_term_hits(
            title=title,
            body=f"{body}\n{image_text if has_image else ''}",
        )

    with st.container(border=True):
        st.markdown('<div class="module-eyebrow">② 内容诊断</div>', unsafe_allow_html=True)
        st.markdown('<div class="module-title">审核结果</div>', unsafe_allow_html=True)
        if not has_review:
            st.info("输入标题或正文后，点击“开始内容诊断”查看风险结果。")
        else:
            metric_score, metric_level, metric_terms, metric_changes = st.columns(4)
            metric_score.metric("安全评分", f"{safety_score}/100")
            metric_level.metric("风险等级", risk_level)
            metric_terms.metric("风险数量", len(findings))
            metric_changes.metric("修改建议", len(risk_detail_rows))
            st.markdown(
                f'<span class="risk-badge {risk_class}">{safety_status}</span>',
                unsafe_allow_html=True,
            )
            st.markdown(f'<div class="diagnostic-note">{escape(risk_summary)}</div>', unsafe_allow_html=True)
            risk_tab, suggestion_tab = st.tabs(["风险问题", "修改建议"])
            with risk_tab:
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
                    st.success("当前未发现明显风险，可继续进行内容优化。")
                elif risk_detail_rows:
                    st.dataframe(risk_detail_rows, use_container_width=True, hide_index=True)
            with suggestion_tab:
                if findings:
                    st.caption("以下建议来自当前规则库，可在安全改写中生成完整版本。")
                    st.dataframe(risk_detail_rows, use_container_width=True, hide_index=True)
                render_safe_term_hits(safe_term_hits)

    with st.container(border=True):
        st.markdown('<div class="module-eyebrow">③ AI优化</div>', unsafe_allow_html=True)
        st.markdown('<div class="module-title">让内容更适合发布</div>', unsafe_allow_html=True)
        rewrite_tab, title_tab, note_tab = st.tabs(["安全改写", "标题生成", "图片驱动生成"])
        with rewrite_tab:
            if not has_review:
                st.info("完成审核后，可在这里生成安全版文案。")
            else:
                line_mode_tab, full_mode_tab = st.tabs(["逐条审校", "格式保持版"])
                with line_mode_tab:
                    st.caption("逐条确认风险位置和最小修改建议；系统不会操作或覆盖供应商原文。")
                    render_line_review_mode(
                        line_review_items,
                        line_review_statuses,
                    )

                with full_mode_tab:
                    st.info("格式保持版只修改命中的风险表达，保留原段落、换行、emoji和标签；建议确认后再替换供应商原稿。")
                    rewrite_label = "重新生成安全版" if st.session_state.get("safe_rewrite_key") == rewrite_key else "一键生成安全版"
                    if st.button(rewrite_label, type="primary", use_container_width=True, key="safe_rewrite_button"):
                        with st.spinner("正在生成安全版文案..."):
                            st.session_state["safe_rewrite_result"] = rewrite_all(
                                title,
                                body,
                                findings,
                                creator_profile=creator_profile,
                            )
                            st.session_state["safe_rewrite_key"] = rewrite_key
                        st.rerun()
                    st.caption(
                        build_rewrite_status_note(
                            findings,
                            source=rewrite_result.source,
                            error=rewrite_result.error,
                        )
                    )
                    st.text_input("格式保持标题", value=rewritten_title, key="rewritten_title_display")
                    st.text_area("格式保持正文", value=rewritten_body, height=170, key="rewritten_body_display")
                    render_format_preserving_changes(format_changes)
                    with st.expander("查看修改原因与记录"):
                        if rewrite_result.reason:
                            st.markdown("**修改原因**")
                            st.write(rewrite_result.reason)
                            st.divider()
                        render_rewrite_changes(title, body, findings, title_changes, body_changes)
                    render_copy_buttons(rewritten_title, rewritten_body, rewrite_result.reason)

        with title_tab:
            if not has_review:
                st.info("完成审核后，可根据当前内容生成高点击标题。")
            else:
                title_button_label = "重新生成5个标题" if title_candidates else "生成5个高点击标题"
                if st.button(title_button_label, type="primary", use_container_width=True, key="title_generation_button"):
                    with st.spinner("正在生成标题候选..."):
                        candidates = generate_title_candidates(
                            title,
                            body,
                            findings,
                            creator_profile=creator_profile,
                        )
                        reviews = review_title_candidates(candidates, rules) if candidates else []
                        st.session_state["title_generation_key"] = rewrite_key
                        st.session_state["title_candidates"] = [review.safe_title for review in reviews]
                        st.session_state["title_candidate_reviews"] = reviews
                        st.session_state["title_generation_error"] = "" if candidates else get_last_error()
                    st.rerun()
                if title_candidate_reviews:
                    render_title_candidate_reviews(title_candidate_reviews)
                elif title_candidates:
                    render_title_candidates(title_candidates)
                elif title_generation_error:
                    st.warning(f"标题生成失败：{title_generation_error}")

        with note_tab:
            if "note_generation_topic" not in st.session_state:
                st.session_state["note_generation_topic"] = st.session_state.get("draft_title", "")
            st.caption("上传图片后，先分析图片内容，再结合已确认的创作者资料和审核规则生成笔记。")
            generation_mode = st.radio(
                "生成来源",
                GENERATION_MODES,
                horizontal=True,
                key="note_generation_mode",
            )
            image_mode = generation_mode == "根据图片生成"
            image_bytes = get_current_image_bytes()
            ocr_text = "\n".join(st.session_state.get("cover_ocr_lines", []))
            corrected_cover_text = st.session_state.get("draft_image_text", "").strip()
            image_context = build_image_source_context(
                image_bytes,
                ocr_text,
                corrected_cover_text,
                cover_analysis=cover_analysis,
            )
            rule_constraints = build_rule_constraints(rules)
            viral_examples = load_viral_examples(VIRAL_EXAMPLES_PATH) if image_mode else []
            if image_context:
                image_context["rule_constraints"] = rule_constraints
            if image_mode:
                st.caption("主流程：图片内容分析 → 标题候选 → 1000字以内正文 → 规则二次审核。")
            else:
                st.caption("备用模式：使用当前标题、正文或主题关键词生成。")
            topic = st.text_input(
                "主题/关键词（可选）",
                placeholder="可补充主题；图片模式可留空",
                key="note_generation_topic",
            )
            option_left, option_right = st.columns(2)
            with option_left:
                if image_mode:
                    content_direction = "图片驱动固定结构"
                    st.info("固定结构：用户痛点 → 老师背书 → 课程/服务 → 优势 → 行动引导")
                    length_range = "800—1000字"
                    st.caption("图片模式正文固定为 800—1000 字，适配小红书投放阅读节奏。")
                else:
                    content_direction = st.selectbox(
                        "内容方向",
                        CONTENT_DIRECTIONS,
                        key="note_content_direction",
                    )
                    length_range = st.selectbox(
                        "字数范围",
                        list(LENGTH_RANGES),
                        index=1,
                        key="note_length_range",
                    )
                if image_mode:
                    include_intro = any(
                        creator_profile.get(field, "").strip()
                        for field in ("name", "subjects", "personal_experience")
                    )
                    include_service = any(
                        creator_profile.get(field, "").strip()
                        for field in ("teaching_format", "session_duration", "pricing", "teaching_features")
                    )
                    st.caption("老师背书和课程信息仅在创作者资料已保存时加入。")
                else:
                    include_intro = st.checkbox("加入老师介绍", key="note_include_intro")
                    include_service = st.checkbox("加入课程信息", key="note_include_service")
            with option_right:
                if image_mode:
                    include_action = True
                    st.caption("图片模式默认生成自然行动引导。")
                else:
                    include_action = st.checkbox(
                        "加入行动引导",
                        value=True,
                        key="note_include_action",
                    )
                include_tags = st.checkbox(
                    "加入标签",
                    value=True,
                    key="note_include_tags",
                )
                available_materials = [
                    label
                    for label, available in (
                        ("当前标题", bool(title.strip())),
                        ("当前正文", bool(body.strip())),
                        ("封面图片", bool(image_bytes)),
                        ("OCR文字", bool(ocr_text.strip())),
                        ("修正封面文字", bool(corrected_cover_text)),
                        ("创作者资料", any(value.strip() for value in creator_profile.values())),
                    )
                    if available
                ]
                st.caption(
                    "已读取：" + ("、".join(available_materials) if available_materials else "等待补充素材")
                )

            generate_requested = st.button(
                "根据图片生成笔记" if image_mode else "根据文字生成笔记",
                type="primary",
                use_container_width=True,
                key="note_generation_button",
            )
            regenerate_requested = st.session_state.pop("note_regenerate_requested", False)
            if generate_requested or regenerate_requested:
                can_generate, generation_error = can_generate_note(
                    generation_mode,
                    topic,
                    title,
                    body,
                    image_context,
                )
                if not can_generate:
                    st.warning(generation_error)
                else:
                    st.session_state["note_generation_error"] = ""
                    confirmed_image_text = str(image_context.get("confirmed_cover_text", "")).strip()
                    note_topic = (
                        topic.strip()
                        or (confirmed_image_text.splitlines()[0] if confirmed_image_text else "")
                        or title.strip()
                    )
                    if image_mode:
                        min_chars, max_chars = IMAGE_NOTE_MIN_CHARS, IMAGE_NOTE_MAX_CHARS
                    else:
                        min_chars, max_chars = LENGTH_RANGES[length_range]
                    source_title = "" if image_mode else title.strip()
                    source_body = "" if image_mode else body.strip()
                    source_findings = list(findings)
                    if image_mode:
                        source_findings = check_text("", confirmed_image_text, rules)

                    image_analysis = None
                    image_analysis_error = ""
                    image_analysis_key = ""
                    if image_mode:
                        image_analysis_key = build_generation_request_key(
                            {
                                "image_context": image_context,
                                "creator_profile": creator_profile,
                                "risk_terms": [item.term for item in source_findings],
                                "rule_constraints": rule_constraints,
                            }
                        )
                        if (
                            st.session_state.get("note_image_analysis_key") == image_analysis_key
                            and st.session_state.get("note_image_analysis")
                        ):
                            image_analysis = st.session_state.get("note_image_analysis")
                        else:
                            with st.spinner("正在进行图片内容分析..."):
                                image_analysis = analyze_note_image_source(
                                    image_context,
                                    creator_profile=creator_profile,
                                    risk_items=source_findings,
                                )
                            st.session_state["note_image_analysis_key"] = image_analysis_key
                            st.session_state["note_image_analysis"] = image_analysis
                        if not image_analysis:
                            image_analysis_error = get_last_error() or "图片素材分析失败，请稍后重试。"

                    viral_example_analysis: dict = {}
                    viral_example_analysis_error = ""
                    if image_mode and viral_examples and image_analysis:
                        example_analysis_key = build_generation_request_key(
                            {
                                "viral_examples": viral_examples,
                                "image_analysis": image_analysis,
                            }
                        )
                        if (
                            st.session_state.get("note_viral_example_analysis_key")
                            == example_analysis_key
                            and st.session_state.get("note_viral_example_analysis")
                        ):
                            viral_example_analysis = st.session_state[
                                "note_viral_example_analysis"
                            ]
                        else:
                            with st.spinner("正在拆解历史跑量案例的共同写法..."):
                                analyzed_examples = analyze_viral_examples_for_generation(
                                    viral_examples,
                                    image_analysis=image_analysis,
                                )
                            st.session_state["note_viral_example_analysis_key"] = (
                                example_analysis_key
                            )
                            st.session_state["note_viral_example_analysis"] = (
                                analyzed_examples or {}
                            )
                            viral_example_analysis = analyzed_examples or {}
                        if not viral_example_analysis:
                            viral_example_analysis_error = (
                                get_last_error() or "历史案例拆解失败，请稍后重试。"
                            )

                    source_materials = {
                        "current_title": source_title,
                        "current_body": source_body,
                        "has_cover_image": bool(image_bytes),
                        "cover_image_hash": hashlib.sha256(image_bytes).hexdigest() if image_bytes else "",
                        "ocr_text": ocr_text.strip(),
                        "corrected_cover_text": corrected_cover_text,
                        "cover_analysis": cover_analysis or {},
                        "image_analysis": image_analysis or {},
                        "viral_example_analysis": viral_example_analysis,
                        "rule_constraints": rule_constraints,
                        "viral_examples": viral_examples,
                    }
                    structure_seed = "|".join(
                        [note_topic, title.strip(), body.strip()[:160], corrected_cover_text]
                    )
                    generation_options = {
                        "generation_mode": generation_mode,
                        "content_direction": content_direction,
                        "length_range": length_range,
                        "min_chars": min_chars,
                        "max_chars": max_chars,
                        "include_intro": include_intro,
                        "include_service": include_service,
                        "include_action": include_action,
                        "include_tags": include_tags,
                        "structure_guidance": get_structure_guidance(
                            content_direction, structure_seed
                        ),
                    }
                    if image_mode:
                        generation_options["structure_guidance"] = IMAGE_GENERATION_STRUCTURE
                        generation_options["expected_title_count"] = IMAGE_NOTE_TITLE_COUNT
                    request_payload = {
                        "topic": note_topic,
                        "source_materials": source_materials,
                        "creator_profile": creator_profile,
                        "generation_options": generation_options,
                        "risk_terms": [item.term for item in source_findings],
                    }
                    request_key = build_generation_request_key(request_payload)
                    note_result = None
                    blocking_error = image_analysis_error or viral_example_analysis_error
                    if blocking_error:
                        st.session_state["note_generation_error"] = blocking_error
                    else:
                        with st.spinner("正在根据当前图文素材生成标题和文案..."):
                            raw_note = generate_xiaohongshu_note(
                                note_topic,
                                creator_profile=creator_profile,
                                generation_options=generation_options,
                                source_materials=source_materials,
                                risk_items=source_findings,
                            )
                            format_issues = (
                                validate_image_note_format(raw_note)
                                if image_mode and raw_note
                                else []
                            )
                            if format_issues:
                                st.session_state["note_generation_error"] = (
                                    "生成结果未达到图片投放格式要求："
                                    + "；".join(format_issues)
                                    + "。请重新生成。"
                                )
                            else:
                                finalize_options = {
                                    "max_body_chars": max_chars,
                                    "include_action": include_action,
                                    "include_tags": include_tags,
                                }
                                if _finalizer_supports_title_count:
                                    finalize_options["expected_title_count"] = (
                                        IMAGE_NOTE_TITLE_COUNT if image_mode else 5
                                    )
                                note_result = (
                                    finalize_generated_note(
                                        raw_note,
                                        rules,
                                        **finalize_options,
                                    )
                                    if raw_note
                                    else None
                                )
                    if note_result:
                        note_result["request_key"] = request_key
                        note_result["generation_mode"] = generation_mode
                        note_result["image_analysis"] = image_analysis
                        st.session_state["note_generation_key"] = request_key
                    st.session_state["note_generation_result"] = note_result
                    if not blocking_error and note_result:
                        st.session_state["note_generation_error"] = ""
                    elif not blocking_error and not st.session_state.get("note_generation_error"):
                        st.session_state["note_generation_error"] = get_last_error()
            generated_note = st.session_state.get("note_generation_result")
            note_generation_error = st.session_state.get("note_generation_error", "")
            if generated_note and "action" in generated_note:
                if generated_note.get("generation_mode") == "根据图片生成":
                    render_note_image_analysis(generated_note.get("image_analysis"))
                render_generated_note(generated_note)
            elif generated_note:
                st.session_state.pop("note_generation_result", None)
                st.info("图片驱动生成已升级，请重新生成新版本。")
            elif note_generation_error:
                st.warning(f"图片驱动生成失败：{note_generation_error}")

    with st.container(border=True):
        st.markdown('<div class="module-eyebrow">④ 发布检查</div>', unsafe_allow_html=True)
        st.markdown('<div class="module-title">发布前最后检查</div>', unsafe_allow_html=True)
        with st.expander("展开发布检查", expanded=False):
            if not has_review:
                st.info("完成当前内容诊断后，可生成发布前体检报告。")
            else:
                checklist = [
                    ("标题安全", "已完成" if not any(item.position == "标题" for item in findings) else "需优化"),
                    ("正文安全", "已完成" if not any(item.position == "正文" for item in findings) else "需优化"),
                    ("封面是否已检查", "已检查" if cover_analysis else ("已上传，待检查" if has_image else "未上传")),
                    ("是否存在绝对化承诺", "需结合风险详情确认" if findings else "未发现"),
                    ("是否包含未经确认的数据", "请人工确认"),
                    ("是否包含明确行动引导", "请人工确认"),
                ]
                st.dataframe(
                    [{"检查项": label, "状态": status} for label, status in checklist],
                    use_container_width=True,
                    hide_index=True,
                )
                report_key = json.dumps(
                    {
                        "rewrite_key": rewrite_key,
                        "safety_score": safety_score,
                        "safe_title": rewritten_title,
                        "safe_body": rewritten_body,
                        "cover_analysis": cover_analysis,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                if st.button("生成发布前体检报告", type="primary", use_container_width=True, key="pre_publish_report_button"):
                    with st.spinner("正在生成发布前体检报告..."):
                        report = generate_pre_publish_report(
                            title=title,
                            body=body,
                            risk_items=findings,
                            safety_score=safety_score,
                            safe_rewrite={"title": rewritten_title, "body": rewritten_body},
                            cover_analysis=cover_analysis,
                        )
                    st.session_state["pre_publish_report_key"] = report_key
                    st.session_state["pre_publish_report"] = report
                    st.session_state["pre_publish_report_error"] = "" if report else get_last_error()

                if st.session_state.get("pre_publish_report_key") == report_key:
                    report = st.session_state.get("pre_publish_report")
                    report_error = st.session_state.get("pre_publish_report_error", "")
                    if report:
                        render_pre_publish_report(report)
                    elif report_error:
                        st.warning(f"体检报告生成失败：{report_error}")
                elif st.session_state.get("pre_publish_report"):
                    st.caption("审核内容已更新，请重新生成体检报告。")


if __name__ == "__main__":
    main()
