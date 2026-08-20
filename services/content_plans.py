from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any
from uuid import uuid4


MAX_CONTENT_PLANS = 200
MAX_TEXT_CHARS = 2000


def _clean_text(value: object, limit: int = MAX_TEXT_CHARS) -> str:
    return str(value or "").strip()[:limit]


def _pattern_values(analysis: dict[str, Any], field: str, limit: int = 3) -> list[str]:
    records = analysis.get(field, [])
    if not isinstance(records, list):
        return []
    values: list[str] = []
    for record in records:
        value = record.get("value") if isinstance(record, dict) else record
        text = _clean_text(value, 500)
        if text and text not in values:
            values.append(text)
        if len(values) >= limit:
            break
    return values


def build_content_plan(method: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    """Build a planning card from saved method fields without generating publish-ready copy."""
    method_name = _clean_text(method.get("name"), 200)
    if not method_name:
        raise ValueError("请选择一个方法模型。")

    normalized_inputs = {
        "business_profile_id": _clean_text(inputs.get("business_profile_id"), 100),
        "product_name": _clean_text(inputs.get("product_name"), 300),
        "brand_name": _clean_text(inputs.get("brand_name"), 300),
        "target_user": _clean_text(inputs.get("target_user"), 300),
        "common_pain_points": _clean_text(inputs.get("common_pain_points")),
        "usage_scenario": _clean_text(inputs.get("usage_scenario"), 300),
        "conversion_method": _clean_text(inputs.get("conversion_method"), 500),
        "promotion_theme": _clean_text(inputs.get("promotion_theme"), 500),
        "core_selling_point": _clean_text(inputs.get("core_selling_point")),
        "problem_to_solve": _clean_text(inputs.get("problem_to_solve")),
    }
    required_fields = ("product_name", "target_user", "problem_to_solve")
    if any(not normalized_inputs[field] for field in required_fields):
        raise ValueError("请填写产品/服务名称、目标用户和想解决的问题。")

    analysis = method.get("analysis") if isinstance(method.get("analysis"), dict) else {}
    structures = _pattern_values(analysis, "content_patterns", 1)
    title_directions = _pattern_values(analysis, "title_templates", 3)
    visual_patterns = _pattern_values(analysis, "visual_patterns", 3)

    core_structure = _clean_text(method.get("core_structure"), 500)
    recommended_structure = structures[0] if structures else core_structure
    if not recommended_structure:
        recommended_structure = "用户问题 → 真实依据 → 方法展示 → 行动入口"

    if not title_directions:
        title_directions = [
            "目标用户 + 具体问题 + 方法价值",
            "使用场景 + 常见困扰 + 解决方向",
            "真实观察 + 问题原因 + 可执行方法",
        ]

    product_name = normalized_inputs["product_name"]
    target_user = normalized_inputs["target_user"]
    problem = normalized_inputs["problem_to_solve"]
    scenario = normalized_inputs["usage_scenario"] or _clean_text(method.get("applicability"), 300)
    selling_point = normalized_inputs["core_selling_point"]
    promotion_theme = normalized_inputs["promotion_theme"]
    conversion_method = normalized_inputs["conversion_method"]
    content_direction = promotion_theme or f"面向{target_user}的{problem}解决型内容"

    visual_focus = "；".join(visual_patterns) or "突出问题、真实依据和使用场景"
    image_type = "知识点展示 / 人物信任"
    combined_context = f"{product_name} {scenario} {selling_point} {problem}"
    if any(term in combined_context for term in ("评价", "反馈", "案例", "成果")):
        image_type = "评价截图 / 结果展示"
    elif any(term in combined_context for term in ("课程", "服务", "试听", "招生")):
        image_type = "人物信任 / 服务场景"

    body_framework = [
        f"用户问题：{target_user}在{scenario or '当前场景'}中遇到的“{problem}”",
        f"解决过程：围绕{selling_point or product_name}说明具体方法和过程",
        "结果证明：只使用可核实的案例、过程记录或真实反馈",
        f"行动引导：{conversion_method or '邀请用户结合自身情况留言或进一步了解'}",
    ]

    return {
        "method": {
            "id": _clean_text(method.get("id"), 100),
            "name": method_name,
            "source_count": max(0, int(method.get("source_count") or 0)),
        },
        "inputs": normalized_inputs,
        "content_direction": content_direction,
        "recommended_structure": recommended_structure,
        "title_directions": title_directions[:3],
        "cover_suggestion": {
            "image_type": image_type,
            "visual_focus": visual_focus,
        },
        "body_framework": body_framework,
    }


def build_plan_reference_cases(
    method: dict[str, Any],
    cases: list[dict[str, Any]],
    limit: int = 3,
) -> list[dict[str, str]]:
    """Resolve a method's existing source links into concise planning references."""
    source_ids = method.get("source_case_ids", [])
    if not isinstance(source_ids, list):
        return []
    case_map = {
        str(case.get("id")): case
        for case in cases
        if isinstance(case, dict) and str(case.get("id") or "").strip()
    }
    references: list[dict[str, str]] = []
    for case_id in source_ids:
        case = case_map.get(str(case_id))
        if not case:
            continue
        model = case.get("model") if isinstance(case.get("model"), dict) else {}
        analysis = case.get("analysis") if isinstance(case.get("analysis"), dict) else {}
        text_analysis = analysis.get("text") if isinstance(analysis.get("text"), dict) else {}
        operation = (
            case.get("operation_review")
            if isinstance(case.get("operation_review"), dict)
            else {}
        )
        reuse_point = (
            _clean_text(model.get("core_structure"), 500)
            or _clean_text(model.get("reusable_title_formula"), 500)
            or _clean_text(text_analysis.get("copyable_template"), 500)
            or _clean_text(operation.get("save_reason"), 500)
            or "复用该案例已沉淀的内容结构"
        )
        references.append(
            {
                "id": str(case_id),
                "title": _clean_text(case.get("title"), 300) or "未命名案例",
                "reuse_point": reuse_point,
            }
        )
        if len(references) >= max(1, limit):
            break
    return references


def load_content_plans(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]\n", encoding="utf-8")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(payload, list):
        return []

    plans: list[dict[str, Any]] = []
    for record in payload[:MAX_CONTENT_PLANS]:
        if not isinstance(record, dict):
            continue
        method = record.get("method") if isinstance(record.get("method"), dict) else {}
        inputs = record.get("inputs") if isinstance(record.get("inputs"), dict) else {}
        if not method and not record.get("content_direction"):
            continue
        plans.append(
            {
                **record,
                "id": _clean_text(record.get("id") or uuid4().hex, 100),
                "created_at": _clean_text(record.get("created_at"), 100),
                "method": method,
                "inputs": inputs,
                "title_directions": record.get("title_directions", [])
                if isinstance(record.get("title_directions"), list)
                else [],
                "cover_suggestion": record.get("cover_suggestion", {})
                if isinstance(record.get("cover_suggestion"), dict)
                else {},
                "body_framework": record.get("body_framework", [])
                if isinstance(record.get("body_framework"), list)
                else [],
                "reference_cases": record.get("reference_cases", [])
                if isinstance(record.get("reference_cases"), list)
                else [],
            }
        )
    return plans


def save_content_plan(path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict) or not plan.get("content_direction"):
        raise ValueError("请先生成内容策划方案。")
    saved = {
        **plan,
        "id": _clean_text(plan.get("id") or uuid4().hex, 100),
        "created_at": _clean_text(
            plan.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            100,
        ),
    }
    plans = load_content_plans(path)
    plans.insert(0, saved)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(plans[:MAX_CONTENT_PLANS], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
    return saved
