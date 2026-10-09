from __future__ import annotations

import base64
from dataclasses import asdict
import importlib
import json
import hashlib
import inspect
import os
import re
import sys
import time
from html import escape
from pathlib import Path
from uuid import uuid4

import streamlit as st
import streamlit.components.v1 as components


def _enforce_fixed_streamlit_runtime() -> None:
    """Reject local Windows launches that bypass the verified OCR runtime."""
    if os.name != "nt":
        return
    if os.getenv("NOTEGUARD_ALLOW_TEST_RUNTIME") == "1":
        return

    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        if get_script_run_ctx(suppress_warning=True) is None:
            return
    except Exception:
        return

    if os.getenv("NOTEGUARD_FIXED_RUNTIME") == "1" and sys.version_info[:2] == (3, 12):
        return

    expected_python = Path(
        r"C:\Users\崔丽娅\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    )
    actual_python = Path(sys.executable)
    correct_python = os.path.normcase(str(actual_python.resolve())) == os.path.normcase(
        str(expected_python.resolve())
    )
    if correct_python:
        return

    raise RuntimeError(
        "启动环境不正确。请关闭当前服务，并在项目目录运行："
        "powershell -ExecutionPolicy Bypass -File .\\start.ps1。"
        f" 当前 Python：{sys.executable}"
    )


_enforce_fixed_streamlit_runtime()

from services import note_generator as note_generator_service
from services import viral_examples as viral_examples_service
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
from services import content_context as content_context_service
from services.business_profiles import (
    build_material_profile_suggestion,
    load_business_profiles,
    save_business_profile,
)
from services import content_plans as content_plans_service

if not hasattr(content_plans_service, "build_plan_reference_cases"):
    content_plans_service = importlib.reload(content_plans_service)

from services.content_plans import (
    build_content_plan,
    build_plan_reference_cases,
    load_content_plans,
    save_content_plan,
)
from services.demo_mode import (
    DEMO_COVER_ANALYSIS,
    DEMO_PRE_PUBLISH_REPORT,
    DEMO_NOTE_IMAGE_ANALYSIS,
    DEMO_TITLES,
    DEMO_VIRAL_ANALYSIS,
    DEMO_VIRAL_EXAMPLE_ANALYSIS,
    DEMO_VIRAL_IMAGE_ANALYSIS,
    build_demo_note,
    resolve_demo_or_live,
)
from services.image_reviewer import ImageReviewResult, review_image
from services import image_ocr as image_ocr_service
from services.image_input import (
    IMAGE_RESULT_STATE_KEYS,
    ImageInputError,
    normalize_image_input,
    store_image_payload,
)
from services.vision_text import is_vision_text_available, read_cover_text_with_vision
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
from services.ocr_postprocessor import correct_ocr_text
from services import llm as llm_service
from services.workflow_ui_v2 import render_workflow_v2

if not hasattr(llm_service, "generate_content_lab_draft"):
    llm_service = importlib.reload(llm_service)

from services.llm import (
    analyze_cover,
    analyze_note_image_source,
    analyze_viral_examples_for_generation,
    analyze_viral_image,
    analyze_viral_note,
    generate_content_lab_draft,
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
    VIRAL_IMAGE_RESULT_KEYS,
    build_viral_image_context,
    can_analyze_viral_input,
    store_viral_image_payload,
)


def _load_note_generator_exports() -> None:
    """Refresh note-generator exports when Streamlit retained an older module."""
    required = (
        "CONTENT_DIRECTIONS",
        "GENERATION_MODES",
        "LENGTH_RANGES",
        "build_image_source_context",
        "build_generation_request_key",
        "build_rule_constraints",
        "can_generate_note",
        "classify_image_content",
        "finalize_generated_note",
        "get_image_content_structure",
        "get_structure_guidance",
        "validate_publish_draft_quality",
    )
    if any(not hasattr(note_generator_service, name) for name in required):
        importlib.invalidate_caches()
        importlib.reload(note_generator_service)
    missing = [name for name in required if not hasattr(note_generator_service, name)]
    if missing:
        raise ImportError(
            "services.note_generator is missing required exports: " + ", ".join(missing)
        )
    globals().update({name: getattr(note_generator_service, name) for name in required})


_load_note_generator_exports()


def _load_viral_example_exports() -> None:
    """Refresh case-library exports when Streamlit retained an older module."""
    required = (
        "build_cover_visual_analysis",
        "build_case_comparison",
        "build_combined_case_analysis",
        "delete_viral_case",
        "filter_viral_cases",
        "load_viral_cases",
        "load_viral_examples",
        "load_method_models",
        "save_method_model",
        "save_viral_case",
        "update_viral_case_tags",
        "update_viral_case_operation",
    )
    if any(not hasattr(viral_examples_service, name) for name in required):
        importlib.invalidate_caches()
        importlib.reload(viral_examples_service)
    missing = [name for name in required if not hasattr(viral_examples_service, name)]
    if missing:
        raise ImportError(
            "services.viral_examples is missing required exports: " + ", ".join(missing)
        )
    globals().update({name: getattr(viral_examples_service, name) for name in required})


_load_viral_example_exports()

IMAGE_NOTE_MIN_CHARS = getattr(note_generator_service, "IMAGE_NOTE_MIN_CHARS", 800)
IMAGE_NOTE_MAX_CHARS = getattr(note_generator_service, "IMAGE_NOTE_MAX_CHARS", 1000)
IMAGE_NOTE_TITLE_COUNT = getattr(note_generator_service, "IMAGE_NOTE_TITLE_COUNT", 3)
_image_note_format_validator = getattr(
    note_generator_service,
    "validate_image_note_format",
    None,
)


def extract_cover_text_details(image: object, vision_reader=None):
    """Load the enhanced OCR entrypoint safely across Streamlit hot reloads."""
    extractor = getattr(image_ocr_service, "extract_cover_text_details", None)
    if not callable(extractor):
        try:
            importlib.invalidate_caches()
            importlib.reload(image_ocr_service)
            extractor = getattr(image_ocr_service, "extract_cover_text_details", None)
        except Exception:
            extractor = None
    if callable(extractor):
        return extractor(image, vision_reader=vision_reader)
    return image_ocr_service.extract_text_details(image)


def _load_content_context_function(name: str):
    """Recover newly added context helpers from a stale Streamlit module cache."""
    function = getattr(content_context_service, name, None)
    if not callable(function):
        importlib.invalidate_caches()
        importlib.reload(content_context_service)
        function = getattr(content_context_service, name, None)
    if not callable(function):
        raise ImportError(f"services.content_context is missing required function: {name}")
    return function


build_content_context = _load_content_context_function("build_content_context")
build_publish_diagnosis = _load_content_context_function("build_publish_diagnosis")
build_publish_readiness = _load_content_context_function("build_publish_readiness")


extract_text_with_status = image_ocr_service.extract_text_with_status
get_available_ocr_engine = image_ocr_service.get_available_ocr_engine
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
VIRAL_CASE_LIBRARY_PATH = BASE_DIR / "data" / "viral_case_library.json"
VIRAL_METHOD_MODEL_PATH = BASE_DIR / "data" / "viral_method_models.json"
CONTENT_PLAN_PATH = BASE_DIR / "data" / "content_plans.json"
BUSINESS_PROFILE_PATH = BASE_DIR / "data" / "business_profiles.json"
EXPERIENCE_TITLE = "数学差生逆袭秘籍！30天提高50分"
EXPERIENCE_BODY = """孩子数学一直拖后腿，
我通过每天1小时线上1v1辅导，
帮助孩子找到适合自己的学习方法。
一个月后成绩提升明显，
很多家长都来咨询。"""
PUBLIC_DEMO = os.getenv("NOTEGUARD_PUBLIC_DEMO", "1").strip().lower() not in {
    "0",
    "false",
    "no",
}
DEMO_BUSINESS_PROFILE = {
    "id": "public-demo-profile",
    "product_name": "初中数学学习规划",
    "brand_name": "林老师（演示账号）",
    "target_user": "初一至初三、数学基础薄弱的学生家长",
    "usage_scenario": "学情诊断与错题复盘",
    "common_pain_points": "同类题反复出错，盲目刷题仍找不到原因",
    "core_selling_point": "先定位知识点与审题习惯，再给出阶段性学习建议",
    "conversion_method": "预约一次公开演示用学情沟通",
}
DEMO_HISTORY_RECORD = {
    "id": "public-demo-history",
    "time": "演示记录",
    "title": "30天提高50分？先看看学习方法是否适合",
    "body": "这是一条脱敏演示内容，用于展示风险定位和修改建议。",
    "safety_score": 80,
    "risk_level": "高风险",
    "risk_items": [
        {
            "风险词": "30天提高50分",
            "风险等级": "高风险",
            "分类": "效果承诺",
            "原因": "疑似短期量化成绩结果承诺。",
            "建议替换": "阶段性学习调整记录",
            "位置": "标题",
        }
    ],
    "safe_title": "阶段性学习调整记录：先看看学习方法是否适合",
    "safe_body": "这是一条脱敏演示内容，用于展示风险定位和修改建议。",
    "line_review_items": [],
    "line_review_statuses": {},
    "demo_record": True,
}


def get_visible_history() -> list[dict]:
    if not PUBLIC_DEMO:
        return load_recent_history(10)
    session_records = st.session_state.setdefault("session_history", [])
    return [*session_records[:9], DEMO_HISTORY_RECORD.copy()]


def upsert_visible_history(record: dict) -> None:
    if not PUBLIC_DEMO:
        upsert_history_record(record)
        return
    records = st.session_state.setdefault("session_history", [])
    records[:] = [item for item in records if item.get("id") != record.get("id")]
    records.insert(0, record)
    del records[10:]


def open_workspace_page(page: str) -> None:
    st.session_state["workspace_page"] = page


def restore_history_for_review(record: dict) -> None:
    st.session_state["title_input"] = str(record.get("title") or "")
    st.session_state["body_input"] = str(record.get("body") or "")
    st.session_state["draft_title"] = st.session_state["title_input"]
    st.session_state["draft_body"] = st.session_state["body_input"]
    st.session_state["review_started"] = False
    st.session_state["workspace_page"] = "内容审核中心"


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
    st.session_state["cover_image_description"] = ""
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
    st.session_state.pop("cover_text", None)
    st.session_state.pop("cover_vision_lines", None)
    st.session_state.pop("cover_vision_context", None)
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


def delete_current_image() -> None:
    manual_text = st.session_state.get("image_text_input", "") or st.session_state.get(
        "draft_image_text", ""
    )
    for key in (
        "uploaded_image_data",
        "current_image_source",
        "current_image_bytes",
        "current_image_hash",
        "current_image_preview",
        "last_seen_upload_hash",
        "last_seen_clipboard_hash",
        "image_input_error",
        "cover_image_description",
        *IMAGE_RESULT_STATE_KEYS,
    ):
        st.session_state.pop(key, None)
    st.session_state["image_text_input"] = manual_text
    st.session_state["draft_image_text"] = manual_text
    st.session_state["uploader_key"] = st.session_state.get("uploader_key", 0) + 1


def delete_viral_image() -> None:
    manual_text = st.session_state.get("viral_image_text", "")
    manual_description = st.session_state.get("viral_image_description", "")
    for key in (
        "viral_image_source",
        "viral_image_bytes",
        "viral_image_hash",
        "viral_image_preview",
        "viral_image_format",
        "viral_image_width",
        "viral_image_height",
        "viral_image_input_error",
        "viral_last_seen_upload_hash",
        "viral_last_seen_clipboard_hash",
        "viral_last_seen_link_hash",
        "viral_last_seen_manual_hash",
        *VIRAL_IMAGE_RESULT_KEYS,
    ):
        st.session_state.pop(key, None)
    st.session_state["viral_image_text"] = manual_text
    st.session_state["viral_image_description"] = manual_description
    st.session_state["viral_uploader_key"] = st.session_state.get("viral_uploader_key", 0) + 1


def select_imported_main_image(image_urls: list[str]) -> None:
    raw_index = st.session_state.get("viral_import_image_choice", -1)
    selected_index = int(raw_index) if raw_index is not None else -1
    selected_url = image_urls[selected_index] if 0 <= selected_index < len(image_urls) else ""
    previous_url = str(st.session_state.get("viral_selected_image_url", ""))
    if previous_url != selected_url and st.session_state.get("viral_image_source") == "link":
        delete_viral_image()
        st.session_state["viral_image_text"] = ""
        st.session_state["viral_image_description"] = ""
    st.session_state["viral_selected_image_url"] = selected_url
    st.session_state["viral_selected_image_deleted"] = not bool(selected_url)


def delete_imported_main_image(image_urls: list[str]) -> None:
    st.session_state["viral_import_image_choice"] = -1
    select_imported_main_image(image_urls)


def load_experience_case() -> None:
    st.session_state["title_input"] = EXPERIENCE_TITLE
    st.session_state["body_input"] = EXPERIENCE_BODY
    st.session_state["image_text_input"] = ""
    st.session_state["draft_title"] = EXPERIENCE_TITLE
    st.session_state["draft_body"] = EXPERIENCE_BODY
    st.session_state["draft_image_text"] = ""
    st.session_state["cover_image_description"] = ""
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
    st.session_state.pop("cover_text", None)
    st.session_state.pop("cover_vision_lines", None)
    st.session_state.pop("cover_vision_context", None)
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


def load_public_demo() -> None:
    load_experience_case()
    st.session_state["demo_mode"] = True
    st.session_state["viral_note_title"] = EXPERIENCE_TITLE
    st.session_state["viral_note_body"] = EXPERIENCE_BODY
    st.session_state["viral_note_analysis"] = DEMO_VIRAL_ANALYSIS.copy()
    st.session_state["viral_image_analysis"] = DEMO_VIRAL_IMAGE_ANALYSIS.copy()
    st.session_state["workspace_notice"] = "Demo 已加载：全程使用脱敏示例数据，不会调用真实 AI API。"


def exit_public_demo() -> None:
    st.session_state["demo_mode"] = False
    st.session_state["workspace_notice"] = "已退出 Demo，可继续使用自己的内容和已配置的 AI 服务。"


def sync_content_draft() -> None:
    st.session_state["draft_title"] = st.session_state.get("title_input", "")
    st.session_state["draft_body"] = st.session_state.get("body_input", "")


def sync_cover_text_draft() -> None:
    st.session_state["draft_image_text"] = st.session_state.get("image_text_input", "")


def show_publish_optimization_plan() -> None:
    st.session_state["show_publish_optimization_plan"] = True
    st.session_state["workspace_notice"] = "优化方案已整理，请按“修改标题、修改封面文案、生成发布稿”依次处理。"


def request_workspace_recheck() -> None:
    st.session_state["review_started"] = True
    st.session_state["is_reviewing"] = True
    st.session_state["review_run_id"] = uuid4().hex
    st.session_state["workspace_notice"] = "已重新读取当前标题、正文和封面内容。"


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
            --ng-primary: #2563eb;
            --ng-primary-hover: #1d4ed8;
            --ng-primary-soft: #eff6ff;
            --ng-text: #1f2937;
            --ng-muted: #64748b;
            --ng-subtle: #98a2b3;
            --ng-canvas: #f8fafc;
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
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
            background-color: var(--ng-canvas) !important;
        }
        [data-testid="stHeader"] {
            background: rgba(248, 250, 252, 0.96) !important;
            color: var(--ng-text) !important;
            box-shadow: none !important;
        }
        [data-testid="stDecoration"] {
            display: none !important;
        }
        [data-testid="stToolbar"],
        [data-testid="stStatusWidget"] {
            background: transparent !important;
            color: var(--ng-muted) !important;
        }
        .block-container {
            padding-top: 2rem;
            padding-right: 2rem;
            padding-bottom: 3.5rem;
            padding-left: 2rem;
            max-width: 1180px;
        }
        .hero {
            display: block;
            width: 100%;
            height: auto !important;
            min-height: 0 !important;
            padding: 26px 28px;
            margin-bottom: 18px;
            border: 1px solid var(--ng-border);
            border-radius: 18px;
            background: linear-gradient(135deg, #ffffff 0%, #fff7f7 100%);
            box-shadow: 0 10px 30px rgba(15, 23, 42, 0.05);
            overflow: visible !important;
        }
        [data-testid="stMarkdownContainer"]:has(.hero),
        [data-testid="stMarkdownContainer"]:has(.quick-entry-grid) {
            height: auto !important;
            min-height: 0 !important;
            overflow: visible !important;
        }
        .hero h1 {
            margin: 0;
            font-size: 34px;
            line-height: 1.2;
            color: var(--ng-text);
            letter-spacing: 0;
            font-weight: 750;
        }
        .hero p {
            margin: 13px 0 0;
            color: var(--ng-text);
            font-size: 18px;
            font-weight: 650;
        }
        .notice {
            margin-top: 9px;
            color: #475569;
            font-size: 14px;
            font-weight: 550;
            line-height: 1.6;
            max-width: 760px;
        }
        .v2-heading h1 {
            margin: 0 0 13px;
            color: var(--ng-text);
            font-size: 34px;
            line-height: 1.25;
            font-weight: 750;
        }
        .v2-heading .v2-lead {
            margin: 0 0 8px;
            color: #344054;
            font-size: 16px;
            font-weight: 570;
            line-height: 1.6;
        }
        .v2-heading .v2-detail {
            margin: 0 0 18px;
            color: #526174;
            font-size: 13px;
            font-weight: 550;
            line-height: 1.55;
        }
        .quick-entry-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 14px;
            margin: 0 0 22px;
            overflow: visible;
        }
        .quick-entry-card {
            min-height: 112px;
            padding: 18px;
            border: 1px solid var(--ng-border);
            border-radius: 14px;
            background: #ffffff;
            box-shadow: 0 4px 16px rgba(15, 23, 42, 0.045);
            transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease;
        }
        .quick-entry-card:hover {
            transform: translateY(-2px);
            border-color: #fecaca;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
        }
        .quick-entry-card strong {
            display: block;
            margin-bottom: 7px;
            color: var(--ng-text);
            font-size: 16px;
        }
        .quick-entry-card span {
            color: var(--ng-muted);
            font-size: 13px;
            line-height: 1.55;
        }
        .trust-strip {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 8px 18px;
            margin: -6px 0 20px;
            padding: 11px 14px;
            border: 1px solid var(--ng-border);
            border-radius: 12px;
            background: #ffffff;
            color: var(--ng-muted);
            font-size: 12px;
            line-height: 1.5;
        }
        .trust-strip strong {
            color: var(--ng-text);
            font-weight: 650;
        }
        .trust-strip span::before {
            margin-right: 6px;
            color: var(--ng-primary);
            content: "✓";
            font-weight: 800;
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
            box-shadow: 8px 0 24px rgba(15, 23, 42, 0.035);
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
            gap: 7px;
            margin-top: 18px;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label,
        [data-testid="stSidebar"] [role="radiogroup"] label p,
        [data-testid="stSidebar"] [role="radiogroup"] label span {
            color: var(--ng-text) !important;
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"] {
            position: relative;
            min-height: 58px;
            margin: 0;
            padding: 8px 12px;
            border: 1px solid transparent;
            border-radius: 12px;
            color: var(--ng-text) !important;
            transition: background-color 120ms ease, color 120ms ease;
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"] > div:first-child {
            display: none !important;
            width: 0 !important;
            min-width: 0 !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            opacity: 0 !important;
            overflow: hidden !important;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label > div:first-child,
        [data-testid="stSidebar"] [role="radiogroup"] label input[type="radio"] {
            display: none !important;
            width: 0 !important;
            min-width: 0 !important;
            height: 0 !important;
            margin: 0 !important;
            opacity: 0 !important;
            pointer-events: none !important;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label > div:first-child *,
        [data-testid="stSidebar"] [role="radiogroup"] label [role="radio"],
        [data-testid="stSidebar"] [role="radiogroup"] label svg,
        [data-testid="stSidebar"] [role="radiogroup"] label circle {
            display: none !important;
            visibility: hidden !important;
            width: 0 !important;
            min-width: 0 !important;
            height: 0 !important;
            opacity: 0 !important;
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"] > div:last-child,
        [data-testid="stSidebar"] label[data-baseweb="radio"] p,
        [data-testid="stSidebar"] label[data-baseweb="radio"] span {
            color: var(--ng-text) !important;
            font-size: 14px;
            font-weight: 560;
            line-height: 1.45;
            white-space: pre-line;
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"]:hover {
            border-color: var(--ng-border);
            background: #f8fafc;
            color: var(--ng-text);
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) {
            background: var(--ng-primary-soft);
            border-color: #fecaca;
            color: #a93240 !important;
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) > div:last-child,
        [data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) p,
        [data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) span {
            color: #a93240 !important;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label p {
            color: var(--ng-muted) !important;
            font-size: 12px !important;
            font-weight: 450 !important;
            line-height: 1.55 !important;
            white-space: pre-line !important;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label p::first-line {
            color: var(--ng-text);
            font-size: 14px;
            font-weight: 700;
            line-height: 1.9;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p {
            color: var(--ng-muted) !important;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p::first-line {
            color: #dc2626;
            font-weight: 750;
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
            margin: 2px 0 14px;
            padding: 16px;
            border: 1px solid #f1dadd;
            border-radius: 14px;
            background: linear-gradient(145deg, #fff7f7 0%, #ffffff 100%);
            box-shadow: 0 6px 16px rgba(239, 68, 68, 0.06);
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
            border-radius: 16px;
            background: var(--ng-surface);
            box-shadow: 0 6px 22px rgba(15, 23, 42, 0.045);
            transition: border-color 160ms ease, box-shadow 160ms ease;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:hover {
            border-color: #dbe1e8;
            box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
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
        .module-title::after {
            display: block;
            width: 34px;
            height: 3px;
            margin-top: 9px;
            border-radius: 999px;
            background: var(--ng-primary);
            content: "";
        }
        .module-subtitle {
            margin: -8px 0 16px;
            color: var(--ng-muted);
            font-size: 14px;
            line-height: 1.55;
        }
        .input-hint {
            display: inline-flex;
            float: right;
            margin: 2px 0 8px;
            padding: 5px 9px;
            border: 1px solid #e2e8f0;
            border-radius: 999px;
            background: #f8fafc;
            color: var(--ng-subtle);
            font-size: 12px;
            line-height: 1.3;
        }
        .assistant-panel-heading {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin: 2px 0 12px;
        }
        .assistant-panel-heading strong { color: var(--ng-text); font-size: 16px; }
        .assistant-panel-heading div span { display: block; margin-top: 3px; color: var(--ng-muted); font-size: 12px; }
        .assistant-progress { padding: 5px 9px; border-radius: 999px; background: #f1f5f9; color: var(--ng-muted); font-size: 12px; }
        .assistant-preview {
            min-height: 360px;
            padding: 24px;
            border: 1px solid var(--ng-border);
            border-radius: 14px;
            background: #ffffff;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.8), 0 8px 24px rgba(15,23,42,.04);
        }
        .assistant-preview-label { margin-bottom: 8px; color: var(--ng-subtle); font-size: 11px; font-weight: 700; letter-spacing: .08em; }
        .assistant-preview-label.body-label { margin-top: 24px; padding-top: 20px; border-top: 1px solid #eef2f6; }
        .assistant-title-text { color: var(--ng-text); font-size: 21px; font-weight: 750; line-height: 1.55; }
        .assistant-body-text { color: var(--ng-text); font-size: 15px; line-height: 1.95; }
        .assistant-empty { color: var(--ng-subtle); }
        .assistant-mark { padding: 2px 3px; border-radius: 4px; color: inherit !important; box-decoration-break: clone; -webkit-box-decoration-break: clone; }
        .assistant-mark.high { background: #fee2e2; box-shadow: inset 0 -2px 0 #ef4444; }
        .assistant-mark.medium { background: #fef3c7; box-shadow: inset 0 -2px 0 #f59e0b; }
        .assistant-mark.info { background: #dbeafe; box-shadow: inset 0 -2px 0 #3b82f6; }
        .assistant-mark.selected { outline: 2px solid rgba(239,68,68,.25); outline-offset: 2px; }
        .assistant-mark.applied { background: #dcfce7; box-shadow: inset 0 -2px 0 #22c55e; }
        .optimization-summary { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between; margin: 4px 0 16px; padding: 16px 18px; border: 1px solid #fecaca; border-radius: 14px; background: linear-gradient(135deg,#fff 0%,#fff7f7 100%); }
        .optimization-summary strong { color: var(--ng-text); font-size: 17px; }
        .optimization-summary-tags { display: flex; flex-wrap: wrap; gap: 7px; }
        .optimization-summary-tags span { padding: 6px 9px; border: 1px solid #e5e7eb; border-radius: 999px; background: #fff; color: var(--ng-muted); font-size: 11px; font-weight: 650; }
        .comparison-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 16px; margin-bottom: 16px; }
        .comparison-card { min-height: 340px; padding: 20px; border: 1px solid var(--ng-border); border-radius: 16px; background: #fff; box-shadow: 0 8px 24px rgba(15,23,42,.05); }
        .comparison-card.after { border-color: #bbf7d0; background: linear-gradient(180deg,#fff 0%,#fbfffc 100%); }
        .comparison-card-heading { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; }
        .comparison-card-heading strong { color: var(--ng-text); font-size: 16px; }
        .comparison-card-heading span { color: var(--ng-subtle); font-size: 11px; }
        .comparison-section-label { margin-bottom: 7px; color: var(--ng-subtle); font-size: 11px; font-weight: 700; letter-spacing: .08em; }
        .comparison-section-label.body { margin-top: 22px; padding-top: 18px; border-top: 1px solid #eef2f6; }
        .comparison-title { color: var(--ng-text); font-size: 19px; font-weight: 750; line-height: 1.6; }
        .comparison-body { color: var(--ng-text); font-size: 14px; line-height: 1.9; }
        .comparison-before-mark { padding: 2px 3px; border-radius: 4px; background: #fee2e2; color: inherit !important; box-shadow: inset 0 -2px 0 #ef4444; box-decoration-break: clone; -webkit-box-decoration-break: clone; }
        .comparison-after-mark { padding: 2px 3px; border-radius: 4px; background: #dcfce7; color: inherit !important; box-shadow: inset 0 -2px 0 #22c55e; box-decoration-break: clone; -webkit-box-decoration-break: clone; }
        .assistant-detail-card { min-height: 360px; padding: 22px; border: 1px solid var(--ng-border); border-radius: 14px; background: #fff; box-shadow: 0 10px 28px rgba(15,23,42,.06); }
        .assistant-detail-title { margin-bottom: 20px; color: var(--ng-text); font-size: 18px; font-weight: 750; }
        .assistant-detail-block { margin-bottom: 18px; }
        .assistant-detail-block > span, .assistant-detail-meta span, .assistant-suggestion span { display: block; margin-bottom: 6px; color: var(--ng-subtle); font-size: 11px; font-weight: 650; }
        .assistant-detail-block strong, .assistant-detail-meta strong { color: var(--ng-text); font-size: 14px; line-height: 1.6; }
        .assistant-detail-block p { margin: 0; color: var(--ng-muted); font-size: 13px; line-height: 1.7; }
        .assistant-detail-meta { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 18px; }
        .assistant-detail-meta > div { padding: 10px 12px; border-radius: 10px; background: #f8fafc; }
        .assistant-detail-meta .severity-high { color: #dc2626 !important; }
        .assistant-detail-meta .severity-medium { color: #b45309 !important; }
        .assistant-detail-meta .severity-info { color: #2563eb !important; }
        .assistant-suggestion { padding: 14px; border: 1px solid #fecaca; border-radius: 11px; background: #fff7f7; }
        .assistant-suggestion strong { color: #b42318; font-size: 14px; line-height: 1.65; }
        .st-key-assistant_legacy_action { display: none !important; }
        .optimization-mode-card { min-height: 96px; padding: 14px 16px; border: 1px solid var(--ng-border); border-radius: 12px; background: #fff; }
        .optimization-mode-card strong { display: block; color: var(--ng-text); font-size: 14px; }
        .optimization-mode-card span { display: block; margin-top: 5px; color: var(--ng-muted); font-size: 12px; line-height: 1.5; }
        .before-after-label { margin-bottom: 7px; color: var(--ng-subtle); font-size: 11px; font-weight: 700; letter-spacing: .08em; }
        .before-after-content { min-height: 180px; padding: 16px; border: 1px solid var(--ng-border); border-radius: 12px; background: #fff; color: var(--ng-text); font-size: 14px; line-height: 1.75; }
        .preflight-checks { display: flex; flex-wrap: wrap; gap: 8px; margin: -4px 0 20px; }
        .preflight-checks span { padding: 7px 10px; border: 1px solid var(--ng-border); border-radius: 999px; background: #fff; color: var(--ng-muted); font-size: 12px; }
        .preflight-checks span::before { margin-right: 5px; color: var(--ng-primary); content: "✓"; font-weight: 800; }
        .readiness-score-card { display: grid; grid-template-columns: .75fr 1.25fr; gap: 24px; align-items: center; margin: 10px 0 18px; padding: 24px 26px; border: 1px solid #fecaca; border-radius: 16px; background: linear-gradient(135deg,#fff 0%,#fff7f7 100%); box-shadow: 0 10px 26px rgba(239,68,68,.07); }
        .readiness-score-card > div:first-child span { display: block; color: var(--ng-muted); font-size: 13px; font-weight: 650; }
        .readiness-score-card > div:first-child strong { display: block; margin-top: 4px; color: var(--ng-primary); font-size: 44px; line-height: 1.1; }
        .readiness-score-card small { color: var(--ng-subtle); font-size: 18px; }
        .readiness-score-copy { padding-left: 24px; border-left: 1px solid #fecaca; }
        .readiness-score-copy strong { color: var(--ng-text); font-size: 18px; }
        .readiness-score-copy p { margin: 7px 0 0; color: var(--ng-muted); font-size: 13px; line-height: 1.6; }
        .preflight-analysis-card { min-height: 320px; padding: 20px; border: 1px solid var(--ng-border); border-radius: 14px; background: #fff; box-shadow: 0 7px 22px rgba(15,23,42,.045); }
        .preflight-card-icon { margin-bottom: 12px; font-size: 24px; }
        .preflight-analysis-card > strong { display: block; color: var(--ng-text); font-size: 16px; }
        .preflight-score { display: block; margin: 9px 0; color: var(--ng-primary); letter-spacing: 3px; }
        .preflight-kicker { display: block; margin-top: 7px; color: var(--ng-subtle); font-size: 11px; }
        .preflight-analysis-card p { margin: 12px 0; color: var(--ng-muted); font-size: 13px; line-height: 1.65; }
        .preflight-analysis-card ul { margin: 12px 0 0; padding: 12px 0 0; border-top: 1px solid #eef2f6; list-style: none; }
        .preflight-analysis-card li { margin: 8px 0; color: var(--ng-text); font-size: 12px; line-height: 1.55; }
        .interaction-list li b { display: inline-block; min-width: 38px; margin-right: 5px; color: var(--ng-primary); }
        .consultant-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 14px; margin: 16px 0 18px; }
        .consultant-card { padding: 20px; border: 1px solid var(--ng-border); border-radius: 15px; background: #fff; box-shadow: 0 8px 22px rgba(15,23,42,.045); }
        .consultant-card.opportunity { border-color: #fecaca; background: linear-gradient(135deg,#fff 0%,#fff7f7 100%); }
        .consultant-card > strong { display: block; margin-bottom: 14px; color: var(--ng-text); font-size: 16px; }
        .consultant-row { margin-top: 11px; padding-top: 11px; border-top: 1px solid #eef2f6; }
        .consultant-row:first-of-type { margin-top: 0; padding-top: 0; border-top: 0; }
        .consultant-row span { display: block; margin-bottom: 4px; color: var(--ng-subtle); font-size: 11px; font-weight: 700; }
        .consultant-row p { margin: 0; color: var(--ng-text); font-size: 13px; line-height: 1.7; }
        .consultant-row.action p { color: #b42318; font-weight: 650; }
        .preflight-optimization-card { margin-top: 18px; padding: 22px; border: 1px solid var(--ng-border); border-radius: 16px; background: #fff; box-shadow: 0 8px 24px rgba(15,23,42,.05); }
        .preflight-optimization-heading { display: flex; gap: 11px; align-items: flex-start; }
        .preflight-optimization-heading > span { font-size: 22px; }
        .preflight-optimization-heading strong { color: var(--ng-text); font-size: 17px; }
        .preflight-optimization-heading p { margin: 4px 0 0; color: var(--ng-muted); font-size: 12px; }
        .preflight-copy-grid { display: grid; grid-template-columns: 1fr 34px 1fr; gap: 10px; align-items: stretch; margin-top: 18px; }
        .preflight-copy-grid > div:not(.preflight-arrow) { padding: 15px; border: 1px solid var(--ng-border); border-radius: 11px; background: #f8fafc; }
        .preflight-copy-grid .recommended { border-color: #fecaca !important; background: #fff7f7 !important; }
        .preflight-copy-grid span { color: var(--ng-subtle); font-size: 11px; font-weight: 700; }
        .preflight-copy-grid p { margin: 7px 0 0; color: var(--ng-text); font-size: 14px; font-weight: 650; line-height: 1.7; }
        .preflight-arrow { display: flex; align-items: center; justify-content: center; color: var(--ng-subtle); font-size: 18px; }
        .preflight-reasons { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 14px; }
        .preflight-reasons span { margin-right: 2px; color: var(--ng-muted); font-size: 11px; font-weight: 700; }
        .preflight-reasons em { padding: 5px 8px; border-radius: 999px; background: #f1f5f9; color: var(--ng-muted); font-size: 11px; font-style: normal; }
        .workspace-image-insight { margin: 16px 0 20px; padding: 18px; border: 1px solid #dbeafe; border-radius: 14px; background: linear-gradient(135deg,#fff 0%,#f8fbff 100%); }
        .workspace-image-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
        .workspace-image-heading div { display: flex; align-items: center; gap: 8px; }
        .workspace-image-heading strong { color: var(--ng-text); font-size: 16px; }
        .workspace-image-heading em { padding: 5px 9px; border-radius: 999px; background: #ecfdf5; color: #047857; font-size: 11px; font-style: normal; font-weight: 700; }
        .workspace-image-insight > p { margin: 7px 0 14px; color: var(--ng-muted); font-size: 12px; }
        .workspace-image-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 10px; }
        .workspace-image-grid > div { padding: 12px; border: 1px solid #e5e7eb; border-radius: 10px; background: #fff; }
        .workspace-image-grid span { display: block; margin-bottom: 5px; color: var(--ng-subtle); font-size: 11px; font-weight: 650; }
        .workspace-image-grid strong { color: var(--ng-text); font-size: 12px; line-height: 1.55; }
        /* Interaction safety guard: keep Streamlit/BaseWeb controls above decorative CSS. */
        input,
        textarea,
        button,
        [data-baseweb],
        .stButton,
        .stTextInput,
        .stTextArea,
        .stFileUploader,
        [data-testid="stFileUploader"],
        [data-testid="stFileUploaderDropzone"] {
            pointer-events: auto !important;
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
        .content-preview {
            margin: 8px 0 12px;
            padding: 16px 18px;
            border: 1px solid var(--ng-border);
            border-radius: 12px;
            background: #ffffff;
            color: var(--ng-text);
            line-height: 1.9;
            word-break: break-word;
        }
        .suggested-preview {
            border-color: #bbf7d0;
            background: #f0fdf4;
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
        [data-testid="stTextInput"] [data-baseweb="input"],
        [data-testid="stTextArea"] [data-baseweb="textarea"],
        [data-testid="stSelectbox"] [data-baseweb="select"] > div,
        [data-testid="stMultiSelect"] [data-baseweb="select"] > div,
        [data-testid="stNumberInput"] [data-baseweb="input"] {
            border: 1px solid #d0d5dd !important;
            border-radius: 10px !important;
            background: #ffffff !important;
            box-shadow: none !important;
        }
        [data-testid="stTextInput"] [data-baseweb="input"]:hover,
        [data-testid="stTextArea"] [data-baseweb="textarea"]:hover,
        [data-testid="stSelectbox"] [data-baseweb="select"] > div:hover,
        [data-testid="stMultiSelect"] [data-baseweb="select"] > div:hover,
        [data-testid="stNumberInput"] [data-baseweb="input"]:hover {
            border-color: #98a2b3 !important;
        }
        [data-testid="stTextInput"] [data-baseweb="input"]:focus-within,
        [data-testid="stTextArea"] [data-baseweb="textarea"]:focus-within,
        [data-testid="stSelectbox"] [data-baseweb="select"] > div:focus-within,
        [data-testid="stMultiSelect"] [data-baseweb="select"] > div:focus-within,
        [data-testid="stNumberInput"] [data-baseweb="input"]:focus-within {
            border-color: var(--ng-primary) !important;
            box-shadow: 0 0 0 2px rgba(217, 75, 87, 0.10) !important;
        }
        [data-baseweb="select"] span,
        [data-baseweb="select"] input {
            color: var(--ng-text) !important;
        }
        [data-testid="stTextInput"] label,
        [data-testid="stTextArea"] label,
        [data-testid="stSelectbox"] label,
        [data-testid="stMultiSelect"] label,
        [data-testid="stNumberInput"] label {
            color: #344054;
            font-size: 14px;
            font-weight: 600;
        }
        textarea, input {
            border-color: #d0d5dd !important;
            background: #ffffff !important;
            color: var(--ng-text) !important;
            font-size: 15px !important;
        }
        textarea::placeholder, input::placeholder {
            color: var(--ng-subtle) !important;
            opacity: 1 !important;
        }
        [data-baseweb="popover"],
        [data-baseweb="menu"],
        [role="listbox"] {
            border-color: #e5e7eb !important;
            background: #ffffff !important;
            color: var(--ng-text) !important;
        }
        [data-baseweb="menu"] li,
        [role="option"] {
            background: #ffffff !important;
            color: var(--ng-text) !important;
        }
        [data-baseweb="menu"] li:hover,
        [role="option"]:hover {
            background: #f9fafb !important;
        }
        [data-testid="stNumberInput"] button {
            border-color: #d0d5dd !important;
            background: #ffffff !important;
            color: var(--ng-text) !important;
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
            box-shadow: 0 6px 16px rgba(37, 99, 235, 0.20) !important;
            font-weight: 650 !important;
        }
        button[kind="primary"] p,
        button[kind="primary"] span,
        button[kind="primary"] svg {
            color: #ffffff !important;
            fill: currentColor;
        }
        button[kind="primary"]:hover {
            background: var(--ng-primary-hover) !important;
            border-color: var(--ng-primary-hover) !important;
            transform: translateY(-1px);
            box-shadow: 0 8px 20px rgba(37, 99, 235, 0.26) !important;
        }
        button[kind="secondary"] {
            min-height: 40px;
            border: 1px solid #d0d5dd !important;
            border-radius: 10px !important;
            background: #ffffff !important;
            color: #344054 !important;
            box-shadow: 0 2px 6px rgba(15, 23, 42, 0.04) !important;
            font-weight: 600 !important;
        }
        button[kind="secondary"] p,
        button[kind="secondary"] span {
            color: #344054 !important;
        }
        button[kind="secondary"]:hover {
            border-color: #98a2b3 !important;
            background: #f9fafb !important;
            color: var(--ng-text) !important;
            transform: translateY(-1px);
            box-shadow: 0 5px 12px rgba(15, 23, 42, 0.07) !important;
        }
        button {
            transition: transform 140ms ease, background-color 140ms ease, border-color 140ms ease, box-shadow 140ms ease !important;
        }
        [data-testid="stCheckbox"] label {
            padding: 4px 2px;
            color: var(--ng-text) !important;
        }
        [data-testid="stCheckbox"] label span,
        [data-testid="stCheckbox"] label p {
            color: var(--ng-text) !important;
        }
        [data-testid="stCheckbox"] [data-baseweb="checkbox"] > div:first-child {
            border-color: #cbd5e1 !important;
            border-radius: 6px !important;
            background: #ffffff !important;
        }
        [data-testid="stCheckbox"] input:checked + div {
            border-color: var(--ng-primary) !important;
            background: var(--ng-primary) !important;
        }
        [data-testid="stFileUploader"] {
            padding: 2px;
            border-radius: 14px;
            background: #ffffff !important;
        }
        [data-testid="stFileUploaderDropzone"] {
            border: 1px dashed #cbd5e1 !important;
            border-radius: 12px !important;
            background: #f8fafc !important;
            color: var(--ng-text) !important;
            transition: border-color 160ms ease, background-color 160ms ease;
        }
        [data-testid="stFileUploaderDropzone"]:hover {
            border-color: var(--ng-primary) !important;
            background: #fff7f7 !important;
        }
        [data-testid="stFileUploaderDropzone"] p,
        [data-testid="stFileUploaderDropzone"] span,
        [data-testid="stFileUploaderDropzoneInstructions"] {
            color: var(--ng-muted) !important;
        }
        .st-key-request_clear_content button,
        .st-key-confirm_clear_content_button button {
            border-color: #fecaca !important;
            background: #ffffff !important;
            color: #c2414d !important;
        }
        .st-key-delete_workspace_image button,
        .st-key-delete_cover_image button,
        .st-key-delete_viral_image button {
            min-height: 38px;
            border: 1px solid #fecaca !important;
            border-radius: 10px !important;
            background: #ffffff !important;
            color: #c2414d !important;
            box-shadow: none !important;
        }
        .st-key-delete_workspace_image button p,
        .st-key-delete_workspace_image button span,
        .st-key-delete_cover_image button p,
        .st-key-delete_cover_image button span,
        .st-key-delete_viral_image button p,
        .st-key-delete_viral_image button span {
            color: #c2414d !important;
        }
        .st-key-delete_workspace_image button:hover,
        .st-key-delete_cover_image button:hover,
        .st-key-delete_viral_image button:hover {
            border-color: #fca5a5 !important;
            background: #fff1f2 !important;
        }
        .st-key-load_experience_case_button button {
            border-color: #fecaca !important;
            background: #fff7f7 !important;
            color: #dc2626 !important;
            box-shadow: 0 4px 12px rgba(239, 68, 68, 0.08) !important;
        }
        .st-key-load_experience_case_button button p,
        .st-key-load_experience_case_button button span {
            color: #dc2626 !important;
        }
        .st-key-load_experience_case_button button:hover {
            border-color: #fca5a5 !important;
            background: #fef2f2 !important;
            box-shadow: 0 7px 16px rgba(239, 68, 68, 0.13) !important;
        }
        .st-key-request_clear_content button:hover,
        .st-key-confirm_clear_content_button button:hover {
            background: #fff1f2 !important;
            border-color: #fca5a5 !important;
        }
        .st-key-request_clear_content button p,
        .st-key-request_clear_content button span,
        .st-key-confirm_clear_content_button button p,
        .st-key-confirm_clear_content_button button span {
            color: #c2414d !important;
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
            border: 1px solid #e5e7eb !important;
            border-radius: 10px;
            background: #ffffff !important;
        }
        [data-testid="stExpander"] summary {
            display: flex;
            min-height: 48px;
            padding: 0.7rem 1rem;
            align-items: center;
            border-radius: 10px;
            background: #ffffff !important;
            color: var(--ng-text) !important;
            line-height: 1.5;
            transition: background-color 150ms ease;
        }
        [data-testid="stExpander"] summary:hover {
            background: #f8fafc !important;
        }
        [data-testid="stExpander"] summary p {
            margin: 0;
            color: var(--ng-text) !important;
            line-height: 1.5;
            overflow-wrap: anywhere;
        }
        [data-testid="stExpander"] summary svg,
        [data-testid="stExpander"] summary [data-testid="stIconMaterial"] {
            flex: 0 0 auto;
        }
        [data-testid="stExpanderDetails"] {
            padding: 0.4rem 1rem 0.9rem;
            background: #ffffff !important;
            color: var(--ng-text) !important;
            line-height: 1.65;
        }
        [data-testid="stAlert"],
        [data-testid="stMetric"],
        [data-testid="stDataFrame"],
        [data-testid="stForm"] {
            background-color: #ffffff !important;
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

        /* Native Streamlit text visibility safeguards. */
        .stSelectbox label,
        .stSelectbox label *,
        .stCheckbox label,
        .stCheckbox label *,
        [data-testid="stTextInput"] label,
        [data-testid="stTextInput"] label *,
        [data-testid="stTextArea"] label,
        [data-testid="stTextArea"] label *,
        [data-testid="stNumberInput"] label,
        [data-testid="stNumberInput"] label *,
        [data-testid="stMultiSelect"] label,
        [data-testid="stMultiSelect"] label * {
            color: #344054 !important;
        }
        .stSelectbox [data-baseweb="select"],
        .stSelectbox [data-baseweb="select"] *,
        [data-testid="stSelectbox"] [data-baseweb="select"],
        [data-testid="stSelectbox"] [data-baseweb="select"] *,
        [data-testid="stMultiSelect"] [data-baseweb="select"],
        [data-testid="stMultiSelect"] [data-baseweb="select"] *,
        [role="listbox"],
        [role="listbox"] *,
        [role="option"],
        [role="option"] * {
            color: var(--ng-text) !important;
        }
        .stCheckbox [data-baseweb="checkbox"] p,
        .stCheckbox [data-baseweb="checkbox"] span,
        [data-testid="stCheckbox"] [data-baseweb="checkbox"] p,
        [data-testid="stCheckbox"] [data-baseweb="checkbox"] span {
            color: #344054 !important;
        }
        .stButton button:not([kind="primary"]),
        .stButton button:not([kind="primary"]) p,
        .stButton button:not([kind="primary"]) span,
        .stButton button:not([kind="primary"]) div {
            color: #344054 !important;
        }
        input,
        textarea,
        [data-baseweb="input"] input,
        [data-baseweb="textarea"] textarea {
            color: var(--ng-text) !important;
            -webkit-text-fill-color: var(--ng-text) !important;
            opacity: 1 !important;
        }
        [data-baseweb="select"] *,
        [data-baseweb="input"] *,
        [data-baseweb="textarea"] *,
        [data-baseweb="base-input"] *,
        .stSelectbox *,
        .stTextInput *,
        .stTextArea * {
            color: #344054 !important;
            -webkit-text-fill-color: #344054 !important;
        }
        input::placeholder,
        textarea::placeholder,
        [data-baseweb="input"] input::placeholder,
        [data-baseweb="textarea"] textarea::placeholder {
            color: #98A2B3 !important;
            -webkit-text-fill-color: #98A2B3 !important;
            opacity: 1 !important;
        }
        .stButton button[kind="primary"],
        .stButton button[kind="primary"] p,
        .stButton button[kind="primary"] span,
        .stButton button[kind="primary"] div {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
        }
        .st-key-delete_workspace_image button,
        .st-key-delete_workspace_image button *,
        .st-key-delete_cover_image button,
        .st-key-delete_cover_image button *,
        .st-key-delete_viral_image button,
        .st-key-delete_viral_image button *,
        .st-key-load_experience_case_button button,
        .st-key-load_experience_case_button button *,
        .st-key-request_clear_content button,
        .st-key-request_clear_content button *,
        .st-key-confirm_clear_content_button button,
        .st-key-confirm_clear_content_button button * {
            color: #c2414d !important;
            -webkit-text-fill-color: #c2414d !important;
        }

        /* Global normal and interaction-state visibility audit. */
        :is(
            .stMarkdown,
            .stText,
            .stCaption,
            .stMetric,
            .stTabs,
            .stRadio,
            .stSelectbox,
            .stButton,
            .stCheckbox,
            .stTextInput,
            .stTextArea
        ) *,
        [data-baseweb] *,
        [data-baseweb="select"] *,
        [data-baseweb="input"] *,
        [data-baseweb="textarea"] *,
        [data-baseweb="tab"] * {
            color: #344054 !important;
            -webkit-text-fill-color: #344054 !important;
            opacity: 1 !important;
        }
        :is(
            .stMarkdown,
            .stText,
            .stCaption,
            .stMetric,
            .stTabs,
            .stRadio,
            .stSelectbox,
            .stButton,
            .stCheckbox,
            .stTextInput,
            .stTextArea,
            [data-baseweb]
        ) *:is(:hover, :focus, :active, :not(:focus), :disabled) {
            color: #344054 !important;
            -webkit-text-fill-color: #344054 !important;
            opacity: 1 !important;
        }
        input:is(:hover, :focus, :active, :not(:focus), :disabled),
        textarea:is(:hover, :focus, :active, :not(:focus), :disabled),
        label:is(:hover, :focus, :active, :not(:focus), :disabled) {
            color: #344054 !important;
            -webkit-text-fill-color: #344054 !important;
            opacity: 1 !important;
        }
        input::placeholder,
        textarea::placeholder,
        input:hover::placeholder,
        input:focus::placeholder,
        input:disabled::placeholder,
        textarea:hover::placeholder,
        textarea:focus::placeholder,
        textarea:disabled::placeholder {
            color: #98A2B3 !important;
            -webkit-text-fill-color: #98A2B3 !important;
            opacity: 1 !important;
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
            .v2-heading h1 {
                font-size: 28px;
            }
            .comparison-grid {
                grid-template-columns: 1fr;
            }
            .consultant-grid {
                grid-template-columns: 1fr;
            }
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
            .quick-entry-grid {
                grid-template-columns: 1fr;
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


def build_content_comparison(
    text: str,
    findings: list[Finding],
    items: list[LineReviewItem],
    position: str,
) -> tuple[str, str, str]:
    """Build before/after content from the existing finding and suggestion fields."""
    position_pairs = [
        (finding, item)
        for finding, item in zip(findings, items, strict=False)
        if finding.position == position and item.position == position
    ]
    position_pairs.sort(key=lambda pair: pair[0].start)
    before_fragments: list[str] = []
    after_fragments: list[str] = []
    optimized_fragments: list[str] = []
    cursor = 0
    for finding, item in position_pairs:
        if finding.start < cursor or finding.start > len(text):
            continue
        end = min(finding.end, len(text))
        unchanged = text[cursor:finding.start]
        original = text[finding.start:end]
        replacement = finding.suggestion or item.replacement_text or original
        before_fragments.extend(
            [escape(unchanged), f'<mark class="comparison-before-mark">{escape(original)}</mark>']
        )
        after_fragments.append(escape(unchanged))
        if replacement != original:
            after_fragments.append(
                f'<mark class="comparison-after-mark">{escape(replacement)}</mark>'
            )
        else:
            after_fragments.append(escape(original))
        optimized_fragments.extend([unchanged, replacement])
        cursor = end
    before_fragments.append(escape(text[cursor:]))
    after_fragments.append(escape(text[cursor:]))
    optimized_fragments.append(text[cursor:])
    empty = '<span class="assistant-empty">暂无内容</span>'
    return (
        "".join(optimized_fragments),
        "".join(before_fragments).replace("\n", "<br>") or empty,
        "".join(after_fragments).replace("\n", "<br>") or empty,
    )


def mark_review_items_handled(item_ids: tuple[str, ...]) -> None:
    """Record review progress without rewriting the user's title or body."""
    statuses = st.session_state.setdefault("line_review_statuses", {})
    statuses.update({item_id: "handled" for item_id in item_ids})
    st.session_state["workspace_notice"] = "修改方向已记录为已处理，原始内容未被自动改写。"


def continue_editing_content() -> None:
    st.session_state["workspace_notice"] = "可在上方内容准备区继续编辑标题和正文。"


def build_publish_title_suggestion(title: str, body: str, recommended_title: str = "") -> str:
    banned = ("学习状态改善", "学习者", "数理思维基础薄弱", "内容表达优化")
    if recommended_title and recommended_title.strip() != title.strip() and not any(
        term in recommended_title for term in banned
    ):
        return recommended_title.strip()
    combined = f"{title}\n{body}"
    subject = next((term for term in ("数学", "英语", "语文", "物理", "化学") if term in combined), "学习")
    stage_match = re.search(r"(小[一二三四五六]|初[一二三]|高[一二三]|小学|初中|高中)", combined)
    stage = stage_match.group(1) if stage_match else "孩子"
    if any(term in combined for term in ("成绩", "提高", "提分", "逆袭", "差生", "拖后腿")):
        pain = "成绩上不去"
    elif "错题" in combined:
        pain = "错题反复出现"
    else:
        pain = "学习方法怎么选"
    teacher_prefix = "老师总结" if any(term in combined for term in ("老师", "辅导", "教学")) else ""
    return f"{stage}{subject}{pain}？{teacher_prefix}学习关键点"


def build_problem_level_review(
    title: str,
    body: str,
    findings: list[Finding],
    recommended_title: str = "",
) -> dict[str, object]:
    combined = f"{title}\n{body}"
    title_terms = {item.term for item in findings if item.position == "标题" and item.severity != "low"}
    title_problems: list[str] = []
    if title_terms.intersection({"差生", "学渣", "后进生"}):
        title_problems.append("负面学生标签容易让家长产生抵触，也没有说明孩子具体卡在哪里。")
    if any(term in combined for term in ("保证", "一定", "逆袭", "30天提高", "提高50分")):
        title_problems.append("标题使用强结果承诺，点击感很强，但会削弱家长对内容真实性的判断。")
    if not re.search(r"(小[一二三四五六]|初[一二三]|高[一二三]|小学|初中|高中|\d{1,2}\s*[-—至到]\s*\d{1,2}\s*岁)", combined):
        title_problems.append("没有明确年级或年龄阶段，目标家长无法快速判断内容是否与自己的孩子相关。")
    if not title_problems:
        title_problems.append("标题还可以更直接地同时呈现目标家长、具体学习问题和点开后能获得的价值。")

    body_problems: list[str] = []
    opening = next((line.strip() for line in body.splitlines() if line.strip()), "")
    if opening.startswith(("我", "本人", "老师", "我们")):
        body_problems.append("正文开头先介绍创作者，没有先出现家长正在经历的具体学习场景。")
    if any(term in body for term in ("保证", "一定", "一个月后", "很多家长都")):
        body_problems.append("正文强调结果或反馈，但缺少过程、适用条件和可执行方法，可信度不足。")
    if len(body.strip()) < 80:
        body_problems.append("正文信息较短，还没有形成“具体问题—原因—方法”的完整阅读价值。")
    if not body_problems:
        body_problems.append("正文主题清楚，发布前可再确认开头是否先出现家长痛点，并尽快给出方法。")

    title_suggestion = build_publish_title_suggestion(title, body, recommended_title)
    body_suggestion = (
        "先用孩子的具体学习场景开头，例如：“孩子上课能听懂，一到考试却不会做，问题可能不在刷题量。”随后再说明原因和方法。"
        if opening.startswith(("我", "本人", "老师", "我们"))
        else "保留当前开头，再补充一个具体学习场景、判断原因和可执行步骤，让家长知道下一步怎么做。"
    )
    return {
        "count": int(bool(title_problems)) + int(bool(body_problems)),
        "title_problems": title_problems,
        "body_problems": body_problems,
        "title_suggestion": title_suggestion,
        "body_suggestion": body_suggestion,
    }


def render_writing_assistant(
    title: str,
    body: str,
    findings: list[Finding],
    items: list[LineReviewItem],
    statuses: dict[str, str],
    recommended_title: str = "",
) -> None:
    review = build_problem_level_review(title, body, findings, recommended_title)
    title_problem_html = "".join(
        f"<li>{escape(problem)}</li>" for problem in review["title_problems"]
    )
    body_problem_html = "".join(
        f"<li>{escape(problem)}</li>" for problem in review["body_problems"]
    )
    st.markdown(
        f"""
        <div class="optimization-summary">
            <strong>发现 {review['count']} 个影响发布效果的问题</strong>
        </div>
        <div class="comparison-grid">
            <div class="comparison-card before">
                <div class="comparison-card-heading"><strong>标题问题</strong><span>影响搜索与点击</span></div>
                <div class="comparison-section-label">原</div>
                <div class="comparison-title">{escape(title) or '暂未填写标题'}</div>
                <div class="comparison-section-label body">问题</div>
                <div class="comparison-body"><ol>{title_problem_html}</ol></div>
                <div class="comparison-section-label body">建议</div>
                <div class="comparison-body">{escape(str(review['title_suggestion']))}</div>
            </div>
            <div class="comparison-card after">
                <div class="comparison-card-heading"><strong>正文问题</strong><span>影响阅读与信任</span></div>
                <div class="comparison-section-label">当前开头</div>
                <div class="comparison-title">{escape(next((line.strip() for line in body.splitlines() if line.strip()), '暂未填写正文'))}</div>
                <div class="comparison-section-label body">问题</div>
                <div class="comparison-body"><ol>{body_problem_html}</ol></div>
                <div class="comparison-section-label body">建议</div>
                <div class="comparison-body">{escape(str(review['body_suggestion']))}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.button(
        "继续编辑",
        key="continue_editing_content",
        use_container_width=True,
        on_click=continue_editing_content,
    )


def build_xhs_consultant_insights(
    cover_text: str,
    analysis: dict | None,
) -> list[dict[str, str]]:
    """Translate existing cover signals into actionable Xiaohongshu decisions."""
    analysis = analysis or {}
    dimensions = analysis.get("dimensions") or {}
    suggestions = [str(item) for item in (analysis.get("suggestions") or []) if str(item).strip()]
    issues = [str(item) for item in (analysis.get("issues") or []) if str(item).strip()]
    title = st.session_state.get("draft_title", "").strip()
    body = st.session_state.get("draft_body", "").strip()
    image_description = st.session_state.get("cover_image_description", "").strip()
    visible_hook = cover_text.strip() or title or "当前封面没有可确认的主标题"
    content_basis = "、".join(
        value
        for value in (
            f"标题“{title}”" if title else "",
            f"封面文字“{cover_text.strip()}”" if cover_text.strip() else "",
            f"图片描述“{image_description}”" if image_description else "",
        )
        if value
    ) or "当前已上传的封面"
    click_current = dimensions.get("title_attraction") or (
        f"用户首先看到“{visible_hook}”，但还不能立即确认内容写给哪类家长、解决哪个具体学习问题。"
    )
    click_action = analysis.get("recommended_copy") or (
        f"把封面主标题改成“具体家长场景 + 孩子的问题 + 可获得的方法”，例如在“{visible_hook}”后补充“家长可照做的3个步骤”。"
    )
    understanding_current = "；".join(
        value for value in (
            dimensions.get("parent_pain"),
            dimensions.get("core_selling_point"),
        ) if value
    ) or f"从{content_basis}中，目标家长、使用场景和可获得的教育价值尚未同时出现。"
    trust_current = dimensions.get("marketing_risk") or (
        "当前内容更强调结果，方法过程、适用对象和案例边界呈现不足。"
        if any(token in f"{title}{cover_text}{body}" for token in ("提高", "逆袭", "保证", "一定", "必"))
        else "当前内容已有方法方向，但可验证的步骤、适用对象或真实过程还可以更明确。"
    )
    biggest_issue = issues[0] if issues else "用户在3秒内还不能同时回答“写给谁、解决什么、为什么值得点开”。"
    biggest_action = suggestions[0] if suggestions else click_action
    return [
        {
            "title": "标题问题",
            "current": click_current,
            "reason": "小红书用户先扫封面和标题；如果3秒内看不到明确人群、具体问题和点击收益，通常不会继续停留。",
            "action": click_action,
        },
        {
            "title": "正文问题",
            "current": understanding_current,
            "reason": "教育内容需要让家长快速对号入座：这是给谁的方法、适用于什么场景、看完能学会什么。缺少其中一项，就容易被当成泛经验。",
            "action": "开头前两句直接写清“适用家长 + 孩子当前表现”，随后用步骤或清单说明具体怎么做；正文每段只回答一个问题。",
        },
        {
            "title": "封面问题",
            "current": trust_current,
            "reason": "家长会同时判断方法是否可信、案例是否可验证。只强调提分结果会削弱信任，展示过程、条件和适用边界更有说服力。",
            "action": "把结果承诺改成真实过程：补充使用周期、执行步骤、观察到的变化和不适用情况；没有可核实数据时不要补造分数或家长反馈。",
        },
        {
            "title": "最先修改",
            "current": biggest_issue,
            "reason": f"当前最影响用户决策的是：{biggest_issue}",
            "action": biggest_action,
        },
    ]


def render_xhs_consultant_cards(insights: list[dict[str, str]]) -> None:
    cards = []
    for index, insight in enumerate(insights):
        opportunity_class = " opportunity" if index == len(insights) - 1 else ""
        cards.append(
            f'<div class="consultant-card{opportunity_class}">'
            f'<strong>{escape(insight["title"])}</strong>'
            f'<div class="consultant-row"><span>当前表现</span><p>{escape(insight["current"]).replace(chr(10), "<br>")}</p></div>'
            f'<div class="consultant-row"><span>原因</span><p>{escape(insight["reason"]).replace(chr(10), "<br>")}</p></div>'
            f'<div class="consultant-row action"><span>修改建议</span><p>{escape(insight["action"]).replace(chr(10), "<br>")}</p></div>'
            '</div>'
        )
    st.markdown(f'<div class="consultant-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def render_workspace_image_insight(
    has_image: bool,
    analysis: dict | None,
    image_text: str,
    creator_profile: dict[str, str] | None = None,
) -> None:
    if not has_image:
        return

    analysis = analysis or {}
    dimensions = analysis.get("dimensions") or {}
    text = image_text.strip()
    age_match = re.search(r"(\d{1,2}\s*[-—至到]\s*\d{1,2}\s*岁)", text)
    target_user = (
        f"{age_match.group(1)}孩子家长"
        if age_match
        else (creator_profile or {}).get("target_grades", "").strip()
        or dimensions.get("parent_pain")
        or "正文中描述的教育阶段家长"
    )
    service_line = next(
        (
            line.strip(" ，。？！?")
            for line in text.splitlines()
            if any(keyword in line for keyword in ("一对一", "1对1", "1v1", "带学", "辅导", "学习"))
        ),
        "",
    )
    first_impression = service_line or dimensions.get("core_selling_point") or "老师服务信息"
    emphasizes_teacher = any(keyword in text for keyword in ("教学经验", "本人", "收费", "课时"))
    has_student_problem = any(keyword in text for keyword in ("不及格", "跟不上", "基础", "卡住", "成绩"))
    if emphasizes_teacher and not has_student_problem:
        biggest_change = "当前封面突出老师经历和服务信息，但没有先呈现孩子正在遇到的具体学习困难。"
    else:
        biggest_change = (analysis.get("issues") or [dimensions.get("title_attraction") or "封面需要先呈现孩子的具体问题，再说明老师能提供什么帮助。"]) [0]
    original_copy = "，".join(line.strip() for line in text.splitlines()[:3] if line.strip()) or "当前封面主文案"
    recommended_copy = analysis.get("recommended_copy")
    if not recommended_copy:
        if age_match and any(keyword in text for keyword in ("数学", "数理", "不及格")):
            recommended_copy = f"{age_match.group(1)}孩子数理跟不上，先定位这3个基础问题"
        else:
            recommended_copy = "孩子当前学习问题是什么？用3个具体步骤说明家长可以怎么做"
    capability_available, _ = image_analysis_capability()
    read_status = (
        "已读取封面内容"
        if text
        else "等待图片识别配置"
        if not capability_available
        else "未读取到可确认的封面文字"
    )
    st.markdown(
        f"""
        <div class="workspace-image-insight">
            <div class="workspace-image-heading">
                <div><span>🖼️</span><strong>封面表现分析</strong></div>
                <em>✓ {escape(read_status)}</em>
            </div>
            <p>围绕用户第一眼能否看懂“写给谁、解决什么、为什么值得继续看”提供修改建议。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="consultant-grid">'
        f'<div class="consultant-card"><strong>1. 封面传递给谁</strong><div class="consultant-row"><p>{escape(str(target_user))}</p></div></div>'
        f'<div class="consultant-card"><strong>2. 用户第一眼看到什么</strong><div class="consultant-row"><p>{escape(str(first_impression))}</p></div></div>'
        f'<div class="consultant-card"><strong>3. 最大修改建议</strong><div class="consultant-row"><p>{escape(str(biggest_change))}</p></div></div>'
        f'<div class="consultant-card opportunity"><strong>4. 建议修改</strong><div class="consultant-row"><span>原</span><p>{escape(original_copy)}</p></div><div class="consultant-row action"><span>改</span><p>{escape(str(recommended_copy)).replace(chr(10), "<br>")}</p></div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if not text:
        available, _ = image_analysis_capability()
        if available:
            st.caption("未读取到可确认的封面文字，当前建议仅使用已获得的图片信息。")
        else:
            st.info("封面分析暂不可用。当前仍可分析标题和正文；配置图片识别后，可分析封面文字和视觉吸引力。")


def render_publish_decision_summary(
    title: str,
    body: str,
    cover_text: str,
    analysis: dict | None,
    findings: list[Finding],
    creator_profile: dict[str, str],
) -> None:
    context = build_content_context(
        title=title,
        content=body,
        cover_text=cover_text,
        cover_visual=analysis,
        creator_profile=creator_profile,
    )
    diagnosis = build_publish_diagnosis(context)
    st.markdown(
        f'<div class="consultant-grid">'
        f'<div class="consultant-card"><strong>1. 这篇内容适合发给谁</strong><div class="consultant-row"><p>{escape(diagnosis["target_user"])}</p></div></div>'
        f'<div class="consultant-card"><strong>2. 当前最大问题</strong><div class="consultant-row"><p>{escape(diagnosis["problem"])}</p></div><div class="consultant-row"><span>为什么影响发布</span><p>{escape(diagnosis["why"])}</p></div></div>'
        f'<div class="consultant-card opportunity"><strong>3. 建议优先修改</strong><div class="consultant-row action"><p>{escape(diagnosis["priority"])}</p></div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _finding_key(finding: Finding, display_position: str) -> str:
    payload = f"{display_position}|{finding.term}|{finding.start}|{finding.end}|{finding.category}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def build_top_audit_issues(
    findings: list[Finding],
    cover_findings: list[Finding],
    diagnosis: dict[str, str],
    limit: int = 3,
) -> list[dict[str, str]]:
    severity_order = {"high": 0, "medium": 1, "low": 3}
    candidates: list[dict[str, str]] = []
    for finding, position in [
        *((item, item.position) for item in findings),
        *((item, "封面") for item in cover_findings),
    ]:
        candidates.append(
            {
                "position": position,
                "problem": f"“{finding.term}”：{finding.reason}",
                "suggestion": finding.suggestion or "删除、弱化或改为可验证的具体表达",
                "priority": "P0" if finding.severity == "high" else "P1" if finding.severity == "medium" else "P2",
                "order": str(severity_order.get(finding.severity, 4)),
            }
        )
    if diagnosis.get("problem"):
        candidates.append(
            {
                "position": "内容质量",
                "problem": diagnosis["problem"],
                "suggestion": diagnosis.get("priority", "按具体用户场景补充内容"),
                "priority": "P1",
                "order": "2",
            }
        )
    candidates.sort(key=lambda item: item["order"])
    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in candidates:
        identity = (item["position"], item["problem"])
        if identity in seen:
            continue
        seen.add(identity)
        unique.append({key: value for key, value in item.items() if key != "order"})
        if len(unique) >= limit:
            break
    return unique


def build_audit_feedback(
    findings: list[Finding],
    cover_findings: list[Finding],
    diagnosis: dict[str, str] | None = None,
) -> str:
    def problem_lines(items: list[Finding]) -> list[str]:
        return [f"- “{item.term}”：{item.reason}" for item in items] or ["- 未发现明确问题"]

    all_items = [*findings, *cover_findings]
    risk_lines = list(
        dict.fromkeys(f"- {item.category}：{item.reason}" for item in all_items)
    ) or ["- 未发现明确合规风险，建议发布前人工复核"]
    suggestion_lines = list(
        dict.fromkeys(
            [
                f"- {item.position}“{item.term}”："
                f"{item.suggestion or '删除、弱化或改为可验证的具体表达'}"
                for item in findings
            ]
            + [
                f"- 封面“{item.term}”："
                f"{item.suggestion or '删除、弱化或改为可验证的具体表达'}"
                for item in cover_findings
            ]
        )
    )
    if not suggestion_lines:
        suggestion_lines = ["- 当前没有明确修改项"]
    sections = (
        ("标题问题", problem_lines([item for item in findings if item.position == "标题"])),
        ("正文问题", problem_lines([item for item in findings if item.position == "正文"])),
        ("封面问题", problem_lines(cover_findings)),
        ("风险说明", risk_lines),
        ("修改建议", suggestion_lines),
    )
    return "\n\n".join(f"{title}\n" + "\n".join(lines) for title, lines in sections)


def render_audit_highlights(
    title: str,
    body: str,
    cover_text: str,
    findings: list[Finding],
    cover_findings: list[Finding],
) -> None:
    st.markdown("#### 原始内容与可替代表达")
    st.caption("右侧只替换规则命中的词语或问题表达，其余标题、正文和封面文字保持不变。")
    for label, text, items, source_position in (
        ("标题", title, [item for item in findings if item.position == "标题"], "标题"),
        ("正文", body, [item for item in findings if item.position == "正文"], "正文"),
        ("封面", cover_text, cover_findings, "正文"),
    ):
        if not text.strip() and not items:
            continue
        st.markdown(f"**{label}**")
        original_html = build_highlighted_text(text, items, source_position)
        suggested_html = build_suggested_text_html(text, items, source_position)
        original_column, suggested_column = st.columns(2, gap="medium")
        with original_column:
            st.caption("修改前")
            st.markdown(
                f'<div class="content-preview">{original_html or "暂无内容"}</div>',
                unsafe_allow_html=True,
            )
        with suggested_column:
            st.caption("建议表达")
            st.markdown(
                f'<div class="content-preview suggested-preview">{suggested_html}</div>',
                unsafe_allow_html=True,
            )
        if items:
            columns = st.columns(min(3, len(items)))
            for index, finding in enumerate(items):
                finding_key = _finding_key(finding, label)
                if columns[index % len(columns)].button(
                    f"查看：{finding.term}",
                    key=f"audit_finding_{finding_key}",
                    use_container_width=True,
                ):
                    st.session_state["selected_audit_finding"] = (label, finding_key)

    selected = st.session_state.get("selected_audit_finding")
    selectable = [
        *((item, item.position) for item in findings),
        *((item, "封面") for item in cover_findings),
    ]
    chosen = next(
        (
            (item, position)
            for item, position in selectable
            if selected == (position, _finding_key(item, position))
        ),
        selectable[0] if selectable else None,
    )
    if chosen:
        finding, position = chosen
        st.markdown("#### 问题详情")
        st.write(f"**位置：** {position}")
        st.write(f"**问题：** {finding.term}")
        st.write(f"**类型：** {finding.category}")
        st.write(f"**优先级：** {'P0' if finding.severity == 'high' else 'P1' if finding.severity == 'medium' else 'P2'}")
        st.write(f"**风险说明：** {finding.reason}")
        st.write(f"**修改建议：** {finding.suggestion or '删除、弱化或改为可验证的具体表达'}")
    else:
        st.success("标题、正文和封面未命中当前规则库中的明确问题。")


def image_analysis_capability() -> tuple[bool, str]:
    engine = get_available_ocr_engine()
    if engine != "unavailable":
        return True, "OCR"
    if is_vision_text_available():
        return True, "Vision"
    return False, "None"


def is_development_mode() -> bool:
    return os.getenv("NOTEGUARD_DEBUG", "").strip().lower() in {"1", "true", "yes"} or os.getenv(
        "APP_ENV", ""
    ).strip().lower() in {"dev", "development"}


def render_image_analysis_status(cover_text: str = "") -> None:
    available, source = image_analysis_capability()
    if cover_text.strip():
        st.success("图片文字已识别，并已进入内容审核。")
    elif st.session_state.get("cover_ocr_status") == "failed" or not available:
        st.error("图片文字识别失败，请检查OCR环境")
        diagnostic_error = str(st.session_state.get("cover_ocr_error", "")).strip()
        if diagnostic_error:
            with st.expander("OCR错误详情", expanded=True):
                st.code(diagnostic_error, language=None)
    if is_development_mode():
        actual_source = st.session_state.get("cover_ocr_engine", "None")
        st.caption(f"图片识别来源：{actual_source}")
        st.code(cover_text.strip() or "（未识别到文字）", language=None)


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


def build_suggested_text_html(text: str, findings: list[Finding], position: str) -> str:
    """Render a minimal rule-based alternative while preserving all unmatched text."""
    replacements = sorted(
        [
            item
            for item in findings
            if item.position == position and item.suggestion
        ],
        key=lambda item: item.start,
    )
    if not replacements:
        return escape(text or "暂无可替代表达").replace("\n", "<br>")

    fragments: list[str] = []
    cursor = 0
    for finding in replacements:
        if finding.start < cursor or finding.start < 0 or finding.end > len(text):
            continue
        fragments.append(escape(text[cursor:finding.start]))
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
        available, _ = image_analysis_capability()
        if available:
            st.info("未读取到可确认的图片文字，可在下方补充。")
        else:
            st.info("封面分析暂不可用。当前仍可分析标题和正文；配置图片识别后，可分析封面文字和视觉吸引力。")
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


def render_publish_readiness_report(
    current_copy: str,
    analysis: dict | None,
    error: str,
) -> None:
    st.markdown('<div class="module-eyebrow">内容审核中的封面分析</div>', unsafe_allow_html=True)
    if error:
        st.warning(f"封面分析暂未完成：{error}")
        return
    if not analysis:
        st.info("上传封面并补充可用信息后，将从点击、理解、信任和最大提升机会四个方向给出可执行建议。")
        return

    score = int(analysis.get("score", 0))
    readiness_label = "准备较充分" if score >= 80 else "具备基础" if score >= 60 else "建议优化后发布"

    st.markdown(
        f"""
        <div class="readiness-score-card">
            <div>
                <span>📊 发布准备度</span>
                <strong>{score}<small>/100</small></strong>
            </div>
            <div class="readiness-score-copy">
                <strong>{readiness_label}</strong>
                <p>基于标题、封面和正文进行发布前检查，不是流量预测。</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_xhs_consultant_cards(build_xhs_consultant_insights(current_copy, analysis))
    if not current_copy.strip():
        st.caption("未识别到明显封面文字，分析已继续结合标题、正文和图片描述完成；补充文字后可获得更具体的封面文案建议。")


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


def build_backend_image_analysis(
    cover_text: str,
    analysis: dict | None,
    creator_profile: dict[str, str],
    title: str,
    body: str,
) -> dict:
    context = build_content_context(
        title=title,
        content=body,
        cover_text=cover_text,
        cover_visual=analysis,
        creator_profile=creator_profile,
    )
    return {
        **context["cover_visual"],
        "title": context["title"],
        "content": context["content"],
        "cover_text": context["cover_text"],
        "cover_visual": context["cover_visual"],
        "creator_profile": context["creator_profile"],
        "visual_topic": context["visual_topic"],
        "target_user": context["target_user"],
        "pain_point": context["pain_point"],
    }


def build_title_generation_context(body: str, backend_analysis: dict | None = None) -> str:
    backend_analysis = backend_analysis or {}
    cover_text = str(backend_analysis.get("cover_text", "")).strip()
    ocr_text = "\n".join(st.session_state.get("cover_ocr_lines", [])).strip()
    image_description = st.session_state.get("cover_image_description", "").strip()
    cover_analysis = backend_analysis or st.session_state.get("cover_analysis") or {}
    dimensions = cover_analysis.get("dimensions") or {}
    image_signals = "；".join(
        str(dimensions.get(key, "")).strip()
        for key in ("parent_pain", "core_selling_point", "visual_hierarchy", "mobile_readability")
        if str(dimensions.get(key, "")).strip()
    )
    sections = [f"正文内容：\n{body.strip()}"]
    if cover_text:
        sections.append(f"封面确认文字：\n{cover_text}")
    elif ocr_text:
        sections.append(f"封面识别文字：\n{ocr_text}")
    if image_description:
        sections.append(f"图片内容描述：\n{image_description}")
    if image_signals:
        sections.append(f"封面视觉分析：\n{image_signals}")
    return "\n\n".join(sections)


def render_title_candidate_reviews(
    reviews: list[TitleCandidateReview],
    creator_profile: dict[str, str],
    current_title: str,
    current_body: str,
    backend_analysis: dict | None = None,
) -> None:
    title_types = ["痛点型", "好奇型", "干货型", "老师经验型", "家长共鸣型"]
    audience = "、".join(
        value.strip()
        for value in (
            creator_profile.get("target_grades", ""),
            creator_profile.get("target_students", ""),
        )
        if value.strip()
    ) or "正文中描述的家长与学生"
    subjects = creator_profile.get("subjects", "").strip() or "正文中的学科、年级和学习问题"
    cover_analysis = backend_analysis or st.session_state.get("cover_analysis") or {}
    dimensions = cover_analysis.get("dimensions") or {}
    audience = cover_analysis.get("target_user") or audience
    pain_point = cover_analysis.get("pain_point") or dimensions.get("parent_pain") or "标题直接呈现正文中的具体学习场景与家长困扰"
    click_reason = dimensions.get("core_selling_point") or "用方法、步骤或清单说明用户点击后能获得什么"
    content_positioning = dimensions.get("core_selling_point") or (
        f"围绕{subjects}，为{audience}提供可执行的学习方法"
    )
    current_problem = dimensions.get("title_attraction") or (
        "当前标题与正文主题相关，但目标用户、搜索词或用户点开后能获得的具体价值还可以更明确。"
    )
    st.markdown("#### 标题优化报告")
    report_left, report_right = st.columns(2)
    with report_left:
        st.markdown(f"**当前标题**  \n{escape(current_title or '暂未填写标题')}")
        st.markdown(f"**内容定位**  \n{escape(content_positioning)}")
    with report_right:
        st.markdown(f"**目标用户**  \n{escape(audience)}")
        st.markdown(f"**存在问题**  \n{escape(current_problem)}")
    if not reviews:
        return
    primary = reviews[0]
    st.markdown("#### 推荐标题")
    before_title, arrow, after_title = st.columns([1, 0.08, 1], gap="small")
    with before_title:
        st.caption("原标题")
        st.markdown(f"**{escape(current_title or '暂未填写标题')}**")
    with arrow:
        st.markdown("<div style='padding-top:34px;text-align:center;color:#98a2b3'>→</div>", unsafe_allow_html=True)
    with after_title:
        st.caption("推荐标题")
        st.markdown(f"**{escape(primary.safe_title)}**")
    st.markdown("**为什么这样改**")
    st.markdown(
        "\n".join(
            [
                f"- 目标用户：{audience}",
                f"- 内容痛点：{pain_point}",
                f"- 搜索关键词：{subjects}",
                f"- 用户点击后能获得：{click_reason}",
            ]
        )
    )
    render_title_copy_button(primary.safe_title, 1, label="复制推荐标题")
    st.markdown("#### 其他发布测试方案")
    for index, review in enumerate(reviews[1:], start=2):
        title_type = title_types[index - 1] if index <= len(title_types) else "标题候选"
        with st.container(border=True):
            st.caption(f"标题方案 {index} · {title_type}")
            st.markdown(f"**{escape(review.safe_title)}**")
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


def render_generated_note(note: dict, original_title: str = "", original_body: str = "") -> None:
    result_key = note.get("request_key", "generated")[:12]
    publish_title = note["titles"][0] if note.get("titles") else original_title
    publish_body = note.get("body", "")
    tags = note.get("tags", [])
    action = str(note.get("action", "")).strip()
    comment_question = str(note.get("comment_question", "")).strip()
    if not comment_question:
        question_match = re.search(r"([^。！？\n]*[？?])", action)
        comment_question = question_match.group(1).strip() if question_match else "你更想先解决哪一个具体学习问题？"
    st.caption("以下内容根据当前图片、文字素材和创作者资料生成，不是对原文的简单扩写。")
    if note.get("image_content_type"):
        st.caption(f"图片内容类型：{note['image_content_type']} · 已按对应小红书结构生成")
    with st.container(border=True):
        st.markdown("#### 标题")
        st.markdown(f"**{escape(publish_title)}**")
        if note.get("cover_copy"):
            st.markdown("#### 封面文案")
            st.write(note["cover_copy"])
        st.markdown("#### 正文")
        st.markdown(escape(publish_body).replace("\n", "  \n"))
        st.markdown("#### 标签")
        st.write(" ".join(tags) if tags else "未生成标签")
        st.markdown("#### 行动引导")
        st.write(action or "未生成行动引导")
        st.markdown("#### 评论区问题")
        st.write(comment_question)
    copy_body, copy_all, regenerate = st.columns(3)
    with copy_body:
        render_clipboard_button(
            publish_body,
            f"copy-generated-body-{result_key}",
            "复制正文",
            "正文已复制",
        )
    with copy_all:
        render_clipboard_button(
            note.get("publish_text", ""),
            f"copy-generated-all-{result_key}",
            "复制完整发布版",
            "发布版已复制",
        )
    with regenerate:
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
    text_result = analysis if isinstance(analysis, dict) else {}
    image_result = image_analysis if isinstance(image_analysis, dict) else {}
    title_result = (
        text_result.get("title_analysis", {})
        if isinstance(text_result.get("title_analysis"), dict)
        else {}
    )
    structure_result = (
        text_result.get("structure_analysis", {})
        if isinstance(text_result.get("structure_analysis"), dict)
        else {}
    )
    viral_reasons = text_result.get("viral_reasons", [])
    if not isinstance(viral_reasons, list):
        viral_reasons = []
    suggestions = text_result.get("suggestions", [])
    if not isinstance(suggestions, list):
        suggestions = []
    conversion_elements = image_result.get("conversion_elements", [])
    if not isinstance(conversion_elements, list):
        conversion_elements = [conversion_elements] if conversion_elements else []

    def brief(value: object, fallback: str = "现有拆解信息不足", limit: int = 72) -> str:
        if isinstance(value, list):
            content = "；".join(str(item).strip() for item in value if str(item).strip())
        else:
            content = str(value or "").strip()
        if not content:
            return fallback
        first_sentence = re.split(r"(?<=[。！？；])", content, maxsplit=1)[0].strip()
        return first_sentence if len(first_sentence) <= limit else first_sentence[: limit - 1].rstrip() + "…"

    pain_point = title_result.get("pain_point") or image_result.get("user_pain_expression")
    body_structure = "；".join(
        str(structure_result.get(key) or "").strip()
        for key in ("opening", "middle", "ending")
        if str(structure_result.get(key) or "").strip()
    )
    conversion_summary = "、".join(
        str(item).strip() for item in conversion_elements if str(item).strip()
    ) or structure_result.get("ending")
    trust_element = image_result.get("trust_building")
    def core_fragment(value: object) -> str:
        return brief(value, "", 72).rstrip("，。！？； ")[:8]

    summary_parts = [
        f"抓住{core_fragment(pain_point)}" if pain_point else "",
        f"用{core_fragment(trust_element)}建立信任" if trust_element else "",
        f"以{core_fragment(conversion_summary)}促进行动" if conversion_summary else "",
    ]
    core_summary = "，".join(part for part in summary_parts if part)
    if core_summary:
        core_summary += "。"
    else:
        core_summary = brief(viral_reasons[0] if viral_reasons else "")
    if len(core_summary) > 35:
        core_summary = core_summary[:34].rstrip("，。； ") + "。"
    target_audience = title_result.get("target_audience")
    scene_type = "招生转化" if conversion_elements else "知识分享 / 经验复盘"
    suitable_scene = " · ".join(
        part for part in (str(target_audience or "").strip(), scene_type) if part
    )
    trust_reason = trust_element or next(
        (
            reason
            for reason in viral_reasons
            if any(keyword in str(reason) for keyword in ("信任", "老师", "案例", "经验", "证明"))
        ),
        "现有拆解未明确说明信任来源",
    )
    image_template = image_result.get("reusable_template") or image_result.get("information_hierarchy")
    title_template = text_result.get("copyable_template") or title_result.get("click_attraction")
    body_template = body_structure
    click_factors = image_result.get("click_factors", [])
    if not isinstance(click_factors, list):
        click_factors = [click_factors] if click_factors else []
    avoid_copying = image_result.get("avoid_copying", [])
    if not isinstance(avoid_copying, list):
        avoid_copying = [avoid_copying] if avoid_copying else []
    design_role = next(
        (str(item).strip() for item in click_factors if str(item).strip()),
        title_result.get("click_attraction"),
    )

    st.markdown("### 为什么有效")
    with st.container(border=True):
        st.caption("分析依据：基于OCR文字、图片尺寸和已有信息推断，需结合原图人工复核。")
        visual_columns = st.columns(3, gap="medium")
        for column, (label, value) in zip(
            visual_columns,
            (
                ("第一眼吸引点", image_result.get("first_glance") or design_role),
                ("用户心理", pain_point),
                ("信任来源", trust_reason),
            ),
        ):
            with column:
                with st.container(border=True):
                    st.caption(label)
                    st.write(brief(value, limit=50))

    st.markdown("### 爆款核心")
    with st.container(border=True):
        st.caption("一句话总结")
        st.subheader(core_summary)
        st.write(f"**适用场景：** {suitable_scene or '教育内容运营复盘'}")
        if text_result.get("score") is not None:
            st.caption(
                f"内容研究参考 {text_result['score']}/100 · 根据结构完整度、痛点表达和转化设计进行参考分析，不代表真实流量预测。"
            )

    collection_checks = (
        ("痛点明确", bool(str(pain_point or "").strip()), brief(pain_point)),
        (
            "信任建立",
            bool(str(trust_reason or "").strip()) and "未明确" not in str(trust_reason),
            brief(trust_reason),
        ),
        ("转化路径", bool(str(conversion_summary or "").strip()), brief(conversion_summary)),
    )
    collection_score = sum(passed for _, passed, _ in collection_checks)
    star_count = round(collection_score / len(collection_checks) * 5)
    star_display = "★" * star_count + "☆" * (5 - star_count)
    st.markdown("### 收藏价值评分")
    collection_columns = st.columns(4, gap="small")
    collection_columns[0].metric("收藏价值", star_display)
    for column, (label, passed, reason) in zip(collection_columns[1:], collection_checks):
        with column:
            with st.container(border=True):
                st.caption(label)
                st.write(("★ " if passed else "☆ ") + reason)

    st.markdown("### 三个可复制点")
    copy_columns = st.columns(3, gap="medium")
    for column, (label, value) in zip(
        copy_columns,
        (
            ("① 用户痛点", pain_point),
            ("② 内容结构", body_structure),
            ("③ 转化方式", conversion_summary),
        ),
    ):
        with column:
            with st.container(border=True):
                st.caption(label)
                st.write(brief(value))

    st.markdown("### 可复用方法")
    default_avoid = brief(avoid_copying or ["个人身份", "虚假效果承诺", "未经验证的数据"])
    reusable_methods = (
        (
            "图片模板",
            suitable_scene or "教育内容封面复盘",
            str(image_template or "主标题：[用户痛点]\n身份背书：[真实身份/经验]\n行动信息：[已核实的服务入口]"),
            brief(image_result.get("first_glance") or image_template),
            default_avoid,
        ),
        (
            "标题正文模板",
            suitable_scene or "教育内容标题与正文复盘",
            f"标题：{brief(title_template)}\n正文：{brief(body_template)}",
            f"原标题：{str(st.session_state.get('viral_note_title') or '当前案例标题').strip()}\n开头：{brief(structure_result.get('opening'))}",
            "不要照搬原案例身份、课程名称和未经验证的结果数据",
        ),
        (
            "转化模板",
            suitable_scene or "教育内容转化设计",
            "用户痛点 → 建立信任 → 展示真实结果 → 行动入口",
            brief(conversion_summary),
            "不要照搬价格、联系方式或效果承诺",
        ),
    )
    reuse_columns = st.columns(3, gap="medium")
    for index, (column, method) in enumerate(zip(reuse_columns, reusable_methods), start=1):
        method_type, method_scene, template_text, example_text, avoid_text = method
        with column:
            with st.container(border=True):
                st.caption("方法类型")
                st.write(f"**{method_type}**")
                st.caption("适用场景")
                st.write(brief(method_scene))
                st.caption("可复制模板")
                st.write(template_text)
                st.caption("示例")
                st.write(example_text)
                with st.expander("查看注意事项", expanded=False):
                    st.caption("不建议照搬")
                    st.write(avoid_text)
                render_clipboard_button(
                    template_text,
                    f"copy-live-viral-template-{index}",
                    "复制模板",
                    "模板已复制",
                )

    full_review_text = "\n".join(
        [
            "爆款核心：",
            core_summary,
            "",
            "三个复制点：",
            f"1. 用户痛点：{brief(pain_point)}",
            f"2. 内容结构：{brief(body_structure)}",
            f"3. 转化方式：{brief(conversion_summary)}",
            "",
            "图片模板：",
            reusable_methods[0][2],
            "",
            "标题正文模板：",
            reusable_methods[1][2],
            "",
            "转化路径：",
            reusable_methods[2][2],
        ]
    )
    render_clipboard_button(
        full_review_text,
        "copy-live-viral-full-review",
        "复制全部复盘",
        "完整复盘已复制",
    )

    with st.expander("查看详细拆解", expanded=False):
        st.markdown("#### 标题拆解")
        title_columns = st.columns(3, gap="medium")
        for column, (label, value) in zip(
            title_columns,
            (
                ("目标用户", title_result.get("target_audience")),
                ("用户问题", title_result.get("pain_point")),
                ("点击理由", title_result.get("click_attraction")),
            ),
        ):
            with column:
                with st.container(border=True):
                    st.caption(label)
                    st.write(brief(value))
        st.markdown("#### 正文结构")
        body_columns = st.columns(3, gap="medium")
        for column, (key, label) in zip(
            body_columns,
            (("opening", "开头方式"), ("middle", "中段展开"), ("ending", "结尾承接")),
        ):
            with column:
                with st.container(border=True):
                    st.caption(label)
                    st.write(brief(structure_result.get(key)))
        st.markdown("#### 用户痛点与转化设计")
        detail_columns = st.columns(2, gap="medium")
        detail_columns[0].write("**用户痛点：** " + brief(pain_point))
        detail_columns[1].write("**转化设计：** " + brief(conversion_summary))
        st.write("**风险点：** " + brief(image_result.get("risk_points"), "未发现明确风险表达"))
        st.write("**不建议照搬：** " + brief(image_result.get("avoid_copying"), "暂无"))
        with st.container(border=True):
            st.caption("原始拆解模板")
            st.write(brief(text_result.get("copyable_template")))
        reusable_elements = image_result.get("reusable_elements", [])
        if not isinstance(reusable_elements, list):
            reusable_elements = [reusable_elements] if reusable_elements else []
        for index, item in enumerate([*reusable_elements, *suggestions][:4], start=1):
            with st.container(border=True):
                st.caption(f"复盘提示 {index}")
                st.write(brief(item))


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
        "审核规则中心",
        "看懂 NoteGuard 如何稳定识别风险",
        "明确规则负责稳定命中，AI 负责理解上下文与生成自然建议。",
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
        st.markdown("### 规则引擎 + AI 的分工")
        method_columns = st.columns(2, gap="medium")
        method_columns[0].info("**规则引擎**\n\n识别效果承诺、绝对化表达、联系方式等明确风险，保证结果稳定可解释。")
        method_columns[1].info("**AI 语义复核**\n\n理解上下文并给出自然修改方向；最终结果仍需运营人员确认。")
        if PUBLIC_DEMO:
            st.caption("公开 Demo 为只读模式，访客不能新增、修改或删除审核规则。")

    with st.container(border=True):
        st.markdown('<div class="module-eyebrow">当前规则库</div>', unsafe_allow_html=True)
        st.markdown('<div class="module-title">审核规则</div>', unsafe_allow_html=True)
        compliance_records = [record for record in records if record["category"] != "普通教育表达"]
        style_records = [record for record in records if record["category"] == "普通教育表达"]
        summary_left, summary_middle, summary_right = st.columns(3)
        summary_left.metric("合规规则", len(compliance_records))
        summary_middle.metric("表达建议", len(style_records))
        summary_right.metric("启用规则", sum(record["enabled"] for record in records))
        filter_left, filter_right = st.columns([1.5, 1])
        rule_query = filter_left.text_input(
            "搜索规则",
            placeholder="搜索关键词、分类或风险原因",
            key="rule_readonly_query",
        ).strip().lower()
        categories = ["全部", *sorted({record["category"] for record in records})]
        selected_category = filter_right.selectbox(
            "按分类筛选",
            categories,
            key="rule_readonly_category",
        )
        visible_records = [
            record
            for record in records
            if (selected_category == "全部" or record["category"] == selected_category)
            and (
                not rule_query
                or rule_query in " ".join(
                    str(record.get(field, "")).lower()
                    for field in ("term", "category", "reason", "suggestion")
                )
            )
        ]
        table_rows = [
            {
                "关键词": record["term"],
                "类型": "表达优化" if record["category"] == "普通教育表达" else "合规风险",
                "等级": "不计分" if record["category"] == "普通教育表达" else get_severity_label(record["severity"]),
                "分类": record["category"],
                "判断依据": record["reason"],
                "修改建议": record["suggestion"] or "建议删除、弱化或重新表述",
                "启用状态": "启用" if record["enabled"] else "停用",
            }
            for record in visible_records
        ]
        st.dataframe(table_rows, use_container_width=True, hide_index=True)
        st.caption(f"当前显示 {len(table_rows)} 条规则；表达优化建议不参与合规风险评分。")

    if PUBLIC_DEMO:
        return

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
    history_records = get_visible_history()

    with st.container(border=True):
        st.markdown("### 我的记录")
        if PUBLIC_DEMO:
            st.info("公开 Demo 仅显示你当前会话产生的记录，并附带一条脱敏演示记录；关闭会话后不会长期保存。")
        if not history_records:
            st.info("本次会话还没有审核记录。完成一次审核后，可在这里继续修改或重新检查。")
            st.button(
                "前往内容审核中心",
                type="primary",
                on_click=open_workspace_page,
                args=("内容审核中心",),
            )
            return

        def record_type(record: dict) -> str:
            if record.get("cover_analysis"):
                return "含封面分析"
            if record.get("title_candidates"):
                return "含标题分析"
            return "内容审核"

        available_types = ["全部", *sorted({record_type(record) for record in history_records})]
        selected_type = st.selectbox("按功能筛选", available_types, key="history_type_filter")
        filtered_records = [
            record
            for record in history_records
            if selected_type == "全部" or record_type(record) == selected_type
        ]

        for record in filtered_records:
            columns = st.columns([3, 1.2, 1.2, 1.2])
            title_summary = str(record.get("title") or "未填写标题")[:36]
            columns[0].markdown(f"**{title_summary}**")
            record_badge = " · 脱敏演示" if record.get("demo_record") else ""
            columns[0].caption(f"{record_type(record)} · {record.get('time', '')}{record_badge}")
            columns[1].metric("合规安全分", f"{record.get('safety_score', 0)}/100")
            columns[2].metric("风险等级", str(record.get("risk_level", "未知")))
            risk_items = record.get("risk_items", [])
            columns[2].caption(f"命中 {len(risk_items)} 项")
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
        detail_actions = st.columns(3)
        detail_actions[0].button(
            "返回修改",
            type="primary",
            use_container_width=True,
            on_click=restore_history_for_review,
            args=(selected_record,),
            key=f"history_edit_{selected_record.get('id')}",
        )
        detail_actions[1].button(
            "重新审核",
            use_container_width=True,
            on_click=restore_history_for_review,
            args=(selected_record,),
            key=f"history_recheck_{selected_record.get('id')}",
        )
        safe_copy = "\n".join(
            part for part in (
                str(selected_record.get("safe_title") or ""),
                str(selected_record.get("safe_body") or ""),
            ) if part
        )
        with detail_actions[2]:
            render_clipboard_button(
                safe_copy,
                f"history-copy-{selected_record.get('id')}",
                "复制修改建议",
                "修改建议已复制",
            )
        st.markdown("**原内容**")
        st.write(f"标题：{selected_record.get('title', '')}")
        st.write(f"正文：{selected_record.get('body', '')}")
        image_ocr_text = selected_record.get("image_ocr_text", "")
        if image_ocr_text:
            st.write(f"图片识别文字：{image_ocr_text}")

        st.markdown("**合规评估**")
        st.write(
            f"合规安全分：{selected_record.get('safety_score', 0)}/100"
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
                issue_name = str(item.get("category") or item.get("reason") or "待处理问题")
                with st.expander(
                    f"问题 {index} · {issue_name} · {status_label}",
                    expanded=index == 1,
                ):
                    st.write(f"原句：{item.get('original_text', '')}")
                    st.write(f"修改原因：{item.get('reason', '')}")
                    st.write(f"建议修改为：{item.get('replacement_text', '')}")

        st.markdown("**建议修改方向**")
        st.write(f"标题：{selected_record.get('safe_title', '')}")
        st.write(f"正文：{selected_record.get('safe_body', '')}")

        title_candidates = selected_record.get("title_candidates", [])
        if title_candidates:
            st.markdown("**标题分析记录**")
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
        "正在检查标题规则...",
        "正在检查正文规则...",
        "正在检查图片文字...",
        "正在整理合规问题...",
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
        extraction = extract_cover_text_details(image_bytes)
        raw_text = extraction.cover_text or "\n".join(extraction.lines)
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
        st.session_state["cover_vision_lines"] = list(extraction.vision_lines)
        st.session_state["cover_vision_context"] = dict(getattr(extraction, "vision_context", {}) or {})
        st.session_state["cover_ocr_optimized_lines"] = optimized_lines
        st.session_state["cover_ocr_lines"] = optimized_lines
        st.session_state["cover_ocr_confidence"] = extraction.average_confidence
        st.session_state["cover_ocr_engine"] = extraction.engine
        st.session_state["cover_ocr_corrections"] = list(correction.changes)
        st.session_state["cover_ocr_requires_confirmation"] = correction.requires_confirmation
        st.session_state["cover_ocr_error"] = extraction.error
        st.session_state["cover_ocr_status"] = "success" if optimized_lines else "failed"
        st.session_state["cover_text"] = "\n".join(optimized_lines)
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
    image_description: str = "",
) -> dict | None:
    image_key = hashlib.sha256(image_bytes).hexdigest()
    normalized_text = cover_text.strip()
    normalized_description = image_description.strip()
    text_key = hashlib.sha256(
        f"{image_key}:{normalized_text}:{normalized_description}".encode("utf-8")
    ).hexdigest()
    if not normalized_text:
        st.session_state["cover_analysis"] = None
        st.session_state["cover_analysis_error"] = "请先补充封面文字后再分析。"
        return None

    title = st.session_state.get("draft_title", "")
    body = st.session_state.get("draft_body", "")
    findings = check_text(title=title, body=body, rules=rules)
    analysis = resolve_demo_or_live(
        st.session_state.get("demo_mode", False),
        DEMO_COVER_ANALYSIS,
        lambda: analyze_cover(
            normalized_text,
            findings,
            image_description=normalized_description,
        ),
    )
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
    image_description = st.session_state.get("cover_image_description", "")
    with st.spinner("已识别封面文字，正在自动完成封面分析..."):
        analyze_cover_text(
            image_bytes,
            cover_text,
            rules,
            source="automatic",
            image_description=image_description,
        )


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


def retry_workspace_cover_ocr(
    image_bytes: bytes,
    creator_profile: dict[str, str],
    rules: list[Rule],
) -> None:
    """Retry the real OCR/vision chain for the current cover without faking success."""
    for key in (
        "cover_ocr_attempt_key",
        "cover_ocr_status",
        "cover_ocr_error",
        "cover_ocr_lines",
        "cover_vision_lines",
        "cover_text",
    ):
        st.session_state.pop(key, None)
    lines, error = ensure_cover_ocr(image_bytes, creator_profile)
    if lines:
        auto_analyze_cover_once(image_bytes, rules)
        st.session_state["workspace_notice"] = "封面文字已重新识别，并已加入本次审核。"
    else:
        st.session_state["workspace_notice"] = (
            "本次仍未读取到可确认的封面文字。图片已保留，可配置图片识别能力后再次尝试。"
            if error
            else "本次未读取到可确认的封面文字，图片仍已保留。"
        )


def render_cover_diagnosis_page(
    rules: list[Rule],
    creator_profile: dict[str, str],
) -> None:
    render_page_hero(
        "内容审核中的封面分析",
        "发布前，从用户点击、内容理解和互动价值角度，检查你的笔记表现潜力。",
        "上传图片后会自动识别文字；识别失败时可手动补充。结果用于发布前优化，不是流量预测。",
    )
    st.markdown(
        '<div class="preflight-checks"><span>第一眼吸引力</span><span>标题表达</span><span>内容清晰度</span><span>用户需求匹配</span><span>互动潜力</span></div>',
        unsafe_allow_html=True,
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
        st.info("先上传或粘贴笔记封面，也可以从创作工作台带入已上传的图片。")
        return

    ocr_lines, ocr_error = ensure_cover_ocr(image_bytes, creator_profile)
    auto_analyze_cover_once(image_bytes, rules)
    if "image_text_input" not in st.session_state:
        st.session_state["image_text_input"] = st.session_state.get("draft_image_text", "")
    image_review = review_image(st.session_state.get("draft_image_text", ""), rules)
    analysis = st.session_state.get("cover_analysis")
    analysis_error = st.session_state.get("cover_analysis_error", "")
    if analysis and st.session_state.get("cover_analysis_source") == "automatic":
        st.success("已自动识别并完成分析。可修改文字后重新分析。")
    elif ocr_error:
        st.caption("未识别到明显封面文字，仍会结合标题、正文和图片描述继续分析；也可手动补充文字。")

    preview_column, input_column = st.columns([0.85, 1.15], gap="large")
    with preview_column:
        st.markdown("#### 封面预览")
        st.image(image_bytes, caption="当前待发布封面", use_container_width=True)
        st.button(
            "删除图片",
            key="delete_cover_image",
            on_click=delete_current_image,
            use_container_width=True,
        )
    with input_column:
        st.markdown("#### 补充笔记信息")
        if ocr_error:
            st.caption("文字识别未完成，可手动填写封面文字；这不会阻断其他内容分析。")
        elif ocr_lines:
            st.caption("OCR 已自动填充，可确认或修正后重新预检。")
        raw_ocr_text = "\n".join(st.session_state.get("cover_ocr_raw_lines", []))
        if raw_ocr_text:
            with st.expander("查看原始 OCR 文本", expanded=False):
                st.text_area(
                    "原始识别文本",
                    value=raw_ocr_text,
                    height=100,
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
            "封面文字（可编辑）",
            placeholder="补充封面中的标题、副标题或关键信息",
            height=140,
            key="image_text_input",
            on_change=sync_cover_text_draft,
        )
        image_description = st.text_area(
            "图片补充描述（可选）",
            placeholder="例如：人物位于画面右侧，主标题为红色大字，背景为课堂场景",
            height=100,
            key="cover_image_description",
            help="仅填写你确认看到的信息，描述会与 OCR 文字一起用于内容审核中的封面分析。",
        )
        if st.button("生成发布准备度报告", type="primary", use_container_width=True, key="cover_page_analyze_button"):
            with st.spinner("正在检查标题、封面和正文..."):
                analyze_cover_text(
                    image_bytes,
                    cover_text,
                    rules,
                    source="manual",
                    image_description=image_description,
                )
            st.rerun()
        with st.expander("发布前表达检查（可选）", expanded=False):
            st.caption("用于提醒图片文字中的表达风险，不影响发布准备度分析。")
            render_image_review(image_review, True)

    st.divider()
    render_publish_readiness_report(
        st.session_state.get("draft_image_text", ""),
        analysis,
        analysis_error,
    )


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
        "viral_selected_image_deleted",
        "viral_import_image_choice",
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
    uploader_key = st.session_state.get("viral_uploader_key", 0)
    upload_column, paste_column = st.columns(2)
    with upload_column:
        uploaded_image = st.file_uploader(
            "上传拆解图片",
            type=["png", "jpg", "jpeg", "webp"],
            key=f"{prefix}_viral_image_upload_{uploader_key}",
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
                    key=f"{prefix}_viral_image_paste_{uploader_key}",
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
            analysis = resolve_demo_or_live(
                st.session_state.get("demo_mode", False),
                DEMO_VIRAL_ANALYSIS,
                lambda: analyze_viral_note(normalized_title, normalized_body),
            )
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
            image_analysis = resolve_demo_or_live(
                st.session_state.get("demo_mode", False),
                DEMO_VIRAL_IMAGE_ANALYSIS,
                lambda: analyze_viral_image(image_context),
            )
            st.session_state["viral_image_analysis"] = image_analysis
            st.session_state["viral_image_analysis_error"] = "" if image_analysis else get_last_error()
            if image_analysis:
                st.session_state["viral_image_analysis_key"] = image_key


def build_viral_model(
    title: str,
    body: str,
    analysis: dict | None,
    image_analysis: dict | None,
    tags: list[str],
) -> dict[str, str]:
    """Turn an existing case analysis into a reusable model without another AI call."""
    text_analysis = analysis or {}
    visual_analysis = image_analysis or {}
    title_analysis = text_analysis.get("title_analysis", {})
    structure_analysis = text_analysis.get("structure_analysis", {})
    copy_structure = visual_analysis.get("copy_structure", {})
    target_user = str(
        title_analysis.get("target_audience")
        or copy_structure.get("target_audience")
        or "教育内容目标用户"
    ).strip()
    pain_point = str(
        title_analysis.get("pain_point")
        or copy_structure.get("pain_point")
        or "当前拆解未明确用户痛点"
    ).strip()
    click_reason = str(title_analysis.get("click_attraction") or "可获得的具体方法或价值").strip()
    combined = "\n".join([title, body, " ".join(tags)])
    if any(term in combined for term in ("课程", "试听", "招生", "课时", "辅导服务")):
        content_type = "课程服务"
    elif any(term in combined for term in ("成绩单", "成绩案例", "前后对比", "进步记录")):
        content_type = "学生成果案例"
    elif any(term in combined for term in ("方法", "步骤", "清单", "复盘")):
        content_type = "学习方法分享"
    else:
        content_type = "教学经验"

    opening = str(structure_analysis.get("opening") or "从目标用户的具体问题切入").strip()
    middle = str(structure_analysis.get("middle") or "解释原因并给出具体方法").strip()
    ending = str(structure_analysis.get("ending") or "总结适用场景并提出互动问题").strip()
    credibility = str(copy_structure.get("credibility") or "").strip()
    if not credibility:
        credibility = next(
            (
                str(reason).strip()
                for reason in text_analysis.get("viral_reasons", [])
                if any(term in str(reason) for term in ("信任", "案例", "过程", "老师", "经验"))
            ),
            "通过具体过程、方法依据和可验证信息建立信任",
        )
    model_seed = tags[0] if tags else title[:16].strip() or content_type
    return {
        "model_name": f"{model_seed}内容模型",
        "suitable_scenario": "、".join(tags) if tags else f"{target_user}的{content_type}",
        "user_pain": pain_point,
        "content_type": content_type,
        "title_structure": f"{target_user} + {pain_point} + {click_reason}",
        "opening_style": opening,
        "content_structure": f"开头：{opening}；中段：{middle}；结尾：{ending}",
        "trust_building": credibility,
        "reusable_title_formula": "【目标人群/阶段】+【具体问题】+【可获得的方法或结果价值】",
    }


def render_viral_workspace(rules: list[Rule], show_hero: bool = True) -> None:
    if show_hero:
        render_page_hero(
            "爆款研究库",
            "分析优秀教育内容，并沉淀为可复用的个人案例资产",
            "支持公开链接和手动图文素材。拆解完成后可保存标题、正文、封面、分析结果和标签。",
        )

    saved_notice = st.session_state.pop("viral_case_save_notice", "")
    if saved_notice:
        st.success(saved_notice)

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
                st.session_state["viral_import_image_choice"] = 0 if imported["image_urls"] else -1
                st.session_state["viral_selected_image_deleted"] = False
                st.session_state["viral_import_title_edit"] = imported["title"]
                st.session_state["viral_import_body_edit"] = imported["body"]
            except LinkImportError as error:
                st.session_state["imported_link_content"] = None
                st.session_state["link_import_error"] = str(error)

        imported_content = st.session_state.get("imported_link_content")
        import_error = st.session_state.get("link_import_error", "")
        if imported_content:
            final_url = str(imported_content.get("final_url") or "")
            final_url_lower = final_url.lower()
            if "xiaohongshu" in final_url_lower or "xhslink" in final_url_lower:
                source_platform = "小红书"
            elif "douyin" in final_url_lower:
                source_platform = "抖音"
            elif "weixin" in final_url_lower or "qq.com" in final_url_lower:
                source_platform = "微信内容"
            else:
                source_platform = "公开网页"

            image_urls = list(imported_content.get("image_urls") or [])
            cover_source_label = str(imported_content.get("cover_image_source") or "分享图")
            if "viral_import_image_choice" not in st.session_state:
                st.session_state["viral_import_image_choice"] = 0 if image_urls else -1
            image_options = [-1, *range(len(image_urls))]
            selected_index = st.selectbox(
                "选择当前主图",
                image_options,
                format_func=lambda index: (
                    "请选择图片"
                    if index == -1
                    else f"图片{index + 1}（{cover_source_label if index == 0 else '正文图片'}）"
                ),
                key="viral_import_image_choice",
                on_change=select_imported_main_image,
                args=(image_urls,),
            )
            selected_image_url = image_urls[selected_index] if 0 <= selected_index < len(image_urls) else ""
            st.session_state["viral_selected_image_url"] = selected_image_url
            content_image_urls = list(imported_content.get("content_image_urls") or [])
            if not content_image_urls:
                content_image_urls = [url for url in image_urls if url != selected_image_url]
            if selected_image_url:
                image_identity = cover_source_label if selected_index == 0 else "正文图片"
                st.image(selected_image_url, caption=f"当前主图 · {image_identity}", width="stretch")
                st.button(
                    "删除当前图片",
                    key="delete_imported_main_image",
                    on_click=delete_imported_main_image,
                    args=(image_urls,),
                    use_container_width=True,
                )
            else:
                st.info("当前未选择主图，请重新选择图片或重新读取链接。")

            if content_image_urls:
                with st.expander(f"查看正文图片（{len(content_image_urls)}张）", expanded=False):
                    image_columns = st.columns(3)
                    for index, image_url in enumerate(content_image_urls):
                        with image_columns[index % 3]:
                            st.image(image_url, caption=f"正文图片 {index + 1}", width="stretch")

            imported_title = st.text_input("导入标题", key="viral_import_title_edit")
            imported_body_value = str(st.session_state.get("viral_import_body_edit", ""))
            summary = (
                imported_body_value[:180].rstrip() + "…"
                if len(imported_body_value) > 180
                else imported_body_value or "待手动补充"
            )
            overview_columns = st.columns(2)
            overview_columns[0].write(f"**来源平台：** {source_platform}")
            overview_columns[1].write(f"**图片数量：** {len(image_urls)} 张")
            with st.container(border=True):
                st.caption("正文摘要")
                st.write(summary)

            with st.expander("查看全文", expanded=False):
                imported_body = st.text_area(
                    "导入正文",
                    height=220,
                    key="viral_import_body_edit",
                )

            with st.expander("查看导入详情", expanded=False):
                st.write(f"**原始链接：** {imported_content['original_url']}")
                st.write(f"**最终链接：** {imported_content['final_url']}")
                st.write(f"**图片来源：** {cover_source_label}")
                st.write(f"**抓取图片数量：** {len(image_urls)}张")
                current_identity = "封面" if selected_index == 0 else "正文" if selected_index > 0 else "未选择"
                st.write(f"**当前分析图片：** {current_identity}")
                current_source = cover_source_label if selected_index == 0 else "正文图片" if selected_index > 0 else "未选择"
                st.write(f"**当前分析图片来源：** {current_source}")
                st.write(
                    f"**OCR文本：** {str(st.session_state.get('viral_image_text', '')).strip() or '尚未识别'}"
                )
                st.write(f"**页面描述：** {imported_content.get('description') or '未提取到'}")
                st.write(f"**导入状态：** {imported_content['status_message']}")

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
        imported_main_image_is_visible = bool(
            st.session_state.get("viral_image_source") == "link"
            and st.session_state.get("viral_selected_image_url")
        )
        if not imported_main_image_is_visible:
            st.image(image_bytes, caption="当前拆解主图", width="stretch")
        has_analysis_result = bool(
            st.session_state.get("viral_note_analysis")
            or st.session_state.get("viral_image_analysis")
        )
        image_controls = (
            st.expander("查看图片识别与补充信息", expanded=False)
            if has_analysis_result
            else st.container()
        )
        with image_controls:
            st.button(
                "删除图片",
                key="delete_viral_image",
                on_click=delete_viral_image,
                width="stretch",
            )
            ocr_error = st.session_state.get("viral_image_ocr_error", "")
            if ocr_error:
                available, _ = image_analysis_capability()
                if available:
                    st.caption("未读取到可确认的图片文字，可在下方补充。")
                else:
                    st.info("封面分析暂不可用。当前仍可分析标题和正文；配置图片识别后，可分析封面文字和视觉吸引力。")
            st.text_area(
                "图片 OCR 文字（可编辑）",
                key="viral_image_text",
                height=130,
                placeholder="系统会先结合图片内容分析，也可在此补充你确认看到的文字",
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
        with st.container(border=True):
            st.markdown("### 保存到爆款研究库")
            st.caption("保存案例素材、拆解结果和可复用结构，形成自己的教育内容案例库。")
            current_case_title = str(st.session_state.get("viral_note_title", viral_title)).strip()
            current_case_body = str(st.session_state.get("viral_note_body", viral_body)).strip()
            case_type = st.radio(
                "案例类型",
                ["招生转化", "知识分享", "家长痛点", "成绩案例", "方法技巧", "活动招生", "其他"],
                horizontal=True,
                key="viral_case_type",
            )
            target_audiences = st.multiselect(
                "主要面向（可选）",
                ["家长", "学生", "老师", "教培机构", "其他"],
                key="viral_case_target_audiences",
            )
            case_collection_reason = st.text_area(
                "为什么收藏这个案例？",
                placeholder="例如：标题抓人、痛点精准、封面结构好、转化路径明显、家长共鸣强",
                height=80,
                key="viral_case_collection_reason",
            )
            case_tag_source_key = hashlib.sha256(
                f"{current_case_title}\n{current_case_body}".encode("utf-8")
            ).hexdigest()
            if st.session_state.get("viral_case_tag_source_key") != case_tag_source_key:
                st.session_state["viral_case_tag_source_key"] = case_tag_source_key
                st.session_state["viral_case_tags_input"] = "，".join(
                    infer_case_tags(current_case_title, current_case_body)
                )
            with st.expander("更多标签（可选）", expanded=False):
                usage_scenarios = st.multiselect(
                    "使用场景",
                    ["日常获客", "暑假/寒假招生", "考试节点", "成绩提升", "品牌展示", "社群运营"],
                    key="viral_case_usage_scenarios",
                )
                editable_tags = st.text_input(
                    "标签（可编辑，用逗号分隔）",
                    key="viral_case_tags_input",
                    help="系统已根据标题和正文带入基础标签，只需在必要时调整。",
                )
            inferred_subject = infer_case_subject(current_case_title, current_case_body)
            tag_dimensions = {
                "subject": inferred_subject,
                "audience": "、".join(target_audiences),
                "content_type": case_type,
                "scenario": "、".join(usage_scenarios),
            }
            custom_tags = [item.strip() for item in re.split(r"[,，]", editable_tags) if item.strip()]
            case_tags = list(
                dict.fromkeys(
                    [
                        *custom_tags,
                        case_type,
                        *target_audiences,
                        *usage_scenarios,
                    ]
                )
            )
            model_preview = build_viral_model(
                str(st.session_state.get("viral_note_title", viral_title)).strip(),
                str(st.session_state.get("viral_note_body", viral_body)).strip(),
                viral_analysis,
                image_analysis,
                case_tags,
            )
            with st.expander("查看将自动沉淀的爆款模型", expanded=False):
                for key, label in (
                    ("model_name", "模型名称"),
                    ("suitable_scenario", "适用场景"),
                    ("user_pain", "用户痛点"),
                    ("content_type", "内容类型"),
                    ("title_structure", "标题结构"),
                    ("opening_style", "开头方式"),
                    ("content_structure", "内容结构"),
                    ("trust_building", "信任建立方式"),
                    ("reusable_title_formula", "可复用标题公式"),
                ):
                    st.write(f"**{label}：** {model_preview[key]}")
            with st.expander("来源与运营复盘（可选）", expanded=False):
                if "viral_case_source_url" not in st.session_state:
                    st.session_state["viral_case_source_url"] = str(
                        st.session_state.get("viral_final_url", "")
                    ).strip()
                st.session_state.setdefault("viral_case_source_platform", "小红书")
                source_left, source_right = st.columns(2)
                with source_left:
                    case_source_platform = st.selectbox(
                        "来源平台",
                        ["未标注", "小红书", "抖音", "视频号", "其他"],
                        key="viral_case_source_platform",
                    )
                    case_publish_date = st.text_input(
                        "发布日期",
                        placeholder="例如：2026-07-22，可为空",
                        key="viral_case_publish_date",
                    )
                with source_right:
                    case_source_url = st.text_input(
                        "原始链接",
                        key="viral_case_source_url",
                    )
                    case_source_account = st.text_input(
                        "来源账号",
                        placeholder="可为空",
                        key="viral_case_source_account",
                    )
                case_verification_status = st.selectbox(
                    "是否验证有效",
                    ["待验证", "已验证有效", "不推荐复用"],
                    key="viral_case_verification_status",
                )
                case_viral_level = st.selectbox(
                    "爆款等级",
                    ["普通", "优秀", "爆款"],
                    key="viral_case_viral_level",
                )
                metric_columns = st.columns(3)
                with metric_columns[0]:
                    case_likes = st.text_input("点赞", placeholder="可为空", key="viral_case_likes")
                with metric_columns[1]:
                    case_favorites = st.text_input("收藏", placeholder="可为空", key="viral_case_favorites")
                with metric_columns[2]:
                    case_comments = st.text_input("评论", placeholder="可为空", key="viral_case_comments")
                case_conversion = st.text_input(
                    "转化情况",
                    placeholder="例如：收到3条咨询，可为空",
                    key="viral_case_conversion",
                )
                case_operation_notes = st.text_area(
                    "运营备注",
                    placeholder="记录投放、发布时间、评论反馈等人工观察",
                    key="viral_case_operation_notes",
                    height=100,
                )
            if st.button(
                "保存案例",
                type="primary",
                use_container_width=True,
                key="save_viral_case_button",
            ):
                current_title = str(st.session_state.get("viral_note_title", viral_title)).strip()
                current_body = str(st.session_state.get("viral_note_body", viral_body)).strip()
                image_bytes = st.session_state.get("viral_image_bytes", b"") or b""
                image_format = str(st.session_state.get("viral_image_format", "png") or "png")
                cover = {
                    "source": str(st.session_state.get("viral_image_source", "")),
                    "format": image_format,
                    "width": int(st.session_state.get("viral_image_width", 0) or 0),
                    "height": int(st.session_state.get("viral_image_height", 0) or 0),
                    "ocr_text": str(st.session_state.get("viral_image_text", "")).strip(),
                    "description": str(st.session_state.get("viral_image_description", "")).strip(),
                    "source_url": "",
                    "image_data": (
                        f"data:image/{image_format};base64,{base64.b64encode(image_bytes).decode('ascii')}"
                        if image_bytes
                        else ""
                    ),
                }
                imported_asset = st.session_state.get("imported_link_content")
                if not isinstance(imported_asset, dict):
                    imported_asset = {}
                source_url = case_source_url.strip()
                source_type = "公开链接" if source_url else "手动输入"
                imported_urls = {
                    str(imported_asset.get(key) or "").strip()
                    for key in ("original_url", "source_url", "final_url")
                    if str(imported_asset.get(key) or "").strip()
                }
                uses_imported_asset = bool(source_url and source_url in imported_urls)
                imported_cover_url = (
                    str(imported_asset.get("cover_image_url") or imported_asset.get("image_url") or "").strip()
                    if uses_imported_asset
                    else ""
                )
                imported_content_images = (
                    imported_asset.get("content_image_urls")
                    if uses_imported_asset and isinstance(imported_asset.get("content_image_urls"), list)
                    else []
                )
                cover["source_url"] = imported_cover_url
                cover_visual_analysis = build_cover_visual_analysis(cover, image_analysis)
                save_viral_case(
                    VIRAL_CASE_LIBRARY_PATH,
                    {
                        "original_material": {
                            "source": source_type,
                            "source_url": source_url,
                            "title": current_title,
                            "content": current_body,
                            "cover": cover,
                            "cover_image": imported_cover_url,
                            "content_images": imported_content_images,
                        },
                        "title": current_title,
                        "content": current_body,
                        "cover": cover,
                        "cover_visual_analysis": cover_visual_analysis,
                        "analysis": {
                            "text": viral_analysis or {},
                            "image": image_analysis or {},
                        },
                        "tags": case_tags,
                        "tag_dimensions": tag_dimensions,
                        "model": model_preview,
                        "source_info": {
                            "platform": "" if case_source_platform == "未标注" else case_source_platform,
                            "original_url": source_url,
                            "publish_date": case_publish_date,
                            "source_account": case_source_account,
                        },
                        "operation_review": {
                            "save_reason": case_collection_reason,
                            "verification_status": case_verification_status,
                            "viral_level": case_viral_level,
                            "actual_metrics": {
                                "likes": case_likes,
                                "favorites": case_favorites,
                                "comments": case_comments,
                            },
                            "conversion": case_conversion,
                            "notes": case_operation_notes,
                        },
                    },
                )
                st.session_state["viral_case_save_notice"] = "案例已保存到爆款研究库。"
                st.rerun()
    if text_error:
        st.info("文字结构分析暂时不可用，已保留当前素材，可稍后重试。")
    if image_error:
        st.info("已完成封面文字识别，可继续根据标题、OCR文字和案例结构完成拆解。")

    st.divider()
    render_viral_case_library("research_library")


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


def open_audit_center_from_plan() -> None:
    draft = st.session_state.get("content_lab_generated_draft")
    if isinstance(draft, dict):
        titles = draft.get("titles") if isinstance(draft.get("titles"), list) else []
        selected_title = str(
            st.session_state.get("content_lab_draft_selected_title")
            or (titles[0] if titles else "")
        ).strip()
        body = draft.get("body") if isinstance(draft.get("body"), dict) else {}
        final_body = str(
            st.session_state.get("content_lab_draft_full_text")
            or body.get("full_text")
            or ""
        ).strip()
        st.session_state["draft_title"] = selected_title
        st.session_state["draft_body"] = final_body
        st.session_state["title_input"] = selected_title
        st.session_state["body_input"] = final_body
    st.session_state["workspace_page"] = "内容审核中心"
    st.session_state["workspace_notice"] = "招生笔记已带入审核中心，请开始合规检查。"


def import_content_growth_link() -> None:
    """Import a public note into the existing content-lab material state."""
    source_url = str(st.session_state.get("content_growth_link_url") or "").strip()
    if not source_url:
        st.session_state["content_growth_link_notice"] = "请先粘贴小红书公开链接。"
        return
    try:
        imported = import_public_page(source_url)
        st.session_state["content_lab_material_title"] = str(
            imported.get("title") or ""
        ).strip()
        st.session_state["content_lab_material_body"] = str(
            imported.get("body") or ""
        ).strip()
        image_urls = list(imported.get("image_urls") or [])
        if image_urls:
            process_content_lab_material_image(
                download_public_image(str(image_urls[0])),
                "link",
            )
        st.session_state["content_growth_link_notice"] = (
            "链接内容已读取，可继续查看爆款拆解。"
        )
    except (LinkImportError, ValueError):
        st.session_state["content_growth_link_notice"] = (
            "链接暂时无法读取，可直接上传截图或粘贴文案继续。"
        )


def analyze_content_lab_material(
    *,
    title: str,
    body: str,
    ocr_text: str,
    image_bytes: bytes,
    image_width: int,
    image_height: int,
    image_format: str,
    creator_profile: dict[str, str],
    fallback_profile: dict,
) -> tuple[dict, str]:
    """Analyze OCR text plus basic file metadata without sending image pixels to DeepSeek."""
    ratio = round(image_width / image_height, 3) if image_width and image_height else 0
    source_context = {
        "analysis_capability": "ocr_dimensions_and_user_description_only",
        "has_image": bool(image_bytes),
        "ocr_text": ocr_text,
        "corrected_text": ocr_text,
        "user_title": title,
        "user_body": body,
        "visual_scene": "",
        "image_width": image_width,
        "image_height": image_height,
        "image_bytes_size": len(image_bytes),
        "aspect_ratio": ratio,
        "image_format": image_format,
        "evidence": [item for item in (title, ocr_text, body) if item],
        "rule_constraints": [],
    }
    viral_context = {
        "analysis_capability": "ocr_dimensions_and_user_description_only",
        "has_image": bool(image_bytes),
        "ocr_text": ocr_text,
        "user_description": "\n".join(
            item
            for item in (
                f"素材标题：{title}" if title else "",
                f"素材正文：{body}" if body else "",
            )
            if item
        ),
        "image_width": image_width,
        "image_height": image_height,
        "image_bytes_size": len(image_bytes),
        "aspect_ratio": ratio,
        "image_format": image_format,
        "risk_items": [],
        "inference_notice": IMAGE_INFERENCE_NOTICE,
    }
    source_analysis = resolve_demo_or_live(
        st.session_state.get("demo_mode", False),
        DEMO_NOTE_IMAGE_ANALYSIS,
        lambda: analyze_note_image_source(source_context, creator_profile, []),
    )
    source_error = "" if source_analysis else get_last_error()
    image_analysis = resolve_demo_or_live(
        st.session_state.get("demo_mode", False),
        DEMO_VIRAL_IMAGE_ANALYSIS,
        lambda: analyze_viral_image(viral_context),
    )
    image_error = "" if image_analysis else get_last_error()
    suggestion = build_material_profile_suggestion(
        title=title,
        ocr_text=ocr_text,
        source_analysis=source_analysis,
        image_analysis=image_analysis,
        fallback_profile=fallback_profile,
    )
    errors = "；".join(error for error in (source_error, image_error) if error)
    return suggestion, errors


def render_content_plan_card(plan: dict, key_prefix: str) -> None:
    method = plan.get("method", {}) if isinstance(plan.get("method"), dict) else {}
    inputs = plan.get("inputs", {}) if isinstance(plan.get("inputs"), dict) else {}
    cover = plan.get("cover_suggestion", {}) if isinstance(plan.get("cover_suggestion"), dict) else {}
    title_directions = plan.get("title_directions", [])
    if not isinstance(title_directions, list):
        title_directions = []
    body_framework = plan.get("body_framework", [])
    if not isinstance(body_framework, list):
        body_framework = []
    reference_cases = plan.get("reference_cases", [])
    if not isinstance(reference_cases, list):
        reference_cases = []

    with st.container(border=True):
        st.caption(f"使用方法：{method.get('name') or '未记录'}")
        st.markdown(f"### {escape(plan.get('content_direction') or '内容策划方案')}")
        summary_columns = st.columns(2, gap="medium")
        summary_columns[0].write(
            f"**推荐结构：** {plan.get('recommended_structure') or '待补充'}"
        )
        summary_columns[1].write(
            f"**适用对象：** {inputs.get('target_user') or '待补充'}"
        )
        if reference_cases:
            st.markdown("#### 参考爆款案例")
            reference_columns = st.columns(min(3, len(reference_cases)), gap="medium")
            for column, reference in zip(reference_columns, reference_cases[:3]):
                if not isinstance(reference, dict):
                    continue
                with column:
                    with st.container(border=True):
                        st.write(f"**{reference.get('title') or '未命名案例'}**")
                        st.caption(reference.get("reuse_point") or "复用已沉淀的内容结构")
        with st.expander("查看完整策划卡", expanded=False):
            st.markdown("#### 标题方向")
            for index, direction in enumerate(title_directions[:3], start=1):
                st.write(f"{index}. {direction}")
            st.markdown("#### 封面建议")
            cover_columns = st.columns(2)
            cover_columns[0].write(f"**图片类型：** {cover.get('image_type') or '待补充'}")
            cover_columns[1].write(f"**视觉重点：** {cover.get('visual_focus') or '待补充'}")
            st.markdown("#### 正文框架")
            for index, item in enumerate(body_framework, start=1):
                st.write(f"{index}. {item}")
            st.caption("这是内容策划结构，不是可直接发布的完整文案；案例、数据和效果描述需人工核实。")
        st.button(
            "进入审核中心检查",
            key=f"{key_prefix}_open_audit",
            on_click=open_audit_center_from_plan,
            width="stretch",
        )


def render_content_lab_draft(draft: dict, key_prefix: str) -> None:
    titles = draft.get("titles", []) if isinstance(draft.get("titles"), list) else []
    cover = draft.get("cover_copy", {}) if isinstance(draft.get("cover_copy"), dict) else {}
    body = draft.get("body", {}) if isinstance(draft.get("body"), dict) else {}
    publishing = draft.get("publishing", {}) if isinstance(draft.get("publishing"), dict) else {}
    tags = publishing.get("tags", []) if isinstance(publishing.get("tags"), list) else []
    reused_points = (
        publishing.get("reused_points", [])
        if isinstance(publishing.get("reused_points"), list)
        else []
    )
    selected_title_key = f"{key_prefix}_selected_title"
    selected_title = str(st.session_state.get(selected_title_key) or "")
    if titles and selected_title not in titles[:5]:
        selected_title = str(titles[0])
        st.session_state[selected_title_key] = selected_title
    full_text = str(body.get("full_text") or "").strip()
    tag_text = " ".join(str(tag) for tag in tags)

    with st.container(border=True):
        st.markdown("## 🔥 我的招生笔记")
        st.caption("以下内容可直接复制发布；发布前请核实案例、数据和服务信息。")

        st.markdown("### 【标题】")
        if titles:
            selected_title = st.radio(
                "选择一个标题作为最终标题",
                titles[:5],
                key=selected_title_key,
            )
        st.markdown(f"#### {escape(selected_title or '暂未生成标题')}")
        render_clipboard_button(
            selected_title,
            f"{key_prefix}-copy-title",
            "复制标题",
            "标题已复制",
        )

        st.markdown("### 【封面方案】")
        title_signal = f"{selected_title}\n{cover.get('main_title', '')}"
        if any(word in title_signal for word in ("老师", "教龄", "经验", "名师")):
            cover_type = "身份型"
        elif any(word in title_signal for word in ("提升", "结果", "变化", "从", "到")):
            cover_type = "结果型"
        else:
            cover_type = "痛点型"
        cover_columns = st.columns(3, gap="medium")
        cover_columns[0].write(f"**封面类型：** {cover_type}")
        cover_columns[1].write(
            f"**封面大字：** {cover.get('main_title') or selected_title or '待补充'}"
        )
        cover_columns[2].write(
            f"**视觉建议：** {cover.get('visual_suggestion') or '老师或真实学习场景作为辅助，核心文字保持清晰。'}"
        )
        st.caption("V1只提供封面方案，不生成图片。")

        st.markdown("### 【正文】")
        st.caption("痛点共鸣 → 老师背书 → 方法证明 → 服务介绍 → 福利促单")
        final_body = st.text_area(
            "完整小红书正文",
            value=full_text,
            height=440,
            key=f"{key_prefix}_full_text",
        )
        st.caption(f"{len(final_body)} 字 · 建议保持在 800–1500 字")

        st.markdown("### 【标签】")
        st.write(tag_text or "—")
        comment_question = str(publishing.get("comment_question") or "").strip()
        st.markdown("### 【评论区引导】")
        st.write(comment_question or "—")
        final_copy = "\n\n".join(
            part
            for part in (
                f"【标题】\n{selected_title}",
                f"【正文】\n{final_body}",
                f"【标签】\n{tag_text}",
                f"【评论区引导】\n{comment_question}" if comment_question else "",
            )
            if part.strip()
        )
        render_clipboard_button(
            final_copy,
            f"{key_prefix}-copy-final",
            "复制完整发布稿",
            "最终发布稿已复制",
        )

        st.button(
            "一键审核",
            key=f"{key_prefix}_open_audit",
            on_click=open_audit_center_from_plan,
            type="secondary",
            width="stretch",
        )


def render_content_lab_publish_feedback() -> None:
    """Collect a lightweight, session-only publishing result."""
    with st.container(border=True):
        st.markdown("### 发布记录")
        st.caption("发布后补充真实表现，方便后续人工复盘；本记录仅保留在当前页面会话。")
        with st.form("content_lab_publish_feedback_form"):
            top_columns = st.columns(2, gap="medium")
            publish_time = top_columns[0].text_input(
                "发布时间",
                placeholder="例如：2026-07-28 20:00",
            )
            publish_platform = top_columns[1].selectbox(
                "平台",
                ["小红书", "其他"],
            )
            metric_columns = st.columns(4, gap="small")
            likes = metric_columns[0].number_input("点赞", min_value=0, step=1)
            favorites = metric_columns[1].number_input("收藏", min_value=0, step=1)
            comments = metric_columns[2].number_input("评论", min_value=0, step=1)
            inquiries = metric_columns[3].number_input("咨询", min_value=0, step=1)
            is_viral = st.radio(
                "是否爆款",
                ["否", "是"],
                horizontal=True,
            )
            save_feedback = st.form_submit_button(
                "记录发布结果",
                width="stretch",
            )
        if save_feedback:
            st.session_state["content_lab_publish_feedback"] = {
                "publish_time": publish_time.strip(),
                "platform": publish_platform,
                "likes": int(likes),
                "favorites": int(favorites),
                "comments": int(comments),
                "inquiries": int(inquiries),
                "is_viral": is_viral == "是",
            }
            st.success("发布结果已记录在当前会话中。")




def render_content_lab_draft_details(draft: dict, key_prefix: str) -> None:
    """Render secondary draft controls inside the content-lab advanced area."""
    titles = draft.get("titles", []) if isinstance(draft.get("titles"), list) else []
    cover = draft.get("cover_copy", {}) if isinstance(draft.get("cover_copy"), dict) else {}
    body = draft.get("body", {}) if isinstance(draft.get("body"), dict) else {}
    publishing = draft.get("publishing", {}) if isinstance(draft.get("publishing"), dict) else {}
    reused_points = (
        publishing.get("reused_points", [])
        if isinstance(publishing.get("reused_points"), list)
        else []
    )

    st.markdown("#### 封面文字与结构建议")
    st.write(f"**主标题：** {cover.get('main_title') or '—'}")
    st.write(f"**副标题：** {cover.get('subtitle') or '—'}")
    st.write(f"**视觉布局建议：** {cover.get('visual_suggestion') or '—'}")
    cover_text = "\n".join(
        [str(cover.get("main_title") or ""), str(cover.get("subtitle") or "")]
    ).strip()
    render_clipboard_button(
        cover_text,
        f"{key_prefix}-copy-cover",
        "复制封面文案",
        "封面文案已复制",
    )

    st.divider()
    st.markdown("#### 发布时间建议与生成结构")
    body_fields = (
        ("开头吸引", "opening_hook"),
        ("用户痛点", "user_pain"),
        ("场景共鸣", "real_experience"),
        ("解决方案", "solution"),
        ("产品介绍", "product_intro"),
        ("行动引导", "action_guide"),
    )
    for label, field in body_fields:
        st.write(f"**{label}：** {body.get(field) or '—'}")
    st.write(
        f"**发布时间建议：** {publishing.get('timing_advice') or '结合账号历史活跃时段测试。'}"
    )
    if reused_points:
        st.write("**爆款复刻依据：**")
        for point in reused_points:
            st.write(f"- {point}")


def process_content_lab_material_image(image: object, source: str):
    """Normalize uploaded and pasted material through one OCR/state pipeline."""
    try:
        payload = normalize_image_input(image, source)
    except ImageInputError as error:
        st.session_state["content_lab_material_image_error"] = str(error)
        return None

    st.session_state.pop("content_lab_material_image_error", None)
    st.session_state["content_lab_material_image_source"] = source
    if st.session_state.get("content_lab_material_image_hash") == payload.image_hash:
        saved_result = st.session_state.get("content_lab_image_ocr_result") or {}
        saved_text = str(
            saved_result.get("cover_text")
            or saved_result.get("ocr_text")
            or st.session_state.get("content_lab_cover_text")
            or st.session_state.get("content_lab_ocr_text")
            or ""
        ).strip()
        if saved_text and not str(
            st.session_state.get("content_lab_material_ocr_text") or ""
        ).strip():
            st.session_state["content_lab_material_ocr_text"] = saved_text
        return payload

    extraction = extract_cover_text_details(payload.image_bytes)
    recognized_text = str(extraction.cover_text or "").strip()
    if not recognized_text:
        recognized_text = "\n".join(
            str(line).strip() for line in extraction.lines if str(line).strip()
        )
    ocr_result = {
        "ocr_text": recognized_text,
        "cover_text": recognized_text,
        "lines": list(extraction.lines),
        "error": str(extraction.error or ""),
        "average_confidence": extraction.average_confidence,
        "engine": str(extraction.engine or ""),
    }
    st.session_state["content_lab_material_image_hash"] = payload.image_hash
    st.session_state["content_lab_material_image_bytes"] = payload.image_bytes
    st.session_state["content_lab_material_image_width"] = payload.width
    st.session_state["content_lab_material_image_height"] = payload.height
    st.session_state["content_lab_material_image_format"] = payload.image_format
    st.session_state["content_lab_image_ocr_result"] = ocr_result
    st.session_state["content_lab_ocr_text"] = recognized_text
    st.session_state["content_lab_cover_text"] = recognized_text
    st.session_state["content_lab_material_ocr_text"] = recognized_text
    st.session_state.pop("content_lab_material_analysis_key", None)
    st.session_state.pop("content_lab_confirmed_profile", None)
    st.session_state.pop("content_lab_generated_draft", None)
    st.session_state.pop("content_lab_draft_full_text", None)
    st.session_state["content_lab_material_confirmed"] = False
    st.session_state["content_lab_material_applied"] = False
    return payload


def sync_content_lab_ocr_text() -> None:
    """Keep editable OCR text aligned with the stored content-lab result."""
    edited_text = str(st.session_state.get("content_lab_material_ocr_text") or "")
    st.session_state["content_lab_ocr_text"] = edited_text
    st.session_state["content_lab_cover_text"] = edited_text
    saved_result = dict(st.session_state.get("content_lab_image_ocr_result") or {})
    saved_result["ocr_text"] = edited_text
    saved_result["cover_text"] = edited_text
    st.session_state["content_lab_image_ocr_result"] = saved_result


def render_content_growth_breakdown(
    suggestion: dict,
    title: str,
    body: str,
    ocr_text: str,
) -> None:
    """Render a short operator-facing breakdown from existing analysis fields."""
    target_user = str(suggestion.get("target_user") or "目标家长待确认").strip()
    pain_point = str(
        suggestion.get("common_pain_points") or "用户痛点待确认"
    ).strip()
    selling_point = str(
        suggestion.get("core_selling_point") or "核心价值待确认"
    ).strip()
    conversion = str(
        suggestion.get("conversion_method") or "转化入口待确认"
    ).strip()
    source_text = "\n".join((title, ocr_text, body))
    keyword_candidates = [
        keyword
        for keyword in (
            "小学",
            "初中",
            "高中",
            "数学",
            "英语",
            "语文",
            "物理",
            "化学",
            "提分",
            "学习方法",
            "一对一",
            "家长",
        )
        if keyword in source_text
    ]
    keywords = "、".join(keyword_candidates[:4]) or "根据标题与封面文字确认"
    first_cover_line = next(
        (line.strip() for line in ocr_text.splitlines() if line.strip()),
        title.strip() or selling_point,
    )

    st.markdown("### 🔥 为什么这篇能爆？")
    topic_columns = st.columns(4, gap="small")
    topic_columns[0].metric("目标用户", target_user[:24])
    topic_columns[1].metric("核心关键词", keywords[:24])
    topic_columns[2].metric("用户痛点", pain_point[:24])
    topic_columns[3].metric(
        "搜索价值",
        "人群与问题明确" if keyword_candidates else "关键词可继续补强",
    )

    analysis_columns = st.columns(3, gap="medium")
    with analysis_columns[0]:
        st.markdown("#### 封面分析")
        st.write(f"**为什么停留：** {selling_point}")
        st.write(f"**第一眼信息：** {first_cover_line}")
        st.write("**可以复制：** 人群、问题和价值的呈现顺序")
    with analysis_columns[1]:
        st.markdown("#### 标题分析")
        st.write(f"**系统关键词：** {keywords}")
        st.write(f"**点击原因：** {pain_point}")
    with analysis_columns[2]:
        st.markdown("#### 正文成交结构")
        st.write("情绪触发 → 痛点共鸣 → 老师背书")
        st.write("方法证明 → 服务介绍 → 福利转化")
        st.write(f"**成交入口：** {conversion}")

    st.info("爆款公式：精准人群 → 痛点问题 → 专业身份 → 解决方案 → 低门槛体验")


def render_content_lab(profile: dict[str, str]) -> None:
    st.session_state.setdefault("content_lab_platform", "小红书")
    st.session_state.setdefault("content_lab_content_type", "教育培训/课程咨询")
    st.session_state.setdefault("content_lab_conversion_goal", "获取咨询线索")
    render_page_hero(
        "内容增长助手",
        "上传同行爆款，AI 拆解成交逻辑，生成你的招生内容",
        "上传一张同行参考素材，确认用户痛点和转化方式后，直接生成自己的小红书发布稿。",
    )
    st.markdown(
        """
        <div class="step-indicator">
            <span class="active">① 上传爆款</span>
            <span>② AI 拆解</span>
            <span>③ 生成发布稿</span>
            <span>④ 一键复制发布</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("默认平台：小红书　·　内容类型：教育培训/课程咨询　·　目标：获取咨询线索")
    notice = st.session_state.pop("content_plan_notice", "")
    if notice:
        st.success(notice)

    with st.container(border=True):
        st.markdown("### 小红书教育内容增长助手")
        st.write("上传同行爆款截图，AI分析家长痛点、成交逻辑，生成你的招生内容。")
        guide_columns = st.columns(3, gap="small")
        guide_columns[0].markdown("**① 上传爆款素材**")
        guide_columns[1].markdown("**② AI拆解内容结构**")
        guide_columns[2].markdown("**③ 填写业务并生成**")

    existing_draft = st.session_state.get("content_lab_generated_draft")
    if isinstance(existing_draft, dict):
        render_content_lab_draft(existing_draft, "content_lab_draft")
        render_content_lab_publish_feedback()
        st.divider()

    business_profiles = load_business_profiles(BUSINESS_PROFILE_PATH)
    profile_map = {str(item.get("id")): item for item in business_profiles}
    profile_options = [*profile_map, "__new__"]
    profile_key = "content_lab_business_profile_id"
    pending_profile_id = st.session_state.pop("content_lab_pending_profile_id", "")
    if pending_profile_id in profile_map:
        st.session_state[profile_key] = pending_profile_id
    elif st.session_state.get(profile_key) not in profile_options:
        st.session_state[profile_key] = next(iter(profile_map), "__new__")

    active_profile_id = str(st.session_state.get(profile_key) or "__new__")
    active_profile = profile_map.get(active_profile_id)

    st.markdown("## ① 上传爆款图片")
    st.caption("优先粘贴同行小红书链接，也可以上传截图或直接复制文案。")
    st.info("支持小红书爆款截图、招生海报、朋友圈截图和竞品内容截图。")
    st.caption("建议上传点赞、收藏较高的同行内容，结构参考价值通常更高。")
    link_notice = st.session_state.pop("content_growth_link_notice", "")
    if link_notice:
        st.info(link_notice)
    link_columns = st.columns([3, 1], gap="small")
    with link_columns[0]:
        st.text_input(
            "小红书链接（优先）",
            key="content_growth_link_url",
            placeholder="粘贴公开笔记链接",
        )
    with link_columns[1]:
        st.button(
            "读取链接",
            key="content_growth_import_link",
            on_click=import_content_growth_link,
            type="primary",
            width="stretch",
        )
    st.caption("链接无法读取时不会中断，可继续使用截图或复制文案。")
    st.markdown("**或上传截图 / 复制文案**")
    material_columns = st.columns([1.1, 0.9], gap="large")
    pasted_material = None
    with material_columns[0]:
        material_title = st.text_input(
            "已有标题（可选）",
            key="content_lab_material_title",
            placeholder="没有标题可以留空",
        )
        material_body = st.text_area(
            "同行正文（可选）",
            key="content_lab_material_body",
            placeholder="可以直接粘贴同行正文或主要文案",
            height=120,
        )
        material_upload = st.file_uploader(
            "上传封面图片（可选）",
            type=["png", "jpg", "jpeg", "webp"],
            key="content_lab_material_upload",
        )
        st.caption("支持选择文件或将图片拖拽到上传区域。")
        st.markdown("**也可以直接粘贴截图**")
        st.caption(
            "支持直接复制小红书截图后 Ctrl+V 粘贴；微信和浏览器截图也可使用。"
            "请先点击下方粘贴区域。"
        )
        paste_button, component_error = load_paste_image_button()
        if paste_button is None:
            st.caption(component_error)
        else:
            try:
                paste_result = paste_button(
                    label="点击这里后按 Ctrl+V 粘贴截图",
                    key="content_lab_material_paste",
                    text_color="#ffffff",
                    background_color="#ef4f5f",
                    hover_background_color="#dc3f50",
                    errors="ignore",
                )
                pasted_material, paste_message = extract_pasted_image(paste_result)
                if pasted_material is None:
                    st.caption(paste_message)
            except Exception as error:
                log_paste_component_error(error, "content lab material")
                st.caption(PASTE_UNAVAILABLE_MESSAGE)
        st.caption("系统仅处理你主动粘贴的图片，不读取剪贴板文本。")

    material_payload = None
    if pasted_material is not None:
        material_payload = process_content_lab_material_image(
            pasted_material,
            "clipboard",
        )
        if material_payload is not None:
            st.success("截图已粘贴，正在使用现有 OCR 流程识别文字。")
    elif material_upload is not None:
        material_payload = process_content_lab_material_image(material_upload, "upload")

    material_image_error = st.session_state.get("content_lab_material_image_error")
    if material_image_error:
        st.warning(material_image_error)

    stored_material_image = st.session_state.get("content_lab_material_image_bytes", b"")
    if stored_material_image:
        source_label = (
            "剪贴板截图"
            if st.session_state.get("content_lab_material_image_source") == "clipboard"
            else "上传图片"
        )
        with material_columns[1]:
            st.image(
                stored_material_image,
                caption=f"本次封面素材 · {source_label}",
                width="stretch",
            )
    with material_columns[0]:
        with st.expander("查看或修正封面识别文字", expanded=False):
            material_ocr_text = st.text_area(
                "封面/OCR文字（可编辑）",
                key="content_lab_material_ocr_text",
                placeholder="上传图片后自动填充，也可以直接粘贴图片文字",
                height=120,
                on_change=sync_content_lab_ocr_text,
            )
            if stored_material_image:
                if material_ocr_text.strip():
                    st.caption("已自动识别封面文字，你可以直接修改识别结果。")
                else:
                    st.info("未识别成功，可手动补充。")

    image_bytes = st.session_state.get("content_lab_material_image_bytes", b"")
    material_key = hashlib.sha256(
        "\n".join(
            [
                str(st.session_state.get("content_lab_material_image_hash") or ""),
                material_title.strip(),
                material_body.strip(),
                material_ocr_text.strip(),
            ]
        ).encode("utf-8")
    ).hexdigest()
    has_material = bool(
        image_bytes
        or material_title.strip()
        or material_body.strip()
        or material_ocr_text.strip()
    )
    if has_material and st.session_state.get("content_lab_material_analysis_key") != material_key:
        with st.spinner("正在识别素材中的业务信息..."):
            suggestion, material_error = analyze_content_lab_material(
                title=material_title,
                body=material_body,
                ocr_text=material_ocr_text,
                image_bytes=image_bytes,
                image_width=int(st.session_state.get("content_lab_material_image_width") or 0),
                image_height=int(st.session_state.get("content_lab_material_image_height") or 0),
                image_format=str(st.session_state.get("content_lab_material_image_format") or ""),
                creator_profile=profile,
                fallback_profile=active_profile or {},
            )
        st.session_state["content_lab_material_analysis_key"] = material_key
        st.session_state["content_lab_material_suggestion"] = suggestion
        st.session_state["content_lab_material_error"] = material_error
        st.session_state["content_lab_visual_analysis_status"] = (
            "text_limited" if material_error else "text_complete"
        )
        st.session_state["content_lab_material_confirmed"] = False
        st.session_state["content_lab_material_applied"] = False
        st.session_state.pop("content_lab_confirmed_profile", None)
        for field, value in suggestion.items():
            own_value = str((active_profile or {}).get(field) or "").strip()
            st.session_state[f"content_lab_confirm_{field}"] = own_value or value

    material_suggestion = st.session_state.get("content_lab_material_suggestion")
    if isinstance(material_suggestion, dict) and has_material:
        st.markdown("## ② AI爆款拆解")
        if st.session_state.get("content_lab_visual_analysis_status") == "text_limited":
            st.info("部分分析不可用，已使用文字内容继续生成。")
        else:
            st.success("已完成封面文字识别，AI正在根据爆款结构分析内容。")
        render_content_growth_breakdown(
            material_suggestion,
            material_title,
            material_body,
            material_ocr_text,
        )
        st.markdown("#### 同行内容识别")
        recognition_columns = st.columns(4, gap="small")
        recognition_columns[0].metric(
            "行业",
            str(material_suggestion.get("content_type") or "教育培训")[:24],
        )
        recognition_columns[1].metric(
            "用户",
            str(material_suggestion.get("target_user") or "待确认")[:24],
        )
        recognition_columns[2].metric(
            "核心痛点",
            str(material_suggestion.get("common_pain_points") or "待确认")[:24],
        )
        recognition_columns[3].metric(
            "成交入口",
            str(material_suggestion.get("conversion_method") or "待确认")[:24],
        )
        has_teacher_profile = bool(
            str(profile.get("name") or material_suggestion.get("brand_name") or "").strip()
            and str(
                profile.get("personal_experience")
                or profile.get("teaching_features")
                or ""
            ).strip()
        )
        if not has_teacher_profile:
            st.info("老师姓名、教学经验或擅长领域尚不完整；生成时不会编造，建议在高级设置中补充业务档案。")
        st.markdown("## ③ 填写自己的业务信息")
        st.caption("已有业务档案会自动带入，只需确认本次内容需要使用的信息。")
        with st.form("content_lab_material_confirmation_form"):
            first_row = st.columns(3, gap="small")
            with first_row[0]:
                confirm_business = st.text_input(
                    "我的业务",
                    key="content_lab_confirm_product_name",
                    placeholder="例如：初中数学辅导",
                )
            with first_row[1]:
                confirm_teacher = st.text_input(
                    "老师信息",
                    key="content_lab_confirm_brand_name",
                    placeholder="只填写真实姓名、教龄或擅长领域",
                )
            with first_row[2]:
                confirm_service = st.text_input(
                    "课程/服务",
                    key="content_lab_confirm_usage_scenario",
                    placeholder="例如：一对一学情诊断与错题规划",
                )
            second_row = st.columns(3, gap="small")
            with second_row[0]:
                confirm_target = st.text_input(
                    "目标家长",
                    key="content_lab_confirm_target_user",
                )
            with second_row[1]:
                confirm_selling = st.text_area(
                    "优势",
                    key="content_lab_confirm_core_selling_point",
                    height=68,
                )
            with second_row[2]:
                confirm_conversion = st.text_input(
                    "福利",
                    key="content_lab_confirm_conversion_method",
                    placeholder="没有真实福利可以留空",
                )
            confirm_material = st.form_submit_button(
                "确认业务信息",
                type="primary",
                width="stretch",
            )
        if confirm_material:
            confirmed_profile = {
                "id": str((active_profile or {}).get("id") or ""),
                "product_name": confirm_business.strip(),
                "brand_name": confirm_teacher.strip(),
                "target_user": confirm_target.strip(),
                "usage_scenario": confirm_service.strip(),
                "common_pain_points": str(
                    st.session_state.get("content_lab_confirm_common_pain_points") or ""
                ).strip(),
                "core_selling_point": confirm_selling.strip(),
                "conversion_method": confirm_conversion.strip(),
            }
            st.session_state["content_lab_confirmed_profile"] = confirmed_profile
            st.session_state["content_lab_material_confirmed"] = True
            st.session_state["content_lab_material_applied"] = True
            st.session_state["content_lab_promotion_theme"] = (
                material_title.strip() or confirmed_profile["product_name"]
            )
            st.session_state["content_lab_core_selling_point"] = confirmed_profile[
                "core_selling_point"
            ]
            st.session_state["content_lab_problem_to_solve"] = (
                confirmed_profile["common_pain_points"]
                or f"围绕{confirmed_profile['product_name'] or '当前素材'}的用户实际问题"
            )
        if st.session_state.get("content_lab_material_confirmed"):
            st.success("业务信息已确认，可以生成自己的招生笔记。")

    active_profile_id = str(st.session_state.get(profile_key) or "__new__")
    active_profile = profile_map.get(active_profile_id)
    confirmed_profile = st.session_state.get("content_lab_confirmed_profile")
    planning_profile = (
        confirmed_profile
        if st.session_state.get("content_lab_material_confirmed")
        and isinstance(confirmed_profile, dict)
        else active_profile
    )
    if has_material and not st.session_state.get("content_lab_material_confirmed"):
        st.info("请先确认 AI 识别结果，再生成最终发布稿。")
    viral_cases = load_viral_cases(VIRAL_CASE_LIBRARY_PATH)
    case_map = {str(case.get("id")): case for case in viral_cases}
    reference_options = ["__current__", *case_map]
    selected_reference_id = str(
        st.session_state.get("content_lab_reference_case_id") or "__current__"
    )
    if selected_reference_id not in reference_options:
        selected_reference_id = "__current__"
        st.session_state["content_lab_reference_case_id"] = selected_reference_id
    if selected_reference_id == "__current__":
        selected_reference = {
            "id": "__current__",
            "title": material_title.strip()
            or (material_ocr_text.splitlines()[0] if material_ocr_text.strip() else "当前上传封面"),
            "reuse_structure": "封面信息 → 用户问题 → 解决方案 → 转化入口",
            "viral_reason": str(
                (material_suggestion or {}).get("core_selling_point")
                or (material_suggestion or {}).get("selling_direction")
                or "复用当前素材已确认的信息层级和内容方向"
            ),
            "opening_style": "从封面最明确的问题或结果直接切入",
            "trust_building": str(
                (material_suggestion or {}).get("brand_name")
                or (material_suggestion or {}).get("teacher_cues")
                or "只使用已确认的身份与素材建立信任"
            ),
            "pain_expression": str(
                (material_suggestion or {}).get("common_pain_points")
                or "承接封面中已经出现的用户问题"
            ),
            "conversion_style": str(
                (material_suggestion or {}).get("conversion_method")
                or "用自然行动引导承接内容价值"
            ),
        }
    else:
        selected_case = case_map[selected_reference_id]
        case_analysis = selected_case.get("analysis", {}) if isinstance(selected_case.get("analysis"), dict) else {}
        case_text = case_analysis.get("text", {}) if isinstance(case_analysis.get("text"), dict) else {}
        case_image = case_analysis.get("image", {}) if isinstance(case_analysis.get("image"), dict) else {}
        case_model = selected_case.get("model", {}) if isinstance(selected_case.get("model"), dict) else {}
        case_structure = case_text.get("structure_analysis", {}) if isinstance(case_text.get("structure_analysis"), dict) else {}
        case_title_analysis = case_text.get("title_analysis", {}) if isinstance(case_text.get("title_analysis"), dict) else {}
        reasons = case_text.get("viral_reasons", []) if isinstance(case_text.get("viral_reasons"), list) else []
        selected_reference = {
            "id": selected_reference_id,
            "title": str(selected_case.get("title") or "未命名案例"),
            "reuse_structure": str(
                case_model.get("core_structure")
                or case_model.get("content_structure")
                or case_text.get("copyable_template")
                or "问题 → 方法 → 证明 → 行动"
            ),
            "viral_reason": "；".join(str(item) for item in reasons[:2])
            or str(case_model.get("user_pain") or "复用该案例已沉淀的内容结构"),
            "opening_style": str(
                case_structure.get("opening") or case_model.get("opening_style") or "问题场景切入"
            ),
            "trust_building": str(
                case_model.get("trust_building")
                or case_image.get("trust_building")
                or "通过真实过程与专业信息建立信任"
            ),
            "pain_expression": str(
                case_title_analysis.get("pain_point")
                or case_model.get("user_pain")
                or "呈现目标用户的具体困扰"
            ),
            "conversion_style": str(
                case_model.get("conversion_style")
                or "在提供价值后自然引导下一步行动"
            ),
        }

    method_models = load_method_models(VIRAL_METHOD_MODEL_PATH)
    if method_models:
        method_map = {str(model.get("id")): model for model in method_models}
        selected_method_id = str(
            st.session_state.get("content_lab_method_id") or next(iter(method_map))
        )
        if selected_method_id not in method_map:
            selected_method_id = next(iter(method_map))
            st.session_state["content_lab_method_id"] = selected_method_id
        selected_method = method_map[selected_method_id]
    else:
        selected_method = {
            "id": f"case-{selected_reference['id']}",
            "name": f"{selected_reference['title']}复用结构",
            "source_count": 1,
            "core_structure": selected_reference["reuse_structure"],
        }

    can_generate = bool(
        has_material
        and st.session_state.get("content_lab_material_confirmed")
        and isinstance(planning_profile, dict)
    )
    st.markdown("## ④ 生成招生笔记")
    if st.button(
        "生成我的版本",
        type="primary",
        key="generate_content_lab_draft",
        width="stretch",
        disabled=not can_generate,
    ):
        try:
            generated_plan = build_content_plan(
                selected_method,
                {
                    "business_profile_id": planning_profile.get("id"),
                    "product_name": planning_profile.get("product_name") or "当前素材",
                    "brand_name": planning_profile.get("brand_name"),
                    "target_user": planning_profile.get("target_user") or "目标用户",
                    "common_pain_points": planning_profile.get("common_pain_points"),
                    "usage_scenario": planning_profile.get("usage_scenario"),
                    "conversion_method": planning_profile.get("conversion_method"),
                    "promotion_theme": material_title.strip()
                    or planning_profile.get("product_name"),
                    "core_selling_point": planning_profile.get("core_selling_point"),
                    "problem_to_solve": planning_profile.get("common_pain_points")
                    or f"围绕{planning_profile.get('product_name') or '当前素材'}的用户实际问题",
                },
            )
            generated_plan["reference_cases"] = [selected_reference]
            material_context = {
                "has_uploaded_image": bool(image_bytes),
                "image_width": int(st.session_state.get("content_lab_material_image_width") or 0),
                "image_height": int(st.session_state.get("content_lab_material_image_height") or 0),
                "image_format": str(st.session_state.get("content_lab_material_image_format") or ""),
                "uploaded_title": material_title.strip(),
                "uploaded_body": material_body.strip(),
                "ocr_text": material_ocr_text.strip(),
                "ai_recognition": material_suggestion or {},
                "confirmed_recognition": planning_profile,
                "selected_reference_case": selected_reference,
                "platform_settings": {
                    "platform": st.session_state.get("content_lab_platform", "小红书"),
                    "content_type": st.session_state.get(
                        "content_lab_content_type", "教育培训/课程咨询"
                    ),
                    "conversion_goal": st.session_state.get(
                        "content_lab_conversion_goal", "获取咨询线索"
                    ),
                },
            }
            with st.spinner("正在复用参考案例结构，生成标题、封面和完整正文..."):
                generated_draft = generate_content_lab_draft(
                    generated_plan,
                    material_context,
                    planning_profile,
                    selected_method,
                )
            if generated_draft:
                st.session_state["content_lab_current_plan"] = generated_plan
                st.session_state["content_lab_generated_draft"] = generated_draft
                st.session_state.pop("content_lab_draft_full_text", None)
                st.session_state.pop("content_lab_draft_selected_title", None)
                st.rerun()
            else:
                st.info("部分分析不可用，已保留当前文字内容，请稍后重试生成。")
        except ValueError as error:
            st.info("部分分析不可用，已使用文字内容继续生成。")

    generated_draft = st.session_state.get("content_lab_generated_draft")

    with st.expander("⚙️ 高级分析", expanded=False):
        st.markdown("#### 爆款结构分析")
        selected_reference_id = st.selectbox(
            "选择参考爆款",
            reference_options,
            format_func=lambda case_id: (
                "当前上传封面"
                if case_id == "__current__"
                else str(case_map[case_id].get("title") or "未命名案例")
            ),
            key="content_lab_reference_case_id",
        )
        st.write(f"**当前参考：** {selected_reference['title']}")
        st.write(f"**整体复用结构：** {selected_reference['reuse_structure']}")
        reference_columns = st.columns(2, gap="medium")
        reference_columns[0].write(
            f"**开头方式：** {selected_reference['opening_style']}"
        )
        reference_columns[0].write(
            f"**痛点表达：** {selected_reference['pain_expression']}"
        )
        reference_columns[1].write(
            f"**信任建立：** {selected_reference['trust_building']}"
        )
        reference_columns[1].write(
            f"**转化方式：** {selected_reference['conversion_style']}"
        )
        st.caption("只复用结构与方法，不复制案例原句、人物经历或未经确认的数据。")

    current_plan = st.session_state.get("content_lab_current_plan")
    if isinstance(current_plan, dict):
        with st.expander("生成依据", expanded=False):
            render_content_plan_card(current_plan, "current_content_plan")
            if st.button(
                "保存到我的内容方案",
                key="save_content_plan",
                width="stretch",
            ):
                save_content_plan(CONTENT_PLAN_PATH, current_plan)
                st.session_state["content_plan_notice"] = "内容方案已保存。"
                st.rerun()

    with st.expander("高级设置", expanded=False):
        st.markdown("#### 发布目标")
        setting_columns = st.columns(3, gap="small")
        setting_columns[0].selectbox(
            "平台",
            ["小红书"],
            key="content_lab_platform",
        )
        setting_columns[1].selectbox(
            "内容类型",
            ["教育培训/课程咨询"],
            key="content_lab_content_type",
        )
        setting_columns[2].selectbox(
            "目标",
            ["获取咨询线索"],
            key="content_lab_conversion_goal",
        )
        if isinstance(generated_draft, dict):
            render_content_lab_draft_details(generated_draft, "content_lab_draft")
            st.divider()
        st.markdown("#### 业务档案")
        if active_profile:
            st.caption(active_profile.get("brand_name") or "当前业务档案")
            profile_columns = st.columns(3, gap="medium")
            profile_columns[0].write(
                f"**产品：** {active_profile.get('product_name') or '未填写'}"
            )
            profile_columns[1].write(
                f"**用户：** {active_profile.get('target_user') or '未填写'}"
            )
            profile_columns[2].write(
                f"**场景：** {active_profile.get('usage_scenario') or '未填写'}"
            )
        else:
            st.caption("没有长期业务档案时，将优先使用本次 AI 识别结果。")

        selected_profile_id = st.selectbox(
            "选择业务档案",
            profile_options,
            format_func=lambda profile_id: (
                "＋ 新建业务档案"
                if profile_id == "__new__"
                else str(
                    profile_map[profile_id].get("brand_name")
                    or profile_map[profile_id].get("product_name")
                    or "未命名档案"
                )
            ),
            key=profile_key,
        )
        selected_profile = profile_map.get(selected_profile_id, {})
        editor_id = selected_profile_id if selected_profile_id != "__new__" else "new"
        with st.form(f"business_profile_form_{editor_id}"):
            editor_columns = st.columns(2, gap="medium")
            with editor_columns[0]:
                business_product_name = st.text_input(
                    "产品/服务名称",
                    value=str(selected_profile.get("product_name") or ""),
                )
                business_brand_name = st.text_input(
                    "品牌/IP名称",
                    value=str(selected_profile.get("brand_name") or ""),
                )
                business_target_user = st.text_input(
                    "目标用户",
                    value=str(selected_profile.get("target_user") or ""),
                )
            with editor_columns[1]:
                business_pain_points = st.text_area(
                    "常见用户痛点",
                    value=str(selected_profile.get("common_pain_points") or ""),
                    height=90,
                )
                business_usage_scenario = st.text_input(
                    "使用场景",
                    value=str(selected_profile.get("usage_scenario") or ""),
                )
                business_conversion_method = st.text_input(
                    "常用转化方式",
                    value=str(selected_profile.get("conversion_method") or ""),
                )
            save_profile = st.form_submit_button(
                "保存业务档案",
                type="primary",
                width="stretch",
            )
        if save_profile:
            try:
                saved_profile = save_business_profile(
                    BUSINESS_PROFILE_PATH,
                    {
                        **selected_profile,
                        "product_name": business_product_name,
                        "brand_name": business_brand_name,
                        "target_user": business_target_user,
                        "common_pain_points": business_pain_points,
                        "usage_scenario": business_usage_scenario,
                        "conversion_method": business_conversion_method,
                    },
                )
            except ValueError as error:
                st.warning(str(error))
            else:
                st.session_state["content_lab_pending_profile_id"] = saved_profile["id"]
                st.session_state["content_plan_notice"] = "业务档案已保存，后续生成将自动读取。"
                st.rerun()

        if method_models:
            st.divider()
            st.markdown("#### 方法模型")
            st.selectbox(
                "方法模型",
                list(method_map),
                format_func=lambda method_id: str(
                    method_map[method_id].get("name") or "未命名方法"
                ),
                key="content_lab_method_id",
            )
            st.caption(
                selected_method.get("core_structure")
                or selected_method.get("applicability")
                or "复用已沉淀的内容结构"
            )
        else:
            st.caption(f"当前方法：{selected_method.get('name') or '当前案例复用结构'}")

    saved_plans = load_content_plans(CONTENT_PLAN_PATH)
    with st.expander(f"我的内容方案 · {len(saved_plans)}", expanded=False):
        if not saved_plans:
            st.caption("还没有保存方案。生成策划卡后可保存到这里。")
        for plan in saved_plans:
            plan_id = str(plan.get("id") or "plan")
            render_content_plan_card(plan, f"saved_content_plan_{plan_id}")


def _build_current_growth_reference(
    material_title: str,
    material_ocr_text: str,
    suggestion: dict,
) -> dict:
    """Build the reusable structure for the current material without changing saved cases."""
    return {
        "id": "__current__",
        "title": material_title.strip()
        or (
            material_ocr_text.splitlines()[0]
            if material_ocr_text.strip()
            else "当前同行素材"
        ),
        "reuse_structure": "家长痛点 → 老师背书 → 方法证明 → 服务介绍 → 福利转化",
        "viral_reason": str(
            suggestion.get("core_selling_point")
            or suggestion.get("selling_direction")
            or "用明确人群、具体问题和低门槛行动降低家长决策成本"
        ),
        "opening_style": "从家长正在经历的具体问题直接切入",
        "trust_building": str(
            suggestion.get("brand_name")
            or suggestion.get("teacher_cues")
            or "用真实老师身份、教学过程和服务信息建立信任"
        ),
        "pain_expression": str(
            suggestion.get("common_pain_points")
            or "呈现目标家长正在面对的具体学习问题"
        ),
        "conversion_style": str(
            suggestion.get("conversion_method")
            or "先提供方法价值，再承接咨询或体验"
        ),
    }


def _generate_growth_v1_draft(
    *,
    planning_profile: dict,
    material_title: str,
    material_body: str,
    material_ocr_text: str,
    image_bytes: bytes,
    suggestion: dict,
    selected_reference: dict,
    selected_method: dict,
) -> None:
    """Generate a draft through the existing planning and LLM services."""
    generated_plan = build_content_plan(
        selected_method,
        {
            "business_profile_id": planning_profile.get("id"),
            "product_name": planning_profile.get("product_name") or "当前课程",
            "brand_name": planning_profile.get("brand_name"),
            "target_user": planning_profile.get("target_user") or "目标家长",
            "common_pain_points": planning_profile.get("common_pain_points"),
            "usage_scenario": planning_profile.get("usage_scenario"),
            "conversion_method": planning_profile.get("conversion_method"),
            "promotion_theme": material_title.strip()
            or planning_profile.get("product_name"),
            "core_selling_point": planning_profile.get("core_selling_point"),
            "problem_to_solve": planning_profile.get("common_pain_points")
            or f"围绕{planning_profile.get('product_name') or '当前课程'}的家长实际问题",
        },
    )
    generated_plan["reference_cases"] = [selected_reference]
    material_context = {
        "has_uploaded_image": bool(image_bytes),
        "image_width": int(
            st.session_state.get("content_lab_material_image_width") or 0
        ),
        "image_height": int(
            st.session_state.get("content_lab_material_image_height") or 0
        ),
        "image_format": str(
            st.session_state.get("content_lab_material_image_format") or ""
        ),
        "uploaded_title": material_title.strip(),
        "uploaded_body": material_body.strip(),
        "ocr_text": material_ocr_text.strip(),
        "ai_recognition": suggestion,
        "confirmed_recognition": planning_profile,
        "selected_reference_case": selected_reference,
        "platform_settings": {
            "platform": "小红书",
            "content_type": "教育培训/课程咨询",
            "conversion_goal": "获取咨询线索",
        },
    }
    generated_draft = generate_content_lab_draft(
        generated_plan,
        material_context,
        planning_profile,
        selected_method,
    )
    if not generated_draft:
        error_detail = get_last_error() or "未生成发布稿"
        print(f"Content growth draft generation failed: {error_detail}")
        raise ValueError(error_detail)
    st.session_state["content_lab_current_plan"] = generated_plan
    st.session_state["content_lab_generated_draft"] = generated_draft
    st.session_state.pop("content_lab_draft_full_text", None)
    st.session_state.pop("content_lab_draft_selected_title", None)


def render_content_growth_breakdown_v1(
    suggestion: dict,
    title: str,
    body: str,
    ocr_text: str,
    own_profile: dict,
) -> None:
    """Turn the reference analysis into an immediately usable adaptation direction."""
    def usable(value: object, fallback: str) -> str:
        text = str(value or "").strip()
        if not text or "未体现" in text or text in {"无", "暂无", "不明确"}:
            return fallback
        return text

    target_user = usable(suggestion.get("target_user"), "该案例未明确说明目标人群")
    pain_point = usable(
        suggestion.get("common_pain_points"),
        "该案例未提供足够信息来判断家长痛点",
    )
    selling_point = usable(
        suggestion.get("core_selling_point"),
        "该案例尚未形成清晰的继续阅读理由",
    )
    conversion = usable(
        suggestion.get("conversion_method"),
        "该案例未提供明确的转化方式",
    )
    own_business = str(
        own_profile.get("product_name") or own_profile.get("usage_scenario") or "你的课程"
    ).strip()
    own_user = str(own_profile.get("target_user") or target_user).strip()
    own_pain = str(
        own_profile.get("common_pain_points") or pain_point
    ).strip()
    title_direction = f"{own_user}遇到{own_pain}？先看{own_business}里的这一步"

    own_business = usable(own_business, "当前演示业务")
    own_user = usable(own_user, "目标学生家长")
    own_pain = usable(own_pain, "具体学习问题")
    st.markdown("## 第二步 · 拆解结果")
    with st.container(border=True):
        result_columns = st.columns(3, gap="medium")
        with result_columns[0]:
            st.markdown("### ✅ 值得借鉴")
            st.write(f"**目标人群：** {target_user}")
            st.write(f"**用户问题：** {pain_point}")
            st.write(f"**继续阅读理由：** {selling_point}")
        with result_columns[1]:
            st.markdown("### ⚠️ 不建议照搬")
            st.write("不要复制原案例的老师身份、学员经历、成绩数据或未经验证的效果描述。")
            if "未提供" in conversion or "未明确" in conversion:
                st.write("该案例没有清晰转化路径，需要结合自己的真实服务重新设计。")
            else:
                st.write(f"原案例转化方式仅作参考：{conversion}")
        with result_columns[2]:
            st.markdown("### 🎯 如何用于我的账号")
            st.write(f"围绕 **{own_business}**，先回应 **{own_pain}**。")
            st.write(f"标题方向：{title_direction}")
        st.caption("只复制人群、痛点和内容结构；缺失信息不会被当作事实用于生成。")


def render_content_growth_assistant_v1(profile: dict[str, str]) -> None:
    """A focused four-step operator workflow built on existing services and state."""
    render_page_hero(
        "🔥 小红书教育招生内容助手",
        "拆同行跑量内容，生成你的招生笔记",
        "把同行跑量内容丢进来，看懂能复制什么，快速变成自己的招生笔记。",
    )
    st.markdown(
        """
        <div class="step-indicator">
            <span class="active">找参考爆款</span>
            <span>AI告诉我为什么它能招生</span>
            <span>生成我的招生笔记</span>
            <span>一键审核</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    notice = st.session_state.pop("content_plan_notice", "")
    if notice:
        st.success(notice)

    business_profiles = load_business_profiles(BUSINESS_PROFILE_PATH)
    profile_map = {str(item.get("id")): item for item in business_profiles}
    active_profile = next(
        iter(profile_map.values()),
        DEMO_BUSINESS_PROFILE.copy() if PUBLIC_DEMO else {},
    )
    if PUBLIC_DEMO:
        active_profile = DEMO_BUSINESS_PROFILE.copy()
        st.info("当前使用虚构演示账号：林老师（演示账号）· 初中数学学习规划。你可以在生成前临时修改。")

    st.markdown("## 第一步 · 找参考爆款")
    st.write("把你觉得好的内容丢进来，链接、截图或正文任选一种。")
    input_tabs = st.tabs(
        ["小红书链接", "爆款截图", "粘贴笔记正文"]
    )
    with input_tabs[0]:
        link_row = st.columns([4, 1], gap="small", vertical_alignment="bottom")
        link_row[0].text_input(
            "小红书公开链接",
            key="content_growth_link_url",
            placeholder="粘贴同行笔记链接",
        )
        link_row[1].button(
            "读取内容",
            key="content_growth_import_link_v1",
            on_click=import_content_growth_link,
            type="primary",
            width="stretch",
        )
        link_notice = st.session_state.pop("content_growth_link_notice", "")
        if link_notice:
            st.info(link_notice)
    with input_tabs[1]:
        screenshot_columns = st.columns([1.2, 0.8], gap="large")
        with screenshot_columns[0]:
            material_upload = st.file_uploader(
                "上传同行爆款截图",
                type=["png", "jpg", "jpeg", "webp"],
                key="content_lab_material_upload",
            )
            st.caption("支持拖拽上传，也可以复制微信、小红书或浏览器截图后粘贴。")
            pasted_material = None
            paste_button, component_error = load_paste_image_button()
            if paste_button is None:
                st.caption(component_error)
            else:
                try:
                    paste_result = paste_button(
                        label="点击这里后按 Ctrl+V 粘贴截图",
                        key="content_lab_material_paste_v1",
                        text_color="#ffffff",
                        background_color="#ef4f5f",
                        hover_background_color="#dc3f50",
                        errors="ignore",
                    )
                    pasted_material, paste_message = extract_pasted_image(paste_result)
                    if pasted_material is None:
                        st.caption(paste_message)
                except Exception as error:
                    log_paste_component_error(error, "content growth v1")
                    st.caption(PASTE_UNAVAILABLE_MESSAGE)
        material_payload = None
        if pasted_material is not None:
            material_payload = process_content_lab_material_image(
                pasted_material, "clipboard"
            )
        elif material_upload is not None:
            material_payload = process_content_lab_material_image(
                material_upload, "upload"
            )
        stored_image = st.session_state.get("content_lab_material_image_bytes", b"")
        with screenshot_columns[1]:
            if stored_image:
                st.image(stored_image, caption="当前同行素材", width="stretch")
            else:
                st.caption("上传后在这里确认素材。")
    with input_tabs[2]:
        st.text_input(
            "同行笔记标题（可选）",
            key="content_lab_material_title",
            placeholder="粘贴原标题",
        )
        st.text_area(
            "同行笔记正文",
            key="content_lab_material_body",
            placeholder="直接粘贴正文或主要文案",
            height=180,
        )

    material_title = str(
        st.session_state.get("content_lab_material_title") or ""
    )
    material_body = str(st.session_state.get("content_lab_material_body") or "")
    material_ocr_text = str(
        st.session_state.get("content_lab_material_ocr_text")
        or st.session_state.get("content_lab_cover_text")
        or ""
    )
    image_bytes = st.session_state.get("content_lab_material_image_bytes", b"")
    has_material = bool(
        image_bytes
        or material_title.strip()
        or material_body.strip()
        or material_ocr_text.strip()
    )
    material_key = hashlib.sha256(
        "\n".join(
            (
                str(st.session_state.get("content_lab_material_image_hash") or ""),
                material_title.strip(),
                material_body.strip(),
                material_ocr_text.strip(),
            )
        ).encode("utf-8")
    ).hexdigest()

    analysis_is_current = (
        has_material
        and st.session_state.get("content_lab_material_analysis_key") == material_key
        and isinstance(st.session_state.get("content_lab_material_suggestion"), dict)
    )
    if has_material and not analysis_is_current:
        st.caption("内容已准备好。点击后才会开始 AI 拆解，不会因离开输入框自动运行。")
        start_breakdown = st.button(
            "开始拆解同行内容",
            type="primary",
            use_container_width=True,
            key=f"start_content_breakdown_{material_key[:10]}",
        )
        if start_breakdown:
            with st.status("正在拆解选题、用户心理和成交结构...", expanded=True) as status:
                st.write("正在读取标题、正文与封面信息")
                suggestion, material_error = analyze_content_lab_material(
                    title=material_title,
                    body=material_body,
                    ocr_text=material_ocr_text,
                    image_bytes=image_bytes,
                    image_width=int(
                        st.session_state.get("content_lab_material_image_width") or 0
                    ),
                    image_height=int(
                        st.session_state.get("content_lab_material_image_height") or 0
                    ),
                    image_format=str(
                        st.session_state.get("content_lab_material_image_format") or ""
                    ),
                    creator_profile=profile,
                    fallback_profile=active_profile,
                )
                st.write("正在整理可借鉴点与不建议照搬的内容")
                status.update(label="拆解完成", state="complete", expanded=False)
            st.session_state["content_lab_material_analysis_key"] = material_key
            st.session_state["content_lab_material_suggestion"] = suggestion
            st.session_state["content_lab_material_error"] = material_error
            st.session_state.pop("content_lab_generated_draft", None)
            for field, value in suggestion.items():
                saved_value = str(active_profile.get(field) or "").strip()
                st.session_state[f"content_lab_confirm_{field}"] = saved_value or value
            st.rerun()

    suggestion = (
        st.session_state.get("content_lab_material_suggestion")
        if analysis_is_current
        else None
    )
    if not has_material:
        st.caption("添加一篇同行内容后，点击“开始拆解同行内容”查看结果。")
    elif isinstance(suggestion, dict):
        st.markdown("## 第二步 · AI告诉我为什么它能招生")
        current_profile = {
            "product_name": str(
                st.session_state.get("content_lab_confirm_product_name") or ""
            ).strip(),
            "brand_name": str(
                st.session_state.get("content_lab_confirm_brand_name") or ""
            ).strip(),
            "target_user": str(
                st.session_state.get("content_lab_confirm_target_user") or ""
            ).strip(),
            "usage_scenario": str(
                st.session_state.get("content_lab_confirm_usage_scenario") or ""
            ).strip(),
            "common_pain_points": str(
                suggestion.get("common_pain_points") or ""
            ).strip(),
            "core_selling_point": str(
                st.session_state.get("content_lab_confirm_core_selling_point") or ""
            ).strip(),
            "conversion_method": str(
                st.session_state.get("content_lab_confirm_conversion_method") or ""
            ).strip(),
        }
        render_content_growth_breakdown_v1(
            suggestion,
            material_title,
            material_body,
            material_ocr_text,
            current_profile,
        )

        st.markdown("## 第三步 · 生成我的招生笔记")
        with st.container(border=True):
            account_row = st.columns([4, 1], gap="small", vertical_alignment="center")
            with account_row[0]:
                st.markdown(
                    f"**当前账号：** "
                    f"{current_profile['brand_name'] or '老师信息待补充'}　·　"
                    f"{current_profile['product_name'] or current_profile['usage_scenario'] or '课程待补充'}　·　"
                    f"{current_profile['target_user'] or '目标家长待补充'}"
                )
            with account_row[1]:
                with st.popover("修改", width="stretch"):
                    st.text_input(
                        "我的业务",
                        key="content_lab_confirm_product_name",
                        placeholder="例如：初中数学一对一辅导",
                    )
                    st.text_input(
                        "老师身份",
                        key="content_lab_confirm_brand_name",
                        placeholder="真实姓名、教龄、擅长领域",
                    )
                    st.text_input(
                        "课程 / 服务",
                        key="content_lab_confirm_usage_scenario",
                        placeholder="例如：学情诊断与错题规划",
                    )
                    st.text_input(
                        "目标家长",
                        key="content_lab_confirm_target_user",
                    )
                    st.text_area(
                        "服务优势",
                        key="content_lab_confirm_core_selling_point",
                        height=80,
                    )
                    st.text_input(
                        "本次福利",
                        key="content_lab_confirm_conversion_method",
                        placeholder="没有真实福利可以留空",
                    )
                    st.caption("修改后关闭窗口，生成时会直接使用最新信息。")

        generate = st.button(
            "🔥 生成我的招生笔记",
            type="primary",
            key="generate_content_growth_v11",
            width="stretch",
        )

        if generate:
            planning_profile = {
                "id": str(active_profile.get("id") or ""),
                "product_name": str(
                    st.session_state.get("content_lab_confirm_product_name") or ""
                ).strip(),
                "brand_name": str(
                    st.session_state.get("content_lab_confirm_brand_name") or ""
                ).strip(),
                "target_user": str(
                    st.session_state.get("content_lab_confirm_target_user") or ""
                ).strip(),
                "usage_scenario": str(
                    st.session_state.get("content_lab_confirm_usage_scenario") or ""
                ).strip(),
                "common_pain_points": str(
                    suggestion.get("common_pain_points") or ""
                ).strip(),
                "core_selling_point": str(
                    st.session_state.get("content_lab_confirm_core_selling_point")
                    or ""
                ).strip(),
                "conversion_method": str(
                    st.session_state.get("content_lab_confirm_conversion_method")
                    or ""
                ).strip(),
            }
            selected_reference = _build_current_growth_reference(
                material_title, material_ocr_text, suggestion
            )
            method_models = load_method_models(VIRAL_METHOD_MODEL_PATH)
            selected_method = (
                method_models[0]
                if method_models
                else {
                    "id": "current-growth-structure",
                    "name": "当前同行内容复用结构",
                    "source_count": 1,
                    "core_structure": selected_reference["reuse_structure"],
                }
            )
            try:
                with st.spinner("正在结合同行结构和你的真实业务生成招生笔记..."):
                    _generate_growth_v1_draft(
                        planning_profile=planning_profile,
                        material_title=material_title,
                        material_body=material_body,
                        material_ocr_text=material_ocr_text,
                        image_bytes=image_bytes,
                        suggestion=suggestion,
                        selected_reference=selected_reference,
                        selected_method=selected_method,
                    )
            except ValueError:
                st.info("生成暂时不可用，已保留当前素材和业务信息，请稍后重试。")
            else:
                st.rerun()

    generated_draft = st.session_state.get("content_lab_generated_draft")
    if isinstance(generated_draft, dict):
        st.markdown("## 第四步 · 审核发布")
        render_content_lab_draft(generated_draft, "content_lab_draft")

    with st.expander("🔬 高级玩法（运营人员使用）", expanded=False):
        st.caption("案例库、方法模型、共同结构和案例对比集中在这里，不影响日常生成流程。")
        render_viral_case_library("content_growth_professional")


render_content_lab = render_content_growth_assistant_v1



CASE_SUBJECT_OPTIONS = ("数学", "英语", "语文", "物理", "化学", "综合教育")
CASE_AUDIENCE_OPTIONS = ("家长", "学生", "老师", "教培机构", "其他", "小学生家长", "初中家长", "高中家长", "学生本人")
CASE_CONTENT_TYPE_OPTIONS = ("招生转化", "知识分享", "家长痛点", "成绩案例", "方法技巧", "活动招生", "其他", "学习方法", "案例展示")
CASE_SCENARIO_OPTIONS = ("日常获客", "暑假/寒假招生", "考试节点", "成绩提升", "品牌展示", "社群运营", "日常运营", "活动招生", "暑假招生", "寒假招生")


def infer_case_subject(title: str, body: str) -> str:
    source = f"{title}\n{body}"
    for subject in ("数学", "英语", "语文", "物理", "化学"):
        if subject in source:
            return subject
    return "综合教育"


def infer_case_tags(title: str, body: str) -> list[str]:
    source = f"{title}\n{body}"
    tags = [infer_case_subject(title, body)]
    for keyword in ("小学", "初中", "高中", "小升初", "中考", "高考", "家长焦虑", "提分", "招生"):
        if keyword in source:
            tags.append(keyword)
    return list(dict.fromkeys(tags))


def build_case_filter_options(
    cases: list[dict],
    key: str,
    defaults: tuple[str, ...],
) -> list[str]:
    existing = []
    for case in cases:
        dimensions = case.get("tag_dimensions", {}) if isinstance(case.get("tag_dimensions"), dict) else {}
        value = str(dimensions.get(key, "")).strip()
        if value:
            existing.append(value)
    return ["全部", *dict.fromkeys([*defaults, *existing])]


def render_viral_case_detail(case: dict, key_prefix: str = "viral_case") -> None:
    original = case.get("original_material", {}) if isinstance(case.get("original_material"), dict) else {}
    analysis = case.get("analysis", {}) if isinstance(case.get("analysis"), dict) else {}
    text_analysis = analysis.get("text", {}) if isinstance(analysis.get("text"), dict) else {}
    image_analysis = analysis.get("image", {}) if isinstance(analysis.get("image"), dict) else {}
    title_analysis = text_analysis.get("title_analysis", {}) if isinstance(text_analysis.get("title_analysis"), dict) else {}
    structure_analysis = text_analysis.get("structure_analysis", {}) if isinstance(text_analysis.get("structure_analysis"), dict) else {}
    copy_structure = image_analysis.get("copy_structure", {}) if isinstance(image_analysis.get("copy_structure"), dict) else {}
    model = case.get("model", {}) if isinstance(case.get("model"), dict) else {}
    cover = case.get("cover", {}) if isinstance(case.get("cover"), dict) else {}
    cover_visual = (
        case.get("cover_visual_analysis", {})
        if isinstance(case.get("cover_visual_analysis"), dict)
        else {}
    )
    source_info = case.get("source_info", {}) if isinstance(case.get("source_info"), dict) else {}
    operation_review = (
        case.get("operation_review", {})
        if isinstance(case.get("operation_review"), dict)
        else {}
    )
    actual_metrics = (
        operation_review.get("actual_metrics", {})
        if isinstance(operation_review.get("actual_metrics"), dict)
        else {}
    )
    tag_dimensions = case.get("tag_dimensions", {}) if isinstance(case.get("tag_dimensions"), dict) else {}
    viral_reasons = text_analysis.get("viral_reasons", [])
    if not isinstance(viral_reasons, list):
        viral_reasons = []
    suggestions = text_analysis.get("suggestions", [])
    if not isinstance(suggestions, list):
        suggestions = []

    def short_conclusion(
        value: object,
        fallback: str = "当前拆解未提供",
        limit: int = 72,
    ) -> str:
        if isinstance(value, list):
            text = "；".join(str(item).strip() for item in value if str(item).strip())
        else:
            text = str(value or "").strip()
        if not text:
            return fallback
        first_sentence = re.split(r"(?<=[。！？；])", text, maxsplit=1)[0].strip()
        return first_sentence if len(first_sentence) <= limit else first_sentence[: limit - 1].rstrip() + "…"

    cover_image_data = str(
        cover.get("image_data")
        or original.get("cover_image")
        or cover.get("source_url")
        or ""
    ).strip()
    core_summary = (
        operation_review.get("save_reason")
        or (viral_reasons[0] if viral_reasons else "")
        or title_analysis.get("click_attraction")
    )
    pain_point = title_analysis.get("pain_point") or model.get("user_pain")
    content_structure = model.get("content_structure") or "；".join(
        str(structure_analysis.get(key) or "").strip()
        for key in ("opening", "middle", "ending")
        if str(structure_analysis.get(key) or "").strip()
    )
    conversion_elements = image_analysis.get("conversion_elements", [])
    if not isinstance(conversion_elements, list):
        conversion_elements = [conversion_elements] if conversion_elements else []
    conversion_summary = (
        "、".join(str(item).strip() for item in conversion_elements if str(item).strip())
        or operation_review.get("conversion")
        or structure_analysis.get("ending")
    )
    suitable_scenario = (
        model.get("suitable_scenario")
        or tag_dimensions.get("scenario")
        or tag_dimensions.get("content_type")
    )
    trust_summary = image_analysis.get("trust_building") or model.get("trust_building") or next(
        (
            reason
            for reason in viral_reasons
            if any(keyword in str(reason) for keyword in ("信任", "老师", "案例", "经验", "证明"))
        ),
        "当前拆解未明确说明信任来源",
    )
    core_parts = [
        f"抓住{short_conclusion(pain_point, '', 72).rstrip('，。！？； ')[:8]}" if pain_point else "",
        f"用{short_conclusion(trust_summary, '', 72).rstrip('，。！？； ')[:8]}建立信任"
        if trust_summary
        else "",
        f"以{short_conclusion(conversion_summary, '', 72).rstrip('，。！？； ')[:8]}促进行动"
        if conversion_summary
        else "",
    ]
    structured_core = "，".join(part for part in core_parts if part)
    compact_core_summary = (
        structured_core + "。"
        if structured_core
        else short_conclusion(core_summary, "当前拆解尚未形成明确结论", 35)
    )
    if len(compact_core_summary) > 35:
        compact_core_summary = compact_core_summary[:34].rstrip("，。； ") + "。"
    image_template = image_analysis.get("reusable_template") or (
        " → ".join(str(item).strip() for item in cover_visual.get("information_layers", []) if str(item).strip())
        if isinstance(cover_visual.get("information_layers"), list)
        else ""
    )
    title_template = model.get("reusable_title_formula") or model.get("title_structure")
    body_template = model.get("content_structure") or content_structure
    click_factors = image_analysis.get("click_factors", [])
    if not isinstance(click_factors, list):
        click_factors = [click_factors] if click_factors else []
    avoid_copying = image_analysis.get("avoid_copying", [])
    if not isinstance(avoid_copying, list):
        avoid_copying = [avoid_copying] if avoid_copying else []
    font_hierarchy = (
        cover_visual.get("font_hierarchy", {})
        if isinstance(cover_visual.get("font_hierarchy"), dict)
        else {}
    )
    focus_items = (
        cover_visual.get("visual_focus", [])
        if isinstance(cover_visual.get("visual_focus"), list)
        else []
    )
    information_layers = (
        cover_visual.get("information_layers", [])
        if isinstance(cover_visual.get("information_layers"), list)
        else []
    )
    design_role = next(
        (str(item).strip() for item in click_factors if str(item).strip()),
        title_analysis.get("click_attraction"),
    )

    st.markdown("### 案例复盘")
    st.markdown("#### 原始封面图片")
    if cover_image_data:
        st.image(cover_image_data, caption="案例封面", width=420)
    else:
        with st.container(border=True):
            st.caption("案例封面")
            st.write("当前案例未保存封面")

    st.markdown("### 为什么有效")
    with st.container(border=True):
        st.caption("分析依据：基于OCR文字、图片结构和已有信息推断，未接入视觉模型时需人工复核。")
        visual_items = (
            (
                "第一眼吸引点",
                focus_items[0] if focus_items else image_analysis.get("first_glance") or design_role,
            ),
            ("用户心理", pain_point),
            ("信任来源", trust_summary),
        )
        visual_cards = st.columns(3, gap="medium")
        for column, (label, value) in zip(visual_cards, visual_items):
            with column:
                with st.container(border=True):
                    st.caption(label)
                    st.write(short_conclusion(value, "无法确认", 50))

    st.markdown("### 爆款核心")
    with st.container(border=True):
        st.caption("一句话总结")
        st.subheader(compact_core_summary)
        st.write(f"**适用场景：** {short_conclusion(suitable_scenario)}")
        if text_analysis.get("score") is not None:
            st.caption(
                f"内容研究参考 {text_analysis['score']}/100 · 根据结构完整度、痛点表达和转化设计进行参考分析，不代表真实流量预测。"
            )

    collection_checks = (
        ("痛点明确", bool(str(pain_point or "").strip()), short_conclusion(pain_point)),
        (
            "信任建立",
            bool(str(trust_summary or "").strip()) and "未明确" not in str(trust_summary),
            short_conclusion(trust_summary),
        ),
        (
            "转化路径",
            bool(str(conversion_summary or "").strip()),
            short_conclusion(conversion_summary),
        ),
    )
    collection_score = sum(passed for _, passed, _ in collection_checks)
    star_count = round(collection_score / len(collection_checks) * 5)
    star_display = "★" * star_count + "☆" * (5 - star_count)
    st.markdown("### 收藏价值评分")
    collection_columns = st.columns(4, gap="small")
    collection_columns[0].metric("收藏价值", star_display)
    for column, (label, passed, reason) in zip(collection_columns[1:], collection_checks):
        with column:
            with st.container(border=True):
                st.caption(label)
                st.write(("★ " if passed else "☆ ") + reason)

    st.markdown("### 三个可复制点")
    copy_cards = st.columns(3, gap="medium")
    for column, (label, value) in zip(
        copy_cards,
        (
            ("① 用户痛点", pain_point),
            ("② 内容结构", content_structure),
            ("③ 转化方式", conversion_summary),
        ),
    ):
        with column:
            with st.container(border=True):
                st.caption(label)
                st.write(short_conclusion(value))

    st.markdown("### 可复用方法")
    st.caption("只复用内容组织方式，不照搬课程名称、数据或个体经历。")
    default_avoid = short_conclusion(
        avoid_copying or ["个人身份", "虚假效果承诺", "未经验证的数据"]
    )
    reusable_methods = (
        (
            "图片模板",
            suitable_scenario or "教育内容封面复盘",
            str(image_template or "主标题：[用户痛点]\n身份背书：[真实身份/经验]\n行动信息：[已核实的服务入口]"),
            short_conclusion(
                focus_items[0] if focus_items else image_analysis.get("first_glance") or image_template
            ),
            default_avoid,
        ),
        (
            "标题正文模板",
            suitable_scenario or "教育内容标题与正文复盘",
            f"标题：{short_conclusion(title_template)}\n正文：{short_conclusion(body_template)}",
            f"原标题：{str(case.get('title') or '当前案例标题').strip()}\n开头：{short_conclusion(structure_analysis.get('opening'))}",
            "不要照搬原案例身份、课程名称和未经验证的结果数据",
        ),
        (
            "转化模板",
            suitable_scenario or "教育内容转化设计",
            "用户痛点 → 建立信任 → 展示真实结果 → 行动入口",
            short_conclusion(conversion_summary),
            "不要照搬价格、联系方式或效果承诺",
        ),
    )
    copy_id_seed = hashlib.sha256(str(case.get("id") or case.get("title") or "case").encode("utf-8")).hexdigest()[:10]
    reuse_cards = st.columns(3, gap="medium")
    for index, (column, method) in enumerate(zip(reuse_cards, reusable_methods), start=1):
        method_type, method_scene, template_text, example_text, avoid_text = method
        with column:
            with st.container(border=True):
                st.caption("方法类型")
                st.write(f"**{method_type}**")
                st.caption("适用场景")
                st.write(short_conclusion(method_scene))
                st.caption("可复制模板")
                st.write(template_text)
                st.caption("示例")
                st.write(example_text)
                with st.expander("查看注意事项", expanded=False):
                    st.caption("不建议照搬")
                    st.write(avoid_text)
                render_clipboard_button(
                    template_text,
                    f"copy-saved-viral-template-{copy_id_seed}-{index}",
                    "复制模板",
                    "模板已复制",
                )

    full_review_text = "\n".join(
        [
            "爆款核心：",
            compact_core_summary,
            "",
            "三个复制点：",
            f"1. 用户痛点：{short_conclusion(pain_point)}",
            f"2. 内容结构：{short_conclusion(content_structure)}",
            f"3. 转化方式：{short_conclusion(conversion_summary)}",
            "",
            "图片模板：",
            reusable_methods[0][2],
            "",
            "标题正文模板：",
            reusable_methods[1][2],
            "",
            "转化路径：",
            reusable_methods[2][2],
        ]
    )
    render_clipboard_button(
        full_review_text,
        f"copy-saved-viral-full-review-{copy_id_seed}",
        "复制全部复盘",
        "完整复盘已复制",
    )

    with st.expander("查看详细拆解", expanded=False):
        st.markdown("#### 标题拆解")
        title_cards = st.columns(2, gap="medium")
        title_items = (
            ("目标用户", title_analysis.get("target_audience") or tag_dimensions.get("audience")),
            ("用户问题", title_analysis.get("pain_point") or model.get("user_pain")),
            ("标题结构", model.get("title_structure")),
            ("点击理由", title_analysis.get("click_attraction")),
        )
        for index, (label, value) in enumerate(title_items):
            with title_cards[index % 2]:
                with st.container(border=True):
                    st.caption(label)
                    st.write(short_conclusion(value))
        st.markdown("#### 正文结构")
        body_cards = st.columns(3, gap="medium")
        for column, (key, label) in zip(
            body_cards,
            (("opening", "开头"), ("middle", "中段"), ("ending", "结尾")),
        ):
            with column:
                with st.container(border=True):
                    st.caption(label)
                    st.write(short_conclusion(structure_analysis.get(key)))
        st.markdown("#### 用户痛点与转化设计")
        detail_cards = st.columns(2, gap="medium")
        detail_cards[0].write("**用户痛点：** " + short_conclusion(pain_point))
        detail_cards[1].write(
            "**转化设计：** "
            + short_conclusion(conversion_summary, "当前案例未发现明确转化元素")
        )

    with st.expander("优化建议", expanded=False):
        advice_items = [str(item).strip() for item in suggestions if str(item).strip()]
        if image_analysis.get("reusable_template"):
            advice_items.append(f"封面结构：{image_analysis['reusable_template']}")
        advice_items.append("复用具体课程、数据或个体经历前，需要重新核实。")
        for index, item in enumerate(advice_items[:5], start=1):
            with st.container(border=True):
                st.caption(f"建议 {index}")
                st.write(short_conclusion(item))

    with st.expander("原始素材与运营数据", expanded=False):
        source_columns = st.columns(2)
        source_columns[0].write(f"**来源：** {source_info.get('platform') or original.get('source') or '未标注'}")
        source_columns[1].write(f"**账号：** {source_info.get('source_account') or '未标注'}")
        source_columns[0].write(f"**日期：** {source_info.get('publish_date') or '未记录'}")
        source_columns[1].write(f"**状态：** {operation_review.get('verification_status') or '待验证'}")
        source_columns[1].write(f"**爆款等级：** {operation_review.get('viral_level') or '普通'}")
        original_url = source_info.get("original_url") or original.get("source_url")
        if original_url:
            st.write(f"**原始链接：** {original_url}")
        st.write(f"**标题：** {case.get('title') or '未保存标题'}")
        st.text_area(
            "原始正文",
            value=str(case.get("content") or "未保存正文"),
            height=160,
            disabled=True,
            key=f"{key_prefix}_{case.get('id', '')}_original_content",
        )
        if cover.get("ocr_text"):
            st.write(f"**封面文字：** {short_conclusion(cover.get('ocr_text'))}")
        metric_columns = st.columns(4)
        metric_columns[0].metric("点赞", actual_metrics.get("likes") if actual_metrics.get("likes") != "" else "—")
        metric_columns[1].metric("收藏", actual_metrics.get("favorites") if actual_metrics.get("favorites") != "" else "—")
        metric_columns[2].metric("评论", actual_metrics.get("comments") if actual_metrics.get("comments") != "" else "—")
        metric_columns[3].metric("转化", operation_review.get("conversion") or "—")

    case_id = str(case.get("id", ""))
    edit_requested = st.session_state.get(f"{key_prefix}_edit_case_id") == case_id
    with st.expander("编辑案例标签", expanded=edit_requested):
        current_case_type = str(tag_dimensions.get("content_type") or "其他").strip()
        case_type_options = list(
            dict.fromkeys(["招生转化", "知识分享", "家长痛点", "成绩案例", "方法技巧", "活动招生", "其他", current_case_type])
        )
        current_audiences = [
            item.strip()
            for item in re.split(r"[、,，]", str(tag_dimensions.get("audience") or ""))
            if item.strip()
        ]
        current_scenarios = [
            item.strip()
            for item in re.split(r"[、,，]", str(tag_dimensions.get("scenario") or ""))
            if item.strip()
        ]
        with st.form(f"{key_prefix}_tag_form_{case_id}"):
            edited_case_type = st.radio(
                "案例类型",
                case_type_options,
                index=case_type_options.index(current_case_type),
                horizontal=True,
            )
            edited_audiences = st.multiselect(
                "主要面向（可选）",
                list(dict.fromkeys(["家长", "学生", "老师", "教培机构", "其他", *current_audiences])),
                default=current_audiences,
            )
            edited_scenarios = st.multiselect(
                "使用场景（可选）",
                list(dict.fromkeys(["日常获客", "暑假/寒假招生", "考试节点", "成绩提升", "品牌展示", "社群运营", *current_scenarios])),
                default=current_scenarios,
            )
            classified_values = {
                str(tag_dimensions.get("subject") or "").strip(),
                current_case_type,
                *current_audiences,
                *current_scenarios,
            }
            edited_tags = st.text_input(
                "标签（可编辑，用逗号分隔）",
                value="，".join(
                    str(tag)
                    for tag in case.get("tags", [])
                    if str(tag).strip() and str(tag).strip() not in classified_values
                ),
                key=f"{key_prefix}_{case_id}_extra_tags",
            )
            save_tags = st.form_submit_button("保存标签", type="primary", use_container_width=True)
        if save_tags:
            parsed_tags = [item.strip() for item in re.split(r"[,，]", edited_tags) if item.strip()]
            selected_dimensions = {
                "subject": str(tag_dimensions.get("subject") or infer_case_subject(str(case.get("title") or ""), str(case.get("content") or ""))),
                "audience": "、".join(edited_audiences),
                "content_type": edited_case_type,
                "scenario": "、".join(edited_scenarios),
            }
            update_viral_case_tags(
                VIRAL_CASE_LIBRARY_PATH,
                case_id,
                selected_dimensions,
                [*parsed_tags, edited_case_type, *edited_audiences, *edited_scenarios],
            )
            st.session_state["viral_library_notice"] = "案例标签已更新。"
            st.rerun()

    with st.expander("编辑来源与运营复盘", expanded=edit_requested):
        with st.form(f"{key_prefix}_operation_form_{case_id}"):
            operation_columns = st.columns(2)
            current_platform = str(source_info.get("platform") or "").strip()
            platform_options = [
                "未标注",
                *dict.fromkeys(["小红书", "抖音", "视频号", "其他", *([current_platform] if current_platform else [])]),
            ]
            with operation_columns[0]:
                edited_platform = st.selectbox(
                    "来源平台",
                    platform_options,
                    index=platform_options.index(current_platform) if current_platform in platform_options else 0,
                )
                edited_publish_date = st.text_input(
                    "发布日期",
                    value=str(source_info.get("publish_date") or ""),
                )
                edited_source_account = st.text_input(
                    "来源账号",
                    value=str(source_info.get("source_account") or ""),
                )
            with operation_columns[1]:
                edited_original_url = st.text_input(
                    "原始链接",
                    value=str(source_info.get("original_url") or original.get("source_url") or ""),
                )
                status_options = ["待验证", "已验证有效", "不推荐复用"]
                current_status = str(operation_review.get("verification_status") or "待验证")
                edited_status = st.selectbox(
                    "是否验证有效",
                    status_options,
                    index=status_options.index(current_status) if current_status in status_options else 0,
                )
                edited_conversion = st.text_input(
                    "转化情况",
                    value=str(operation_review.get("conversion") or ""),
                )
                level_options = ["普通", "优秀", "爆款"]
                current_level = str(operation_review.get("viral_level") or "普通")
                edited_viral_level = st.selectbox(
                    "爆款等级",
                    level_options,
                    index=level_options.index(current_level) if current_level in level_options else 0,
                )
            edited_save_reason = st.text_area(
                "为什么保存这个案例",
                value=str(operation_review.get("save_reason") or ""),
                height=80,
            )
            edited_metric_columns = st.columns(3)
            with edited_metric_columns[0]:
                edited_likes = st.text_input("点赞", value=str(actual_metrics.get("likes") or ""))
            with edited_metric_columns[1]:
                edited_favorites = st.text_input("收藏", value=str(actual_metrics.get("favorites") or ""))
            with edited_metric_columns[2]:
                edited_comments = st.text_input("评论", value=str(actual_metrics.get("comments") or ""))
            edited_notes = st.text_area(
                "运营备注",
                value=str(operation_review.get("notes") or ""),
                height=100,
            )
            save_operation = st.form_submit_button("保存运营复盘", type="primary", use_container_width=True)
        if save_operation:
            update_viral_case_operation(
                VIRAL_CASE_LIBRARY_PATH,
                case_id,
                {
                    "platform": "" if edited_platform == "未标注" else edited_platform,
                    "original_url": edited_original_url,
                    "publish_date": edited_publish_date,
                    "source_account": edited_source_account,
                },
                {
                    "save_reason": edited_save_reason,
                    "verification_status": edited_status,
                    "viral_level": edited_viral_level,
                    "actual_metrics": {
                        "likes": edited_likes,
                        "favorites": edited_favorites,
                        "comments": edited_comments,
                    },
                    "conversion": edited_conversion,
                    "notes": edited_notes,
                },
            )
            st.session_state["viral_library_notice"] = "案例运营复盘已更新。"
            st.rerun()



def deduplicate_viral_cases_for_display(cases: list[dict]) -> list[dict]:
    """Keep only the newest visible record for duplicate IDs or source links."""
    ordered_cases = sorted(
        cases,
        key=lambda case: str(case.get("created_at") or ""),
        reverse=True,
    )
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    visible_cases: list[dict] = []
    for case in ordered_cases:
        case_id = str(case.get("id") or "").strip()
        source_info = case.get("source_info") if isinstance(case.get("source_info"), dict) else {}
        original = case.get("original_material") if isinstance(case.get("original_material"), dict) else {}
        source_url = str(
            source_info.get("original_url")
            or original.get("source_url")
            or ""
        ).strip().rstrip("/").casefold()
        if case_id and case_id in seen_ids:
            continue
        if source_url and source_url in seen_urls:
            continue
        visible_cases.append(case)
        if case_id:
            seen_ids.add(case_id)
        if source_url:
            seen_urls.add(source_url)
    return visible_cases


def render_viral_case_library(key_prefix: str) -> None:
    st.markdown("## 🔥 爆款案例库")
    notice = st.session_state.pop("viral_library_notice", "")
    if notice:
        st.success(notice)
    saved_cases = deduplicate_viral_cases_for_display(load_viral_cases(VIRAL_CASE_LIBRARY_PATH))
    if not saved_cases:
        with st.container(border=True):
            st.markdown("### 还没有保存案例")
            st.write("先在招生笔记助手完成一次同行内容拆解，再把值得复用的结构沉淀到这里。")
            st.button(
                "前往招生笔记助手体验",
                type="primary",
                use_container_width=True,
                on_click=open_workspace_page,
                args=("招生笔记助手",),
                key=f"{key_prefix}_open_growth_assistant",
            )
        return
    show_case_library = st.toggle(
        f"展开案例库 · {len(saved_cases)}",
        value=False,
        key=f"{key_prefix}_show_case_library",
    )
    st.caption("案例库：保存历史爆款案例")
    if saved_cases and not show_case_library:
        filtered_cases = saved_cases
        st.caption("案例库已收起，需要查找或打开案例时再展开。")
    elif not saved_cases:
        st.info("还没有保存案例。完成一次案例拆解后，可将结果保存到研究库。")
        filtered_cases: list[dict] = []
    else:
        search_query = st.text_input(
            "搜索案例",
            placeholder="搜索标题、正文或标签",
            key=f"{key_prefix}_search",
        )
        filter_columns = st.columns(5)
        filter_values: dict[str, str] = {}
        for column, key, label, defaults in zip(
            filter_columns,
            ("subject", "audience", "content_type", "scenario"),
            ("学科", "用户群体", "内容类型", "使用场景"),
            (CASE_SUBJECT_OPTIONS, CASE_AUDIENCE_OPTIONS, CASE_CONTENT_TYPE_OPTIONS, CASE_SCENARIO_OPTIONS),
        ):
            with column:
                selected = st.selectbox(
                    label,
                    build_case_filter_options(saved_cases, key, defaults),
                    key=f"{key_prefix}_filter_{key}",
                )
                filter_values[key] = "" if selected == "全部" else selected

        with filter_columns[4]:
            selected_verification = st.selectbox(
                "验证状态",
                ["全部", "待验证", "已验证有效", "不推荐复用"],
                key=f"{key_prefix}_filter_verification",
            )
        verification_filter = "" if selected_verification == "全部" else selected_verification

        filtered_cases = filter_viral_cases(
            saved_cases,
            query=search_query,
            verification_status=verification_filter,
            **filter_values,
        )
        st.caption(f"找到 {len(filtered_cases)} 个案例")
        if not filtered_cases:
            st.info("没有符合当前条件的案例，请调整搜索词或筛选条件。")

        for case in filtered_cases:
            dimensions = case.get("tag_dimensions", {}) if isinstance(case.get("tag_dimensions"), dict) else {}
            cover = case.get("cover", {}) if isinstance(case.get("cover"), dict) else {}
            source_info = case.get("source_info", {}) if isinstance(case.get("source_info"), dict) else {}
            operation_review = (
                case.get("operation_review", {})
                if isinstance(case.get("operation_review"), dict)
                else {}
            )
            with st.container(border=True):
                image_column, info_column, action_column = st.columns([0.8, 2.8, 0.7], gap="medium")
                with image_column:
                    cover_image_data = str(cover.get("image_data") or "")
                    if cover_image_data.startswith("data:image/"):
                        st.image(cover_image_data, width=140)
                    else:
                        st.caption("案例 · 暂无封面")
                with info_column:
                    st.caption("案例")
                    st.markdown(f"### {escape(case.get('title') or '未命名案例')}")
                    metadata_columns = st.columns(3)
                    metadata = (
                        ("状态", operation_review.get("verification_status") or "待验证"),
                        ("平台", source_info.get("platform")),
                        ("学科", dimensions.get("subject")),
                        ("用户", dimensions.get("audience")),
                        ("类型", dimensions.get("content_type")),
                        ("场景", dimensions.get("scenario")),
                    )
                    for index, (label, value) in enumerate(metadata):
                        metadata_columns[index % 2].write(f"**{label}：** {value or '未分类'}")
                    st.caption(f"创建时间：{case.get('created_at') or '旧版案例未记录'}")
                with action_column:
                    if st.button(
                        "查看案例",
                        key=f"{key_prefix}_open_{case['id']}",
                        use_container_width=True,
                    ):
                        st.session_state[f"{key_prefix}_selected_case"] = case["id"]
                        st.session_state.pop(f"{key_prefix}_edit_case_id", None)
                    with st.popover("更多操作", width="stretch"):
                        if st.button(
                            "编辑案例",
                            key=f"{key_prefix}_edit_{case['id']}",
                            width="stretch",
                        ):
                            st.session_state[f"{key_prefix}_selected_case"] = case["id"]
                            st.session_state[f"{key_prefix}_edit_case_id"] = case["id"]
                            st.rerun()
                        delete_confirmed = st.checkbox(
                            "删除后无法恢复",
                            key=f"{key_prefix}_card_delete_confirm_{case['id']}",
                        )
                        if st.button(
                            "删除案例",
                            disabled=not delete_confirmed,
                            key=f"{key_prefix}_card_delete_{case['id']}",
                            width="stretch",
                        ):
                            if delete_viral_case(VIRAL_CASE_LIBRARY_PATH, str(case["id"])):
                                st.session_state.pop(f"{key_prefix}_selected_case", None)
                                st.session_state.pop(f"{key_prefix}_edit_case_id", None)
                                st.session_state["viral_library_notice"] = "案例已删除，无法恢复。"
                                st.rerun()

        selected_id = st.session_state.get(f"{key_prefix}_selected_case", "")
        selected_case = next((case for case in filtered_cases if case.get("id") == selected_id), None)
        if selected_case:
            st.divider()
            render_viral_case_detail(selected_case, key_prefix)

    st.divider()
    show_combined = st.toggle(
        "展开共同结构分析",
        value=False,
        key=f"{key_prefix}_show_combined",
    )
    st.caption("共同结构分析：提炼重复出现的方法")
    if show_combined:
        render_combined_case_workspace(filtered_cases, key_prefix)
    show_methods = st.toggle(
        "展开我的方法库",
        value=False,
        key=f"{key_prefix}_show_methods",
    )
    st.caption("我的方法库：沉淀自己的运营模型")
    if show_methods:
        render_method_model_library(key_prefix)
    show_comparison = st.toggle(
        "展开案例对比",
        value=False,
        key=f"{key_prefix}_show_comparison",
    )
    st.caption("案例对比：比较多个案例共同结构")
    if show_comparison:
        render_case_comparison_workspace(filtered_cases, key_prefix)


def render_case_comparison_workspace(cases: list[dict], key_prefix: str) -> None:
    st.markdown("## 案例对比")
    st.caption("并排查看已保存案例的标题、痛点、封面与正文结构；仅整理现有拆解结果。")
    if len(cases) < 2:
        st.info("至少需要 2 个符合当前筛选条件的案例才能对比。")
        return

    case_map = {str(case.get("id")): case for case in cases}
    selected_ids = st.multiselect(
        "选择 2—5 个案例",
        list(case_map),
        format_func=lambda case_id: str(case_map[case_id].get("title") or "未命名案例"),
        max_selections=5,
        key=f"{key_prefix}_comparison_case_ids",
    )
    if st.button(
        "案例对比",
        type="primary",
        disabled=not 2 <= len(selected_ids) <= 5,
        key=f"{key_prefix}_comparison_button",
        use_container_width=True,
    ):
        st.session_state[f"{key_prefix}_case_comparison"] = build_case_comparison(
            [case_map[case_id] for case_id in selected_ids]
        )

    comparison = st.session_state.get(f"{key_prefix}_case_comparison")
    if not isinstance(comparison, dict):
        return
    if set(comparison.get("case_ids", [])) != set(selected_ids):
        st.caption("案例选择已变化，请重新点击“案例对比”。")
        return

    st.markdown("### 标题结构对比")
    st.dataframe(comparison.get("title_rows", []), hide_index=True, width="stretch")

    st.markdown("### 用户痛点对比")
    st.dataframe(comparison.get("pain_rows", []), hide_index=True, width="stretch")
    common_pains = comparison.get("common_pains", [])
    if common_pains:
        st.caption(
            "共同出现：" + "；".join(
                f"{item.get('value', '')}（{item.get('count', 0)}个案例）" for item in common_pains
            )
        )
    else:
        st.caption("当前所选案例未出现完全相同的痛点表达。")

    st.markdown("### 封面结构对比")
    st.dataframe(comparison.get("cover_rows", []), hide_index=True, width="stretch")

    st.markdown("### 正文结构对比")
    st.dataframe(comparison.get("body_rows", []), hide_index=True, width="stretch")


def render_ranked_case_patterns(
    title: str,
    items: list[dict],
    source_count: int,
    empty_text: str,
) -> None:
    st.markdown(f"**{title}**")
    if not items:
        st.caption(empty_text)
        return
    for item in items:
        st.write(f"- {item.get('value', '')} · {item.get('count', 0)}/{source_count}")


def render_combined_case_workspace(cases: list[dict], key_prefix: str) -> None:
    st.markdown("## 共同结构分析")
    st.caption("从当前筛选结果中选择多个案例，统计已保存拆解字段中的共同规律，不重新生成文案。")
    if len(cases) < 2:
        st.info("至少需要 2 个符合当前筛选条件的案例，才能分析共同结构。")
        return

    case_map = {str(case.get("id")): case for case in cases}
    selected_ids = st.multiselect(
        "选择用于分析的案例",
        list(case_map),
        format_func=lambda case_id: str(case_map[case_id].get("title") or "未命名案例"),
        key=f"{key_prefix}_combined_case_ids",
    )
    if st.button(
        "分析共同结构",
        type="primary",
        disabled=len(selected_ids) < 2,
        key=f"{key_prefix}_combine_button",
        use_container_width=True,
    ):
        selected_cases = [case_map[case_id] for case_id in selected_ids]
        st.session_state[f"{key_prefix}_combined_analysis"] = build_combined_case_analysis(selected_cases)

    analysis = st.session_state.get(f"{key_prefix}_combined_analysis")
    if not isinstance(analysis, dict):
        return
    active_ids = set(case_map)
    analysis_ids = set(analysis.get("source_case_ids", []))
    if not analysis_ids.issubset(active_ids) or analysis_ids != set(selected_ids):
        st.caption("案例选择或筛选条件已变化，请重新分析共同结构。")
        return

    source_count = int(analysis.get("source_count") or 0)
    st.success(f"已完成 {source_count} 篇案例的共同结构分析。")
    pattern_columns = st.columns(3, gap="large")
    with pattern_columns[0]:
        render_ranked_case_patterns("标题规律", analysis.get("title_patterns", []), source_count, "暂无统一标题规律")
    with pattern_columns[1]:
        render_ranked_case_patterns("用户痛点规律", analysis.get("pain_points", []), source_count, "暂无重复痛点")
    with pattern_columns[2]:
        render_ranked_case_patterns("内容结构规律", analysis.get("content_patterns", []), source_count, "暂无统一正文结构")
    with st.container(border=True):
        render_ranked_case_patterns(
            "共同视觉规律",
            analysis.get("visual_patterns", []),
            source_count,
            "所选案例缺少可确认的重复视觉规律",
        )
    template_columns = st.columns(2, gap="large")
    with template_columns[0]:
        render_ranked_case_patterns("高频标题模板", analysis.get("title_templates", []), source_count, "暂无标题模板")
    with template_columns[1]:
        render_ranked_case_patterns("高频正文模板", analysis.get("body_templates", []), source_count, "暂无正文模板")

    analysis_key = hashlib.sha256(
        json.dumps(analysis.get("source_case_ids", []), ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]
    with st.form(f"{key_prefix}_method_model_form_{analysis_key}"):
        model_name = st.text_input(
            "模型名称",
            placeholder="例如：初中数学家长焦虑型招生模型",
        )
        applicability = st.text_input(
            "适用场景",
            value=str(analysis.get("suggested_applicability") or ""),
        )
        core_structure = st.text_input(
            "核心结构",
            value=str(analysis.get("suggested_core_structure") or ""),
        )
        save_model = st.form_submit_button("保存为方法模型", type="primary", use_container_width=True)
    if save_model:
        try:
            save_method_model(
                VIRAL_METHOD_MODEL_PATH,
                {
                    "name": model_name,
                    "source_case_ids": analysis.get("source_case_ids", []),
                    "applicability": applicability,
                    "core_structure": core_structure,
                    "analysis": analysis,
                },
            )
        except ValueError as error:
            st.warning(str(error))
        else:
            st.session_state["viral_library_notice"] = "方法模型已保存。"
            st.rerun()


def render_method_model_library(key_prefix: str) -> None:
    method_models = load_method_models(VIRAL_METHOD_MODEL_PATH)
    saved_cases = deduplicate_viral_cases_for_display(load_viral_cases(VIRAL_CASE_LIBRARY_PATH))
    case_title_map = {
        str(case.get("id") or ""): str(case.get("title") or "未命名案例")
        for case in saved_cases
        if str(case.get("id") or "").strip()
    }
    st.markdown(f"## 我的方法库 · {len(method_models)}")
    if not method_models:
        st.caption("尚未沉淀方法。选择多个案例完成共同结构分析后即可保存为运营笔记。")
        return
    for model in method_models:
        with st.container(border=True):
            st.markdown(f"### {escape(model.get('name') or '未命名方法模型')}")
            analysis = model.get("analysis", {}) if isinstance(model.get("analysis"), dict) else {}
            method_value = str(
                model.get("core_structure")
                or model.get("applicability")
                or "从多个案例中沉淀可复用的运营结构"
            ).strip()
            if len(method_value) > 56:
                method_value = method_value[:55].rstrip("，。； ") + "…"
            st.caption(method_value)
            source_case_ids = model.get("source_case_ids", [])
            if not isinstance(source_case_ids, list):
                source_case_ids = []
            source_case_titles = [
                case_title_map.get(str(case_id), f"历史案例 {index}")
                for index, case_id in enumerate(source_case_ids, start=1)
            ]
            linked_source_count = sum(
                1 for case_id in source_case_ids if str(case_id) in case_title_map
            )
            displayed_source_count = (
                linked_source_count
                or len(source_case_ids)
                or int(model.get("source_count") or analysis.get("source_count") or 0)
            )
            common_rule_count = sum(
                len(analysis.get(field, [])) if isinstance(analysis.get(field), list) else 0
                for field in ("title_patterns", "pain_points", "content_patterns", "visual_patterns")
            )
            source_case_label = "、".join(source_case_titles) or f"{displayed_source_count} 个历史案例"
            st.write(f"**来源案例：** {displayed_source_count} 个")
            copy_text = "\n".join(
                [
                    f"方法名称：{model.get('name') or '未命名方法模型'}",
                    f"方法价值：{method_value}",
                    f"来源案例：{source_case_label}",
                    f"适用场景：{model.get('applicability') or '未标注'}",
                    f"核心结构：{model.get('core_structure') or '未沉淀'}",
                ]
            )
            copy_id = hashlib.sha256(
                str(model.get("id") or model.get("name") or "method").encode("utf-8")
            ).hexdigest()[:10]
            render_clipboard_button(
                copy_text,
                f"copy-method-summary-{key_prefix}-{copy_id}",
                "复制方法",
                "方法已复制",
            )
            with st.expander("展开完整模板", expanded=False):
                st.write(f"**适用场景：** {model.get('applicability') or '未标注'}")
                st.write(f"**可复制结构：** {model.get('core_structure') or '未沉淀'}")
                st.write(f"**实际示例：** {source_case_label}")
                st.write("**不建议照搬：** 原案例身份、课程名称、效果数据和未经验证的承诺。")
                with st.expander("查看全部共同规律", expanded=False):
                    st.caption(f"来源案例：{source_case_label} · 共同规律：{common_rule_count} 条")
                    source_count = displayed_source_count
                    render_ranked_case_patterns("标题规律", analysis.get("title_patterns", []), source_count, "暂无")
                    render_ranked_case_patterns("用户痛点规律", analysis.get("pain_points", []), source_count, "暂无")
                    render_ranked_case_patterns("内容结构规律", analysis.get("content_patterns", []), source_count, "暂无")
                    render_ranked_case_patterns("标题模板", analysis.get("title_templates", []), source_count, "暂无")
                    render_ranked_case_patterns("正文模板", analysis.get("body_templates", []), source_count, "暂无")
                    render_ranked_case_patterns("共同视觉规律", analysis.get("visual_patterns", []), source_count, "暂无可确认的共同视觉规律")


def render_history_and_assets() -> None:
    render_page_hero(
        "历史与资产",
        "统一查看审核记录和已保存的爆款案例",
        "当前阶段保留原审核历史，并新增爆款案例资产视图。",
    )
    audit_tab, cases_tab = st.tabs(["审核记录", "爆款案例"])
    with audit_tab:
        render_history_section()
    with cases_tab:
        render_viral_case_library("asset_library")


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
        ("viral_uploader_key", 0),
        ("is_reviewing", False),
        ("draft_title", ""),
        ("draft_body", ""),
        ("draft_image_text", ""),
        ("cover_image_description", ""),
        ("demo_mode", False),
    ):
        if key not in st.session_state:
            st.session_state[key] = default

    navigation_descriptions = {
        "内容审核中心": "审核标题、正文和封面",
        "协作审核 V2": "人工确认建议稿并复检",
        "招生笔记助手": "拆同行内容，生成招生笔记",
        "历史与资产": "查看审核记录与案例资产",
        "审核规则中心": "维护内容审核标准",
    }
    navigation_icons = {
        "内容审核中心": "🛡️",
        "协作审核 V2": "🔁",
        "招生笔记助手": "🔥",
        "历史与资产": "📚",
        "审核规则中心": "⚙️",
    }
    legacy_navigation = {
        "创作工作台": "内容审核中心",
        "封面诊断": "内容审核中心",
        "爆款拆解": "招生笔记助手",
        "爆款研究库": "招生笔记助手",
        "历史记录": "历史与资产",
        "规则管理": "审核规则中心",
        "创作者资料": "招生笔记助手",
        "内容实验室": "招生笔记助手",
        "内容增长助手": "招生笔记助手",
    }
    forest_target = st.session_state.pop("forest_navigate_to", None)
    if forest_target in navigation_descriptions:
        st.session_state["workspace_page"] = forest_target
    current_page = st.session_state.get("workspace_page")
    if current_page is None and os.getenv("NOTEGUARD_FOREST_PAPER", "0") == "1":
        st.session_state["workspace_page"] = "协作审核 V2"
    if current_page in legacy_navigation:
        st.session_state["workspace_page"] = legacy_navigation[current_page]
    with st.sidebar:
        st.markdown("## NoteGuard AI")
        st.caption("教育内容运营助手")
        workspace_page = st.radio(
            "导航",
            list(navigation_descriptions),
            format_func=lambda page: f"{navigation_icons[page]}  {page}\n    {navigation_descriptions[page]}",
            label_visibility="collapsed",
            key="workspace_page",
        )
        st.markdown(
            f'<div class="sidebar-note">{escape(navigation_descriptions[workspace_page])}</div>',
            unsafe_allow_html=True,
        )
        if st.session_state.get("demo_mode"):
            st.success("Demo 模式 · 不调用真实 AI")
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
    if st.session_state.get("demo_mode"):
        creator_profile = load_creator_profile(DEMO_CREATOR_PROFILE_PATH)

    if workspace_page == "审核规则中心":
        render_rule_management()
        return

    if workspace_page == "历史与资产":
        render_history_and_assets()
        return

    if workspace_page == "招生笔记助手":
        render_content_lab(creator_profile)
        return
    if workspace_page == "协作审核 V2":
        render_workflow_v2(rules)
        return
    render_page_hero(
        "内容审核中心",
        "审核供应商交付的标题、正文和封面",
        "快速判断是否存在违规风险，定位命中表达，并查看最小范围替代建议。",
    )
    st.markdown(
        """
        <div class="quick-entry-grid">
            <div class="quick-entry-card">
                <strong>🛡️ 合规结论</strong>
                <span>判断是否存在风险、风险等级和规则命中数量。</span>
            </div>
            <div class="quick-entry-card">
                <strong>📍 问题定位</strong>
                <span>定位标题、正文和图片文字中的具体问题表达。</span>
            </div>
            <div class="quick-entry-card">
                <strong>✏️ 最小修改</strong>
                <span>只提供命中片段的替代表达，不自动改写原文。</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    demo_entry, demo_exit = st.columns([3, 1])
    with demo_entry:
        st.button(
            "✨ 体验 Demo",
            type="primary",
            use_container_width=True,
            on_click=load_public_demo,
            key="public_demo_button",
        )
    with demo_exit:
        if st.session_state.get("demo_mode"):
            st.button("退出 Demo", use_container_width=True, on_click=exit_public_demo)
    if st.session_state.get("demo_mode"):
        st.info("当前为 Demo 模式 · 结果来自公开脱敏示例，不调用真实 AI API。")
    st.markdown(
        """
        <div class="trust-strip">
            <strong>适用于教育内容审核</strong>
            <span>图文笔记</span>
            <span>视频脚本</span>
            <span>封面文案</span>
            <span>结果仅作发布前辅助检查</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="step-indicator"><span class="active">① 提交内容</span><span>② 查看审核结论</span><span>③ 按优先级修改</span></div>',
        unsafe_allow_html=True,
    )
    completion_placeholder = st.empty()
    progress_placeholder = st.empty()

    workspace_notice = st.session_state.pop("workspace_notice", "")
    if workspace_notice:
        st.info(workspace_notice)

    with st.container(border=True):
        st.markdown('<div class="module-eyebrow">① 上传内容</div>', unsafe_allow_html=True)
        st.markdown('<div class="module-title">✍️ 上传内容</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="module-subtitle">上传封面并输入正文，NoteGuard 会直接告诉你标题、封面和正文应该先改哪里。</div>',
            unsafe_allow_html=True,
        )
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
            st.markdown(
                f'<div class="input-hint">已输入 {len(title) + len(body)} 字 · 支持正文、视频脚本或封面文案</div>',
                unsafe_allow_html=True,
            )
        with input_right:
            st.markdown(
                """
                <div class="experience-card">
                    <strong>✨ 体验完整流程</strong>
                    <p>加载一条教育内容示例，快速体验规则检测、问题定位和替代表达。</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.button(
                "✨ 加载示例笔记",
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
                st.image(active_image_bytes, caption="封面已添加，已进入内容审核中的封面分析", use_container_width=True)
                recognized_cover_text = st.session_state.get("cover_text", "").strip()
                render_image_analysis_status(recognized_cover_text)
                if recognized_cover_text:
                    with st.expander("查看已识别的封面文字", expanded=False):
                        st.text(recognized_cover_text)
                else:
                    st.button(
                        "重新识别封面文字",
                        key="retry_workspace_cover_ocr",
                        on_click=retry_workspace_cover_ocr,
                        args=(active_image_bytes, creator_profile, rules),
                        use_container_width=True,
                    )
                st.button(
                    "删除图片",
                    key="delete_workspace_image",
                    on_click=delete_current_image,
                    use_container_width=True,
                )
                if recognized_cover_text:
                    st.caption("封面 OCR 文字已加入本次合规审核。")

        action_left, action_right = st.columns([2, 1])
        with action_left:
            review_button_slot = st.empty()
            start_review = review_button_slot.button(
                "分析当前笔记",
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
            st.session_state["scroll_to_review_results"] = True

    image_text = (
        st.session_state.get("cover_text", "")
        or st.session_state.get("draft_image_text", "")
    )
    active_image_bytes = get_current_image_bytes()
    has_image = bool(active_image_bytes)
    has_review = st.session_state["review_started"] and bool(
        title.strip() or body.strip() or has_image
    )
    findings: list[Finding] = []
    cover_findings: list[Finding] = []
    cover_analysis = None
    if has_image:
        active_image_key = hashlib.sha256(active_image_bytes).hexdigest()
        if st.session_state.get("cover_analysis_image_key") == active_image_key:
            cover_analysis = st.session_state.get("cover_analysis")
        vision_context = st.session_state.get("cover_vision_context") or {}
        if vision_context:
            cover_analysis = {**vision_context, **(cover_analysis or {})}
    backend_analysis = build_backend_image_analysis(
        image_text,
        cover_analysis,
        creator_profile,
        title,
        body,
    )

    if has_review:
        findings = check_text(title=title, body=body, rules=rules)
        if image_text.strip():
            cover_findings = check_text(title="", body=image_text, rules=rules)
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
        title_generation_body = build_title_generation_context(body, backend_analysis)
        title_context_key = json.dumps(
            {
                "rewrite_key": rewrite_key,
                "generation_context": title_generation_body,
                "creator_profile": creator_profile,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        if st.session_state.get("safe_rewrite_key") == rewrite_key:
            rewrite_result = st.session_state["safe_rewrite_result"]
        else:
            rewrite_result = rewrite_with_local_rules(title, body, findings)
        if st.session_state.get("title_generation_key") == title_context_key:
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
        all_detected_findings = [*findings, *cover_findings]
        risk_level, risk_summary, risk_class = get_risk_level(all_detected_findings)
        safety_score, safety_status = get_content_safety_score(all_detected_findings)
        highlighted_title = build_highlighted_text(title, findings, "标题")
        highlighted_body = build_highlighted_text(body, findings, "正文")
        risk_detail_rows = [
            {**row, "位置": finding.position}
            for row, finding in zip(build_risk_detail_rows(findings), findings)
        ] + [
            {**row, "位置": "封面"}
            for row in build_risk_detail_rows(cover_findings)
        ]
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
        upsert_visible_history(
            create_history_record(
                record_id=review_run_id,
                title=title,
                body=body,
                safety_score=safety_score,
                risk_level=risk_level,
                risk_items=risk_detail_rows,
                rewritten_title=rewritten_title,
                rewritten_body=rewritten_body,
                image_ocr_text=image_text if has_image else "",
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

    st.markdown('<div id="review-results"></div>', unsafe_allow_html=True)
    if st.session_state.pop("scroll_to_review_results", False):
        st.toast("审核完成，已定位到审核结论。", icon="✅")
        components.html(
            """
            <script>
            setTimeout(() => {
              const target = window.parent.document.getElementById("review-results");
              if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
            }, 150);
            </script>
            """,
            height=0,
        )

    with st.container(border=True):
        st.markdown('<div class="module-eyebrow">② 审核结论</div>', unsafe_allow_html=True)
        st.markdown('<div class="module-title">合规审核结果</div>', unsafe_allow_html=True)
        st.caption("依据当前规则库检查标题、正文和图片 OCR 文字，只展示合规风险与最小修改建议。")
        if has_review:
            all_compliance_findings = [*findings, *cover_findings]
            compliance_column, level_column, count_column = st.columns(3, gap="medium")
            compliance_status = (
                "高风险，不建议发布"
                if any(item.severity == "high" for item in all_compliance_findings)
                else "存在修改项"
                if all_compliance_findings
                else "无明显风险"
            )
            display_risk_level, _, _ = get_risk_level(all_compliance_findings)
            compliance_column.metric("审核结论", compliance_status)
            level_column.metric("风险等级", display_risk_level)
            count_column.metric("命中规则数量", len(all_compliance_findings))

            severity_order = {"high": 0, "medium": 1, "low": 2}
            positioned_findings = sorted(
                [
                    *((item, item.position) for item in findings),
                    *((item, "封面") for item in cover_findings),
                ],
                key=lambda pair: severity_order.get(pair[0].severity, 3),
            )
            top_issues = positioned_findings[:3]
            st.markdown("### 优先处理的问题")
            issue_columns = st.columns(3, gap="medium")
            for index, (item, position) in enumerate(top_issues):
                with issue_columns[index]:
                    with st.container(border=True):
                        priority = "高" if item.severity == "high" else "中" if item.severity == "medium" else "低"
                        st.caption(f"{priority}风险 · {position}")
                        st.write(f"**原始片段：** {item.term}")
                        st.write(f"**风险类型：** {item.category}")
                        st.write(f"**风险原因：** {item.reason}")
            if not top_issues:
                st.success("标题、正文和图片文字未命中当前规则库中的明确风险。")

            feedback = build_audit_feedback(findings, cover_findings)
            render_clipboard_button(
                feedback,
                "copy-audit-feedback",
                "复制审核反馈",
                "审核反馈已复制",
            )
        else:
            st.info("提交标题、正文或封面后，点击“分析当前笔记”查看审核结论。")

    with st.expander("问题定位与左右对比", expanded=has_review):
        if not has_review:
            st.info("完成内容分析后，可在这里查看标题、正文和封面的具体命中位置。")
        else:
            render_audit_highlights(title, body, image_text, findings, cover_findings)

    return

    if False:  # Legacy optimization UI retained for state compatibility; no longer rendered.
        with st.expander("1. 修改标题", expanded=True):
            if not has_review:
                st.info("完成内容诊断后，可生成更适合发布测试的标题方案。")
            else:
                st.caption("结合目标用户、搜索关键词、点击动机和内容定位，生成适合小红书发布测试的标题方案。")
                title_button_label = "重新生成标题方案" if title_candidates else "生成更适合发布测试的标题方案"
                if st.button(title_button_label, type="primary", use_container_width=True, key="title_generation_button"):
                    with st.spinner("正在结合正文、封面和创作者资料生成标题方案..."):
                        candidates = resolve_demo_or_live(
                            st.session_state.get("demo_mode", False),
                            DEMO_TITLES,
                            lambda: generate_title_candidates(
                                title,
                                title_generation_body,
                                findings,
                                creator_profile=creator_profile,
                            ),
                        )
                        publishing_rules = [rule for rule in rules if rule.severity != "low"]
                        reviews = review_title_candidates(candidates, publishing_rules) if candidates else []
                        st.session_state["title_generation_key"] = title_context_key
                        st.session_state["title_candidates"] = [review.safe_title for review in reviews]
                        st.session_state["title_candidate_reviews"] = reviews
                        st.session_state["title_generation_error"] = "" if candidates else get_last_error()
                    st.rerun()
                if title_candidate_reviews:
                    render_title_candidate_reviews(
                        title_candidate_reviews,
                        creator_profile,
                        title,
                        body,
                        backend_analysis,
                    )
                elif title_candidates:
                    render_title_candidates(title_candidates)
                elif title_generation_error:
                    st.warning("标题生成暂不可用，请检查 AI 服务配置。")

        with st.expander("2. 修改封面文案", expanded=False):
            if has_image:
                render_workspace_image_insight(
                    has_image,
                    backend_analysis,
                    image_text,
                    creator_profile,
                )
            else:
                st.info("上传封面后，这里会显示封面传递给谁、用户第一眼看到什么，以及最优先修改的文案。")

        with st.expander("3. 生成发布稿", expanded=False):
            if "note_generation_topic" not in st.session_state:
                st.session_state["note_generation_topic"] = st.session_state.get("draft_title", "")
            st.caption("根据图片、案例截图、课程海报、课堂照片或文字素材，生成一篇可直接继续编辑的小红书发布稿。")
            image_bytes = get_current_image_bytes()
            current_image_hash = hashlib.sha256(image_bytes).hexdigest() if image_bytes else ""
            if current_image_hash and st.session_state.get("note_mode_image_hash") != current_image_hash:
                st.session_state["note_generation_mode"] = "根据图片生成"
                st.session_state["note_mode_image_hash"] = current_image_hash
            elif not image_bytes and st.session_state.get("note_generation_mode") == "根据图片生成":
                st.session_state["note_generation_mode"] = "根据文字生成"
            generation_mode = st.radio(
                "生成来源",
                GENERATION_MODES,
                horizontal=True,
                key="note_generation_mode",
            )
            image_mode = generation_mode == "根据图片生成"
            ocr_text = "\n".join(st.session_state.get("cover_ocr_lines", []))
            corrected_cover_text = (
                st.session_state.get("cover_text", "")
                or st.session_state.get("draft_image_text", "")
            ).strip()
            image_context = build_image_source_context(
                image_bytes,
                ocr_text,
                corrected_cover_text,
                cover_analysis=backend_analysis,
            )
            rule_constraints = build_rule_constraints(rules)
            viral_examples = load_viral_examples(VIRAL_EXAMPLES_PATH) if image_mode else []
            if image_context:
                image_context["rule_constraints"] = rule_constraints
            if image_mode:
                st.caption("封面识别 → 图片内容分析 → 内容结构重组 → 完整发布稿。")
            else:
                st.caption("根据当前标题、正文和主题补齐开头、方法结构与收藏点。")
            topic = st.text_input(
                "主题/关键词（可选）",
                placeholder="可补充主题；图片模式可留空",
                key="note_generation_topic",
            )
            if image_mode:
                content_direction = "图片驱动固定结构"
                length_range = "800—1000字"
                include_intro = any(
                    creator_profile.get(field, "").strip()
                    for field in ("name", "subjects", "personal_experience")
                )
                include_service = any(
                    creator_profile.get(field, "").strip()
                    for field in ("teaching_format", "session_duration", "pricing", "teaching_features")
                )
                include_action = True
                include_tags = True
            else:
                content_direction = st.session_state.get("note_content_direction", "自动判断")
                length_range = st.session_state.get("note_length_range", "500—700字")
                include_intro = st.session_state.get("note_include_intro", False)
                include_service = st.session_state.get("note_include_service", False)
                include_action = st.session_state.get("note_include_action", True)
                include_tags = st.session_state.get("note_include_tags", True)

            with st.expander("高级设置", expanded=False):
                if image_mode:
                    st.info("固定结构：用户痛点 → 老师背书 → 课程/服务 → 优势 → 行动引导")
                    st.caption("素材较短时会自动生成完整图文结构，无需先准备长正文。")
                    st.caption("老师介绍和课程信息只会使用已保存的创作者资料，不会自动补造。")
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
                    include_intro = st.checkbox("加入老师介绍", key="note_include_intro")
                    include_service = st.checkbox("加入课程信息", key="note_include_service")
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
                    ("封面内容", bool(corrected_cover_text or ocr_text.strip())),
                    ("创作者资料", any(value.strip() for value in creator_profile.values())),
                )
                if available
            ]
            st.caption(
                "已读取：" + ("、".join(available_materials) if available_materials else "等待补充素材")
            )

            generate_requested = st.button(
                "生成完整发布稿",
                type="primary",
                use_container_width=True,
                key="note_generation_button",
            )
            regenerate_requested = st.session_state.pop("note_regenerate_requested", False)
            if generate_requested or regenerate_requested:
                if image_mode and not str(image_context.get("confirmed_cover_text", "")).strip():
                    fallback_topic = (
                        topic.strip()
                        or title.strip()
                        or creator_profile.get("subjects", "").strip()
                    )
                    if fallback_topic:
                        image_context = dict(image_context)
                        image_context["confirmed_cover_text"] = fallback_topic
                        available, _ = image_analysis_capability()
                        if available:
                            image_context["analysis_basis"] = "未确认封面文字，仅结合已有图片信息、主题、正文和创作者资料继续。"
                            st.info("未读取到可确认的封面文字，将使用主题、正文和创作者资料继续内容重构。")
                        else:
                            image_context["analysis_basis"] = "图片分析能力未配置，仅使用主题、正文和创作者资料。"
                            st.info("封面分析暂不可用，本次将使用主题、正文和创作者资料继续内容重构。")
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
                    source_title = title.strip()
                    source_body = body.strip()
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
                            with st.spinner("正在根据OCR文字和图片基础信息分析..."):
                                image_analysis = resolve_demo_or_live(
                                    st.session_state.get("demo_mode", False),
                                    DEMO_NOTE_IMAGE_ANALYSIS,
                                    lambda: analyze_note_image_source(
                                        image_context,
                                        creator_profile=creator_profile,
                                        risk_items=source_findings,
                                    ),
                                )
                            st.session_state["note_image_analysis_key"] = image_analysis_key
                            st.session_state["note_image_analysis"] = image_analysis
                        if not image_analysis:
                            confirmed_text = str(
                                image_context.get("confirmed_cover_text")
                                or image_context.get("ocr_text")
                                or ""
                            ).strip()
                            image_analysis = {
                                "cover_theme": (
                                    confirmed_text.splitlines()[0]
                                    if confirmed_text
                                    else note_topic
                                ),
                                "visual_elements": [],
                                "target_audience": creator_profile.get("target_audience", ""),
                                "selling_direction": "",
                                "content_type": "",
                                "teacher_cues": "",
                                "analysis_basis": "OCR文字、标题、图片尺寸和已有业务资料",
                            }
                            st.info("已完成封面文字识别，AI正在根据爆款结构分析内容。")

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
                                analyzed_examples = resolve_demo_or_live(
                                    st.session_state.get("demo_mode", False),
                                    DEMO_VIRAL_EXAMPLE_ANALYSIS,
                                    lambda: analyze_viral_examples_for_generation(
                                        viral_examples,
                                        image_analysis=image_analysis,
                                    ),
                                )
                            st.session_state["note_viral_example_analysis_key"] = (
                                example_analysis_key
                            )
                            st.session_state["note_viral_example_analysis"] = (
                                analyzed_examples or {}
                            )
                            viral_example_analysis = analyzed_examples or {}
                        if not viral_example_analysis:
                            viral_example_analysis = {}

                    image_content_type = ""
                    if image_mode:
                        image_content_type = classify_image_content(image_context, image_analysis)
                        image_analysis = dict(image_analysis or {})
                        image_analysis["content_type"] = image_content_type
                    source_materials = {
                        "current_title": source_title,
                        "current_body": source_body,
                        "has_cover_image": bool(image_bytes),
                        "cover_image_hash": hashlib.sha256(image_bytes).hexdigest() if image_bytes else "",
                        "ocr_text": ocr_text.strip(),
                        "corrected_cover_text": corrected_cover_text,
                        "cover_analysis": backend_analysis,
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
                        generation_options["content_direction"] = image_content_type
                        generation_options["structure_guidance"] = get_image_content_structure(image_content_type)
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
                    blocking_error = ""
                    if not blocking_error:
                        with st.spinner("正在根据素材生成标题、正文、标签和互动设计..."):
                            raw_note = resolve_demo_or_live(
                                st.session_state.get("demo_mode", False),
                                build_demo_note(
                                    IMAGE_NOTE_TITLE_COUNT if image_mode else 5
                                ),
                                lambda: generate_xiaohongshu_note(
                                    note_topic,
                                    creator_profile=creator_profile,
                                    generation_options=generation_options,
                                    source_materials=source_materials,
                                    risk_items=source_findings,
                                ),
                            )
                            if (
                                image_mode
                                and raw_note
                                and len(str(raw_note.get("body", "")).strip()) < min_chars
                            ):
                                completion_materials = dict(source_materials)
                                completion_materials["short_generated_draft"] = raw_note
                                completion_options = dict(generation_options)
                                completion_options["structure_guidance"] = (
                                    f"{generation_options['structure_guidance']}；素材较短，请补充具体场景、方法步骤、案例边界和收藏清单，形成完整小红书图文。"
                                )
                                raw_note = resolve_demo_or_live(
                                    st.session_state.get("demo_mode", False),
                                    build_demo_note(IMAGE_NOTE_TITLE_COUNT),
                                    lambda: generate_xiaohongshu_note(
                                        note_topic,
                                        creator_profile=creator_profile,
                                        generation_options=completion_options,
                                        source_materials=completion_materials,
                                        risk_items=source_findings,
                                    ),
                                )
                            quality_issues = (
                                validate_publish_draft_quality(raw_note, image_content_type)
                                if raw_note
                                else []
                            )
                            if quality_issues:
                                quality_materials = dict(source_materials)
                                quality_materials["rejected_draft"] = raw_note
                                quality_options = dict(generation_options)
                                quality_options["quality_retry_requirements"] = (
                                    "上一稿存在以下问题："
                                    + "；".join(quality_issues)
                                    + "。重新生成时必须像真实老师分享经验，从家长困惑或具体学习场景开始，给出可执行方法；"
                                    "禁止营销号语气、夸张承诺、绝对结果和课程推销开头。"
                                )
                                raw_note = resolve_demo_or_live(
                                    st.session_state.get("demo_mode", False),
                                    build_demo_note(IMAGE_NOTE_TITLE_COUNT if image_mode else 5),
                                    lambda: generate_xiaohongshu_note(
                                        note_topic,
                                        creator_profile=creator_profile,
                                        generation_options=quality_options,
                                        source_materials=quality_materials,
                                        risk_items=source_findings,
                                    ),
                                )
                            quality_issues = (
                                validate_publish_draft_quality(raw_note, image_content_type)
                                if raw_note
                                else []
                            )
                            format_issues = (
                                validate_image_note_format(raw_note)
                                if image_mode and raw_note
                                else []
                            )
                            format_issues = [*quality_issues, *format_issues]
                            format_issues = [
                                issue
                                for issue in format_issues
                                if not issue.startswith("正文少于")
                            ]
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
                        note_result["image_content_type"] = image_content_type
                        if image_mode:
                            note_result["cover_copy"] = (
                                backend_analysis.get("recommended_copy")
                                or (note_result.get("titles") or [""])[0]
                            )
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
                render_generated_note(generated_note, title, body)
            elif generated_note:
                st.session_state.pop("note_generation_result", None)
                st.info("图片驱动生成已升级，请重新生成新版本。")
            elif note_generation_error:
                st.warning(f"内容重构暂未完成：{note_generation_error}")

if __name__ == "__main__":
    main()
