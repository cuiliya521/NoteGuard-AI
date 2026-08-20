from __future__ import annotations

import json
import hashlib
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


MAX_EXAMPLES = 20
MAX_TITLE_CHARS = 200
MAX_CONTENT_CHARS = 3000
MAX_METADATA_CHARS = 1000
MAX_METHOD_MODELS = 200
VERIFICATION_STATUSES = ("待验证", "已验证有效", "不推荐复用")
VIRAL_LEVELS = ("普通", "优秀", "爆款")
VISUAL_INFERENCE_NOTICE = "基于图片尺寸、OCR文字位置和图片描述推断，未接入视觉模型时需人工复核。"
LEGACY_VERIFICATION_STATUS_MAP = {
    "未验证": "待验证",
    "表现一般": "不推荐复用",
}

EXAMPLE_FIELDS = (
    "title",
    "content",
    "category",
    "structure",
    "opening_style",
    "pain_points",
    "selling_points",
    "conversion_style",
)


def normalize_viral_example(record: dict[str, Any]) -> dict[str, str] | None:
    normalized = {
        field: str(record.get(field, "")).strip()[:MAX_METADATA_CHARS]
        for field in EXAMPLE_FIELDS
    }
    normalized["title"] = normalized["title"][:MAX_TITLE_CHARS]
    normalized["content"] = normalized["content"][:MAX_CONTENT_CHARS]
    if not normalized["title"] and not normalized["content"]:
        return None
    return normalized


def load_viral_examples(path: Path, limit: int = MAX_EXAMPLES) -> list[dict[str, str]]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]\n", encoding="utf-8")

    try:
        raw_examples = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(raw_examples, list):
        return []
    if limit <= 0:
        return []

    examples: list[dict[str, str]] = []
    for record in raw_examples:
        if not isinstance(record, dict):
            continue
        normalized = normalize_viral_example(record)
        if normalized:
            examples.append(normalized)
        if len(examples) >= limit:
            break
    return examples


