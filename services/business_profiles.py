from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any
from uuid import uuid4


MAX_BUSINESS_PROFILES = 20
PROFILE_FIELDS = (
    "product_name",
    "brand_name",
    "target_user",
    "common_pain_points",
    "usage_scenario",
    "conversion_method",
)


def _text(value: object, limit: int = 2000) -> str:
    return str(value or "").strip()[:limit]


def _normalize_profile(record: dict[str, Any]) -> dict[str, str]:
    return {
        **{field: _text(record.get(field)) for field in PROFILE_FIELDS},
        "id": _text(record.get("id") or uuid4().hex, 100),
        "created_at": _text(record.get("created_at"), 100),
        "updated_at": _text(record.get("updated_at"), 100),
    }


def load_business_profiles(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]\n", encoding="utf-8")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(payload, list):
        return []
    profiles: list[dict[str, str]] = []
    for record in payload[:MAX_BUSINESS_PROFILES]:
        if not isinstance(record, dict):
            continue
        profile = _normalize_profile(record)
        if profile["product_name"] or profile["brand_name"]:
            profiles.append(profile)
    return profiles


def save_business_profile(path: Path, record: dict[str, Any]) -> dict[str, str]:
    if not isinstance(record, dict):
        raise ValueError("业务档案格式无效。")
    profile = _normalize_profile(record)
    if not profile["product_name"] or not profile["target_user"]:
        raise ValueError("请填写产品/服务名称和目标用户。")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    profile["created_at"] = profile["created_at"] or now
    profile["updated_at"] = now
    profiles = load_business_profiles(path)
    profiles = [item for item in profiles if item.get("id") != profile["id"]]
    profiles.insert(0, profile)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(profiles[:MAX_BUSINESS_PROFILES], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
    return profile


def build_material_profile_suggestion(
    *,
    title: str,
    ocr_text: str,
    source_analysis: dict[str, Any] | None,
    image_analysis: dict[str, Any] | None,
    fallback_profile: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Map existing image-analysis outputs into editable business fields."""
    source = source_analysis if isinstance(source_analysis, dict) else {}
    image = image_analysis if isinstance(image_analysis, dict) else {}
    fallback = fallback_profile if isinstance(fallback_profile, dict) else {}
    copy_structure = image.get("copy_structure")
    if not isinstance(copy_structure, dict):
        copy_structure = {}
    conversion_elements = image.get("conversion_elements")
    if not isinstance(conversion_elements, list):
        conversion_elements = []

    first_title = next((line.strip() for line in str(title or "").splitlines() if line.strip()), "")
    first_ocr_line = next((line.strip() for line in str(ocr_text or "").splitlines() if line.strip()), "")
    product_name = (
        _text(copy_structure.get("service_information"), 300)
        or _text(source.get("cover_theme"), 300)
        or first_title
        or first_ocr_line
        or _text(fallback.get("product_name"), 300)
    )
    brand_name = (
        _text(source.get("teacher_cues"), 300)
        or _text(copy_structure.get("credibility"), 300)
        or _text(fallback.get("brand_name"), 300)
    )
    target_user = (
        _text(source.get("target_audience"), 300)
        or _text(copy_structure.get("target_audience"), 300)
        or _text(fallback.get("target_user"), 300)
    )
    pain_point = (
        _text(image.get("user_pain_expression"))
        or _text(copy_structure.get("pain_point"))
        or _text(fallback.get("common_pain_points"))
    )
    selling_point = (
        _text(source.get("selling_direction"))
        or _text(image.get("first_glance"))
        or _text(fallback.get("core_selling_point"))
    )
    conversion_method = (
        "、".join(_text(item, 300) for item in conversion_elements if _text(item, 300))
        or _text(copy_structure.get("service_information"), 500)
        or _text(fallback.get("conversion_method"), 500)
    )
    usage_scenario = (
        _text(source.get("content_type"), 300)
        or _text(image.get("information_hierarchy"), 300)
        or _text(fallback.get("usage_scenario"), 300)
    )
    return {
        "product_name": product_name,
        "brand_name": brand_name,
        "target_user": target_user,
        "usage_scenario": usage_scenario,
        "common_pain_points": pain_point,
        "core_selling_point": selling_point,
        "conversion_method": conversion_method,
    }
