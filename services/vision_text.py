from __future__ import annotations

import base64
from io import BytesIO
import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)


def is_vision_text_available() -> bool:
    return bool(
        (os.getenv("VISION_API_KEY") or os.getenv("OPENAI_API_KEY"))
        and os.getenv("VISION_MODEL", "gpt-4.1-mini").strip()
    )


def _prepare_image_data_url(image: Any) -> str:
    from PIL import Image

    if isinstance(image, bytes):
        raw = image
    elif hasattr(image, "getvalue"):
        raw = image.getvalue()
    elif hasattr(image, "read"):
        raw = image.read()
    else:
        with open(image, "rb") as file:
            raw = file.read()
    with Image.open(BytesIO(raw)) as opened:
        prepared = opened.convert("RGB")
        prepared.thumbnail((1800, 1800))
        output = BytesIO()
        prepared.save(output, format="JPEG", quality=88, optimize=True)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _parse_json_payload(content: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I)
    payload = json.loads(cleaned)
    return payload if isinstance(payload, dict) else {}


def read_cover_text_with_vision(image: Any) -> dict[str, Any]:
    """Read visible text and grounded education-content signals from an image."""
    if not is_vision_text_available():
        return {}

    from openai import OpenAI

    api_key = os.getenv("VISION_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("VISION_BASE_URL", "").strip() or None
    model = os.getenv("VISION_MODEL", "gpt-4.1-mini").strip()
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "你是教育内容图片理解助手。文字字段只抄录图片中实际可见内容，不补写；"
                    "同时根据真实可见画面判断素材类型和教育内容价值，不推测人物身份、成绩变化或课程效果。"
                    "content_type 只能是教学经验、学生成果案例、课程服务、学习方法分享之一。"
                    "返回JSON字段 cover_title、small_text、labels、badges（字符串数组），以及"
                    "content_type、visual_scene、education_value、evidence（字符串）。"
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "读取可见文字，并判断这张教育图片适合承载哪类小红书内容。"},
                    {
                        "type": "image_url",
                        "image_url": {"url": _prepare_image_data_url(image), "detail": "high"},
                    },
                ],
            },
        ],
    )
    content = response.choices[0].message.content or "{}"
    return _parse_json_payload(content)