def load_viral_cases(path: Path) -> list[dict[str, Any]]:
    """Load user-saved research cases without changing legacy example projections."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]\n", encoding="utf-8")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(payload, list):
        return []
    cases: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        normalized = normalize_viral_case(item)
        if normalized:
            cases.append(normalized)
    return cases


def normalize_viral_case(record: dict[str, Any]) -> dict[str, Any] | None:
    """Return a display-safe projection while keeping legacy case data readable."""
    title = str(record.get("title") or "").strip()[:MAX_TITLE_CHARS]
    content = str(record.get("content") or "").strip()[:MAX_CONTENT_CHARS]
    analysis = record.get("analysis") if isinstance(record.get("analysis"), dict) else {}
    cover = record.get("cover") if isinstance(record.get("cover"), dict) else {}
    original_material = (
        record.get("original_material")
        if isinstance(record.get("original_material"), dict)
        else {}
    )
    model = record.get("model") if isinstance(record.get("model"), dict) else {}
    tag_dimensions = (
        record.get("tag_dimensions")
        if isinstance(record.get("tag_dimensions"), dict)
        else {}
    )
    source_info = record.get("source_info") if isinstance(record.get("source_info"), dict) else {}
    operation_review = (
        record.get("operation_review")
        if isinstance(record.get("operation_review"), dict)
        else {}
    )
    cover_visual_analysis = normalize_cover_visual_analysis(record.get("cover_visual_analysis"))
    actual_metrics = (
        operation_review.get("actual_metrics")
        if isinstance(operation_review.get("actual_metrics"), dict)
        else {}
    )
    verification_status = str(operation_review.get("verification_status") or "待验证").strip()
    verification_status = LEGACY_VERIFICATION_STATUS_MAP.get(verification_status, verification_status)
    if verification_status not in VERIFICATION_STATUSES:
        verification_status = "待验证"
    viral_level = str(operation_review.get("viral_level") or "普通").strip()
    if viral_level not in VIRAL_LEVELS:
        viral_level = "普通"

    raw_tags = record.get("tags", [])
    if isinstance(raw_tags, str):
        raw_tags = [raw_tags]
    elif not isinstance(raw_tags, list):
        raw_tags = []
    tags = list(
        dict.fromkeys(str(tag).strip()[:40] for tag in raw_tags if str(tag).strip())
    )[:12]

    # Completely empty/corrupt records are not useful assets. Image-only and
    # analysis-only legacy records remain readable.
    if not title and not content and not analysis and not cover and not original_material:
        return None

    record_id = str(record.get("id") or "").strip()
    if not record_id:
        identity_payload = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
        record_id = f"legacy-{hashlib.sha256(identity_payload.encode('utf-8')).hexdigest()[:16]}"

    return {
        **record,
        "id": record_id,
        "created_at": str(record.get("created_at") or ""),
        "original_material": original_material,
        "title": title,
        "content": content,
        "cover": cover,
        "cover_visual_analysis": cover_visual_analysis,
        "analysis": analysis,
        "tags": tags,
        "tag_dimensions": {
            key: str(tag_dimensions.get(key) or "").strip()[:80]
            for key in ("subject", "audience", "content_type", "scenario")
            if str(tag_dimensions.get(key) or "").strip()
        },
        "model": {
            str(key): str(value).strip()[:MAX_METADATA_CHARS]
            for key, value in model.items()
            if str(key).strip() and str(value).strip()
        },
        "source_info": {
            "platform": str(source_info.get("platform") or "").strip()[:80],
            "original_url": str(
                source_info.get("original_url")
                or original_material.get("source_url")
                or ""
            ).strip()[:2000],
            "publish_date": str(source_info.get("publish_date") or "").strip()[:40],
            "source_account": str(source_info.get("source_account") or "").strip()[:200],
        },
        "operation_review": {
            "save_reason": str(operation_review.get("save_reason") or "").strip()[:MAX_METADATA_CHARS],
            "verification_status": verification_status,
            "viral_level": viral_level,
            "actual_metrics": {
                key: _normalize_optional_metric(actual_metrics.get(key))
                for key in ("likes", "favorites", "comments")
            },
            "conversion": str(operation_review.get("conversion") or "").strip()[:MAX_METADATA_CHARS],
            "notes": str(operation_review.get("notes") or "").strip()[:MAX_CONTENT_CHARS],
        },
    }


def normalize_cover_visual_analysis(value: Any) -> dict[str, Any]:
    """Normalize optional V2 visual fields without inventing missing observations."""
    source = value if isinstance(value, dict) else {}

    def mapping(field: str, keys: tuple[str, ...]) -> dict[str, str]:
        raw = source.get(field) if isinstance(source.get(field), dict) else {}
        return {key: str(raw.get(key) or "").strip()[:MAX_METADATA_CHARS] for key in keys}

    def text_list(field: str) -> list[str]:
        raw = source.get(field) if isinstance(source.get(field), list) else []
        return [str(item).strip()[:MAX_METADATA_CHARS] for item in raw if str(item).strip()][:8]

    return {
        "font_hierarchy": mapping("font_hierarchy", ("primary", "secondary", "small_text")),
        "color_analysis": mapping(
            "color_analysis",
            ("primary_color", "background_color", "text_color", "contrast"),
        ),
        "subject_position": mapping(
            "subject_position",
            ("person_present", "position", "text_avoidance"),
        ),
        "visual_focus": text_list("visual_focus"),
        "information_layers": text_list("information_layers"),
        "basis_notice": str(source.get("basis_notice") or "").strip()[:MAX_METADATA_CHARS],
    }


def build_cover_visual_analysis(
    cover: dict[str, Any] | None,
    image_analysis: dict[str, Any] | None,
) -> dict[str, Any]:
    """Derive a conservative visual record from existing non-vision evidence."""
    cover_data = cover if isinstance(cover, dict) else {}
    image_data = image_analysis if isinstance(image_analysis, dict) else {}
    layout = image_data.get("layout_structure") if isinstance(image_data.get("layout_structure"), dict) else {}
    ocr_lines = [
        line.strip()
        for line in str(cover_data.get("ocr_text") or "").splitlines()
        if line.strip()
    ]
    description = str(cover_data.get("description") or "").strip()

    primary_text = ocr_lines[0] if ocr_lines else ""
    secondary_text = " / ".join(ocr_lines[1:3])
    small_text = " / ".join(ocr_lines[3:])
    text_hierarchy = str(layout.get("text_hierarchy") or image_data.get("information_hierarchy") or "").strip()
    if text_hierarchy and not primary_text:
        primary_text = text_hierarchy

    color_terms = (
        "红色", "橙色", "黄色", "绿色", "蓝色", "紫色", "粉色",
        "黑色", "白色", "灰色", "浅色", "深色", "渐变",
    )
    observed_colors = list(dict.fromkeys(term for term in color_terms if term in description))
    background_color = next(
        (term for term in observed_colors if f"{term}背景" in description or f"背景{term}" in description),
        "",
    )
    text_color = next(
        (term for term in observed_colors if f"{term}字" in description or f"文字{term}" in description),
        "",
    )
    contrast = ""
    if any(term in description for term in ("强对比", "高对比", "撞色", "明暗对比")):
        contrast = "存在明确强对比（来自图片描述）"
    elif background_color and text_color and background_color != text_color:
        contrast = "背景与文字使用不同颜色；对比强度需人工确认"

    person_present = "无法确认"
    position = "无法确认"
    text_avoidance = "无法确认"
    if any(term in description for term in ("人物", "老师", "教师", "学生", "家长", "人像")):
        person_present = "存在（来自图片描述）"
        position = next(
            (label for term, label in (("左侧", "左侧"), ("右侧", "右侧"), ("中间", "中间"), ("中央", "中间")) if term in description),
            "位置未说明",
        )
        if any(term in description for term in ("避让文字", "文字留白", "不遮挡文字")):
            text_avoidance = "主体避让文字区域（来自图片描述）"
    elif any(term in description for term in ("无人物", "没有人物", "纯文字", "文字海报")):
        person_present = "无人物（来自图片描述）"
        position = "无人物"
        text_avoidance = "不适用"

    first_focus = str(image_data.get("first_glance") or layout.get("visual_focus") or primary_text).strip()
    visual_focus = []
    for candidate in (
        first_focus,
        secondary_text,
        str(image_data.get("trust_building") or "").strip(),
    ):
        if candidate and candidate not in visual_focus:
            visual_focus.append(candidate)

    information_layers = []
    if ocr_lines:
        layer_names = ("第一层", "第二层", "第三层", "第四层")
        for index, line in enumerate(ocr_lines[:4]):
            information_layers.append(f"{layer_names[index]}：{line}")
    elif text_hierarchy:
        information_layers.append(f"第一层：{text_hierarchy}")

    return normalize_cover_visual_analysis(
        {
            "font_hierarchy": {
                "primary": primary_text,
                "secondary": secondary_text,
                "small_text": small_text,
            },
            "color_analysis": {
                "primary_color": "、".join(observed_colors),
                "background_color": background_color,
                "text_color": text_color,
                "contrast": contrast,
            },
            "subject_position": {
                "person_present": person_present,
                "position": position,
                "text_avoidance": text_avoidance,
            },
            "visual_focus": visual_focus,
            "information_layers": information_layers,
            "basis_notice": VISUAL_INFERENCE_NOTICE,
        }
    )


def _normalize_optional_metric(value: Any) -> int | str:
    if value in (None, ""):
        return ""
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return ""


def filter_viral_cases(
    cases: list[dict[str, Any]],
    *,
    query: str = "",
    subject: str = "",
    audience: str = "",
    content_type: str = "",
    scenario: str = "",
    verification_status: str = "",
) -> list[dict[str, Any]]:
    """Filter saved cases without requiring a database or changing stored data."""
    query_text = query.strip().casefold()
    filters = {
        "subject": subject.strip(),
        "audience": audience.strip(),
        "content_type": content_type.strip(),
        "scenario": scenario.strip(),
    }
    matched: list[dict[str, Any]] = []
    for case in cases:
        dimensions = case.get("tag_dimensions") if isinstance(case.get("tag_dimensions"), dict) else {}
        dimension_mismatch = False
        for key, value in filters.items():
            if not value:
                continue
            actual = str(dimensions.get(key, "")).strip()
            actual_values = [item.strip() for item in actual.replace("，", "、").split("、") if item.strip()]
            if actual != value and value not in actual_values:
                dimension_mismatch = True
                break
        if dimension_mismatch:
            continue
        operation_review = (
            case.get("operation_review")
            if isinstance(case.get("operation_review"), dict)
            else {}
        )
        if verification_status and operation_review.get("verification_status") != verification_status:
            continue
        if query_text:
            source_info = case.get("source_info") if isinstance(case.get("source_info"), dict) else {}
            searchable = " ".join(
                [
                    str(case.get("title", "")),
                    str(case.get("content", "")),
                    " ".join(str(tag) for tag in case.get("tags", []) if str(tag).strip()),
                    " ".join(str(value) for value in dimensions.values()),
                    " ".join(str(value) for value in source_info.values()),
                    str(operation_review.get("notes", "")),
                ]
            ).casefold()
            if query_text not in searchable:
                continue
        matched.append(case)
    return matched


def update_viral_case_tags(
    path: Path,
    case_id: str,
    tag_dimensions: dict[str, Any],
    tags: list[Any],
) -> dict[str, Any]:
    """Update case classification only; existing material and analysis remain untouched."""
    cases = load_viral_cases(path)
    target = next((case for case in cases if case.get("id") == case_id), None)
    if target is None:
        raise ValueError("未找到需要更新的案例。")
    target["tag_dimensions"] = {
        key: str(tag_dimensions.get(key) or "").strip()[:80]
        for key in ("subject", "audience", "content_type", "scenario")
        if str(tag_dimensions.get(key) or "").strip()
    }
    target["tags"] = list(
        dict.fromkeys(str(tag).strip()[:40] for tag in tags if str(tag).strip())
    )[:12]
    _write_viral_cases(path, cases)
    return target


def update_viral_case_operation(
    path: Path,
    case_id: str,
    source_info: dict[str, Any],
    operation_review: dict[str, Any],
) -> dict[str, Any]:
    """Update manually verified operating data without touching AI analysis."""
    cases = load_viral_cases(path)
    target = next((case for case in cases if case.get("id") == case_id), None)
    if target is None:
        raise ValueError("未找到需要更新的案例。")
    status = str(operation_review.get("verification_status") or "待验证").strip()
    status = LEGACY_VERIFICATION_STATUS_MAP.get(status, status)
    if status not in VERIFICATION_STATUSES:
        status = "待验证"
    viral_level = str(operation_review.get("viral_level") or "普通").strip()
    if viral_level not in VIRAL_LEVELS:
        viral_level = "普通"
    metrics = operation_review.get("actual_metrics")
    if not isinstance(metrics, dict):
        metrics = {}
    target["source_info"] = {
        "platform": str(source_info.get("platform") or "").strip()[:80],
        "original_url": str(source_info.get("original_url") or "").strip()[:2000],
        "publish_date": str(source_info.get("publish_date") or "").strip()[:40],
        "source_account": str(source_info.get("source_account") or "").strip()[:200],
    }
    target["operation_review"] = {
        "save_reason": str(operation_review.get("save_reason") or "").strip()[:MAX_METADATA_CHARS],
        "verification_status": status,
        "viral_level": viral_level,
        "actual_metrics": {
            key: _normalize_optional_metric(metrics.get(key))
            for key in ("likes", "favorites", "comments")
        },
        "conversion": str(operation_review.get("conversion") or "").strip()[:MAX_METADATA_CHARS],
        "notes": str(operation_review.get("notes") or "").strip()[:MAX_CONTENT_CHARS],
    }
    _write_viral_cases(path, cases)
    return target


def delete_viral_case(path: Path, case_id: str) -> bool:
    """Delete one explicitly selected case and keep every other record intact."""
    cases = load_viral_cases(path)
    remaining = [case for case in cases if case.get("id") != case_id]
    if len(remaining) == len(cases):
        return False
    _write_viral_cases(path, remaining)
    return True


def build_case_comparison(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a side-by-side review from saved fields only."""
    if not 2 <= len(cases) <= 5:
        raise ValueError("案例对比需要选择 2 到 5 个案例。")

    title_rows: list[dict[str, str]] = []
    pain_rows: list[dict[str, str]] = []
    cover_rows: list[dict[str, str]] = []
    body_rows: list[dict[str, str]] = []
    pain_counter: Counter[str] = Counter()

    def list_text(value: Any) -> str:
        if isinstance(value, list):
            return "；".join(str(item).strip() for item in value if str(item).strip())
        return str(value or "").strip()

    for index, case in enumerate(cases, start=1):
        label = str(case.get("title") or f"案例{index}")
        analysis = case.get("analysis") if isinstance(case.get("analysis"), dict) else {}
        text_analysis = analysis.get("text") if isinstance(analysis.get("text"), dict) else {}
        image_analysis = analysis.get("image") if isinstance(analysis.get("image"), dict) else {}
        title_analysis = (
            text_analysis.get("title_analysis")
            if isinstance(text_analysis.get("title_analysis"), dict)
            else {}
        )
        structure = (
            text_analysis.get("structure_analysis")
            if isinstance(text_analysis.get("structure_analysis"), dict)
            else {}
        )
        model = case.get("model") if isinstance(case.get("model"), dict) else {}
        pain = str(title_analysis.get("pain_point") or model.get("user_pain") or "").strip()
        if pain:
            pain_counter[pain] += 1

        title_rows.append(
            {
                "案例": label,
                "标题结构": str(model.get("title_structure") or "当前案例未提供").strip(),
            }
        )
        pain_rows.append({"案例": label, "用户痛点": pain or "当前案例未提供"})
        cover_rows.append(
            {
                "案例": label,
                "第一视觉": str(image_analysis.get("first_glance") or "当前案例未提供"),
                "核心文字位置": str(
                    image_analysis.get("information_hierarchy")
                    or image_analysis.get("layout_method")
                    or "当前案例未提供"
                ),
                "信任元素": str(image_analysis.get("trust_building") or "当前案例未提供"),
                "转化元素": list_text(image_analysis.get("conversion_elements")) or "当前案例未提供",
            }
        )
        body_rows.append(
            {
                "案例": label,
                "开头方式": str(structure.get("opening") or "当前案例未提供"),
                "中段展开方式": str(structure.get("middle") or "当前案例未提供"),
                "结尾方式": str(structure.get("ending") or "当前案例未提供"),
            }
        )

    return {
        "case_ids": [str(case.get("id") or "") for case in cases],
        "title_rows": title_rows,
        "pain_rows": pain_rows,
        "common_pains": [
            {"value": value, "count": count}
            for value, count in pain_counter.most_common()
            if count >= 2
        ],
        "cover_rows": cover_rows,
        "body_rows": body_rows,
    }


