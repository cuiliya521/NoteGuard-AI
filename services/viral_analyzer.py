from __future__ import annotations

from typing import Any, MutableMapping

from services.image_input import ImagePayload


VIRAL_IMAGE_RESULT_KEYS = (
    "viral_image_ocr_lines",
    "viral_image_ocr_error",
    "viral_image_analysis",
    "viral_image_analysis_error",
    "viral_image_analysis_key",
)

IMAGE_INFERENCE_NOTICE = (
    "当前图片分析主要基于OCR文字、图片尺寸和用户补充信息，部分视觉结论属于推断。"
)


def can_analyze_viral_input(title: str, body: str) -> bool:
    return bool((title or "").strip() or (body or "").strip())


def store_viral_image_payload(
    state: MutableMapping[str, Any],
    payload: ImagePayload,
) -> bool:
    is_new_image = state.get("viral_image_hash") != payload.image_hash
    state["viral_image_source"] = payload.source
    state["viral_image_bytes"] = payload.image_bytes
    state["viral_image_hash"] = payload.image_hash
    state["viral_image_preview"] = payload.image_bytes
    state["viral_image_format"] = payload.image_format
    state["viral_image_width"] = payload.width
    state["viral_image_height"] = payload.height

    if not is_new_image:
        return False

    for key in VIRAL_IMAGE_RESULT_KEYS:
        state.pop(key, None)
    state["viral_image_text"] = ""
    state["viral_image_description"] = ""
    return True


def build_viral_image_context(
    state: MutableMapping[str, Any],
    risk_items: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    width = int(state.get("viral_image_width", 0) or 0)
    height = int(state.get("viral_image_height", 0) or 0)
    ratio = round(width / height, 3) if width and height else 0
    return {
        "analysis_capability": "ocr_dimensions_and_user_description_only",
        "ocr_text": str(state.get("viral_image_text", "")).strip(),
        "user_description": str(state.get("viral_image_description", "")).strip(),
        "image_width": width,
        "image_height": height,
        "aspect_ratio": ratio,
        "image_format": str(state.get("viral_image_format", "")),
        "risk_items": risk_items or [],
        "inference_notice": IMAGE_INFERENCE_NOTICE,
    }