def _write_viral_cases(path: Path, cases: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(cases, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def build_combined_case_analysis(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate existing structured findings without inventing new case facts."""
    normalized_cases = [case for case in cases if isinstance(case, dict)]
    if len(normalized_cases) < 2:
        raise ValueError("请至少选择 2 个案例进行共同结构分析。")

    title_patterns: Counter[str] = Counter()
    pain_points: Counter[str] = Counter()
    content_patterns: Counter[str] = Counter()
    title_templates: Counter[str] = Counter()
    body_templates: Counter[str] = Counter()
    visual_patterns: Counter[str] = Counter()
    dimensions: dict[str, Counter[str]] = {
        "subject": Counter(),
        "audience": Counter(),
        "content_type": Counter(),
        "scenario": Counter(),
    }

    for case in normalized_cases:
        analysis = case.get("analysis") if isinstance(case.get("analysis"), dict) else {}
        text_analysis = analysis.get("text") if isinstance(analysis.get("text"), dict) else {}
        title_analysis = (
            text_analysis.get("title_analysis")
            if isinstance(text_analysis.get("title_analysis"), dict)
            else {}
        )
        structure = (
            text_analysis.get("structure_analysis")
            if isinstance(text_analysis.get("structure_analysis"), dict)
            else {}
        )
        model = case.get("model") if isinstance(case.get("model"), dict) else {}
        cover_visual = normalize_cover_visual_analysis(case.get("cover_visual_analysis"))
        tags = case.get("tag_dimensions") if isinstance(case.get("tag_dimensions"), dict) else {}

        title_parts: list[str] = []
        if title_analysis.get("target_audience") or tags.get("audience"):
            title_parts.append("目标用户")
        if title_analysis.get("pain_point") or model.get("user_pain"):
            title_parts.append("具体问题")
        if title_analysis.get("click_attraction"):
            title_parts.append("结果或方法价值")
        if title_parts:
            title_patterns[" + ".join(title_parts)] += 1

        pain = str(title_analysis.get("pain_point") or model.get("user_pain") or "").strip()
        if pain:
            pain_points[pain[:MAX_METADATA_CHARS]] += 1

        content_parts: list[str] = []
        if structure.get("opening"):
            content_parts.append("问题提出")
        if structure.get("middle"):
            content_parts.extend(("原因解释", "方法提供"))
        if model.get("trust_building"):
            content_parts.append("信任建立")
        if structure.get("ending"):
            content_parts.append("行动引导")
        if content_parts:
            content_patterns[" → ".join(content_parts)] += 1

        title_template = str(model.get("reusable_title_formula") or "").strip()
        if title_template:
            title_templates[title_template[:MAX_METADATA_CHARS]] += 1
        body_template = str(
            text_analysis.get("copyable_template") or model.get("content_structure") or ""
        ).strip()
        if body_template:
            body_templates[body_template[:MAX_METADATA_CHARS]] += 1

        visual_focus = cover_visual.get("visual_focus", [])
        if visual_focus:
            visual_patterns[f"第一视觉：{visual_focus[0]}"] += 1
        color_contrast = str(cover_visual.get("color_analysis", {}).get("contrast") or "").strip()
        if color_contrast:
            visual_patterns[f"色彩对比：{color_contrast}"] += 1
        subject_position = str(cover_visual.get("subject_position", {}).get("position") or "").strip()
        if subject_position and subject_position != "无法确认":
            visual_patterns[f"主体位置：{subject_position}"] += 1
        information_layers = cover_visual.get("information_layers", [])
        if information_layers:
            visual_patterns[f"信息层级：{len(information_layers)}层"] += 1

        for key in dimensions:
            value = str(tags.get(key) or "").strip()
            if value:
                dimensions[key][value[:80]] += 1

    def ranked(counter: Counter[str], limit: int = 5) -> list[dict[str, Any]]:
        return [{"value": value, "count": count} for value, count in counter.most_common(limit)]

    source_count = len(normalized_cases)
    applicability_parts = [
        dimensions[key].most_common(1)[0][0]
        for key in ("subject", "audience", "content_type", "scenario")
        if dimensions[key]
    ]
    primary_structure = title_patterns.most_common(1)[0][0] if title_patterns else "当前案例未形成统一标题结构"
    return {
        "source_case_ids": [str(case.get("id") or "") for case in normalized_cases],
        "source_case_titles": [str(case.get("title") or "未命名案例") for case in normalized_cases],
        "source_count": source_count,
        "title_patterns": ranked(title_patterns),
        "pain_points": ranked(pain_points),
        "content_patterns": ranked(content_patterns),
        "title_templates": ranked(title_templates, 3),
        "body_templates": ranked(body_templates, 3),
        "visual_patterns": [
            {"value": value, "count": count}
            for value, count in visual_patterns.most_common(5)
            if count >= 2
        ],
        "suggested_applicability": " · ".join(applicability_parts) or "教育内容运营",
        "suggested_core_structure": primary_structure,
    }


def load_method_models(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]\n", encoding="utf-8")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(payload, list):
        return []
    models: list[dict[str, Any]] = []
    for record in payload[:MAX_METHOD_MODELS]:
        if not isinstance(record, dict):
            continue
        analysis = record.get("analysis") if isinstance(record.get("analysis"), dict) else {}
        name = str(record.get("name") or "").strip()[:200]
        if not name and not analysis:
            continue
        try:
            source_count = max(0, int(record.get("source_count") or 0))
        except (TypeError, ValueError):
            source_count = 0
        models.append(
            {
                **record,
                "id": str(record.get("id") or uuid4().hex),
                "name": name or "未命名方法模型",
                "created_at": str(record.get("created_at") or ""),
                "source_case_ids": [
                    str(value) for value in record.get("source_case_ids", [])
                ] if isinstance(record.get("source_case_ids"), list) else [],
                "source_count": source_count,
                "applicability": str(record.get("applicability") or "").strip()[:MAX_METADATA_CHARS],
                "core_structure": str(record.get("core_structure") or "").strip()[:MAX_METADATA_CHARS],
                "analysis": analysis,
            }
        )
    return models


def save_method_model(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    name = str(record.get("name") or "").strip()[:200]
    analysis = record.get("analysis") if isinstance(record.get("analysis"), dict) else {}
    source_case_ids = record.get("source_case_ids") if isinstance(record.get("source_case_ids"), list) else []
    if not name:
        raise ValueError("请填写模型名称。")
    if len(source_case_ids) < 2 or not analysis:
        raise ValueError("方法模型至少需要 2 个来源案例和一份共同结构分析。")
    saved = {
        "id": str(record.get("id") or uuid4().hex),
        "name": name,
        "created_at": str(record.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "status": "已沉淀模型",
        "source_case_ids": [str(value) for value in source_case_ids],
        "source_count": len(source_case_ids),
        "applicability": str(record.get("applicability") or "").strip()[:MAX_METADATA_CHARS],
        "core_structure": str(record.get("core_structure") or "").strip()[:MAX_METADATA_CHARS],
        "analysis": analysis,
    }
    models = load_method_models(path)
    models.insert(0, saved)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(models[:MAX_METHOD_MODELS], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
    return saved


def save_viral_case(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    """Persist one structured research case in the personal asset library."""
    title = str(record.get("title", "")).strip()[:MAX_TITLE_CHARS]
    content = str(record.get("content", "")).strip()[:MAX_CONTENT_CHARS]
    analysis = record.get("analysis") if isinstance(record.get("analysis"), dict) else {}
    if not title and not content and not analysis:
        raise ValueError("案例至少需要标题、正文或拆解结果。")

    tags = record.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    normalized_tags = list(
        dict.fromkeys(str(tag).strip()[:40] for tag in tags if str(tag).strip())
    )[:12]
    cover = record.get("cover") if isinstance(record.get("cover"), dict) else {}
    cover_visual_analysis = normalize_cover_visual_analysis(record.get("cover_visual_analysis"))
    original_material = (
        record.get("original_material")
        if isinstance(record.get("original_material"), dict)
        else {}
    )
    model = record.get("model") if isinstance(record.get("model"), dict) else {}
    tag_dimensions = (
        record.get("tag_dimensions")
        if isinstance(record.get("tag_dimensions"), dict)
        else {}
    )
    source_info = record.get("source_info") if isinstance(record.get("source_info"), dict) else {}
    operation_review = (
        record.get("operation_review")
        if isinstance(record.get("operation_review"), dict)
        else {}
    )
    status = str(operation_review.get("verification_status") or "待验证").strip()
    status = LEGACY_VERIFICATION_STATUS_MAP.get(status, status)
    if status not in VERIFICATION_STATUSES:
        status = "待验证"
    viral_level = str(operation_review.get("viral_level") or "普通").strip()
    if viral_level not in VIRAL_LEVELS:
        viral_level = "普通"
    metrics = operation_review.get("actual_metrics")
    if not isinstance(metrics, dict):
        metrics = {}
    saved = {
        "id": str(record.get("id") or uuid4().hex),
        "created_at": str(record.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "original_material": original_material,
        "title": title,
        "content": content,
        "cover": cover,
        "cover_visual_analysis": cover_visual_analysis,
        "analysis": analysis,
        "tags": normalized_tags,
        "tag_dimensions": {
            key: str(tag_dimensions.get(key, "")).strip()[:80]
            for key in ("subject", "audience", "content_type", "scenario")
            if str(tag_dimensions.get(key, "")).strip()
        },
        "model": {
            str(key): str(value).strip()[:MAX_METADATA_CHARS]
            for key, value in model.items()
            if str(key).strip() and str(value).strip()
        },
        "source_info": {
            "platform": str(source_info.get("platform") or "").strip()[:80],
            "original_url": str(
                source_info.get("original_url")
                or original_material.get("source_url")
                or ""
            ).strip()[:2000],
            "publish_date": str(source_info.get("publish_date") or "").strip()[:40],
            "source_account": str(source_info.get("source_account") or "").strip()[:200],
        },
        "operation_review": {
            "save_reason": str(operation_review.get("save_reason") or "").strip()[:MAX_METADATA_CHARS],
            "verification_status": status,
            "viral_level": viral_level,
            "actual_metrics": {
                key: _normalize_optional_metric(metrics.get(key))
                for key in ("likes", "favorites", "comments")
            },
            "conversion": str(operation_review.get("conversion") or "").strip()[:MAX_METADATA_CHARS],
            "notes": str(operation_review.get("notes") or "").strip()[:MAX_CONTENT_CHARS],
        },
    }

    cases = load_viral_cases(path)
    cases.insert(0, saved)
    _write_viral_cases(path, cases)
    return saved
