from __future__ import annotations

from importlib import import_module
from typing import Any, Callable


def load_paste_image_button() -> tuple[Callable[..., Any] | None, str]:
    try:
        module = import_module("streamlit_paste_button")
        return module.paste_image_button, ""
    except Exception:
        return None, "粘贴图片组件暂不可用，请继续使用文件上传。"


def extract_pasted_image(result: Any) -> tuple[Any | None, str]:
    if result is None:
        return None, "剪贴板中没有可用图片，请先复制图片后重试。"

    image_data = getattr(result, "image_data", None)
    if image_data is None:
        return None, "剪贴板中没有可用图片，请先复制图片后重试。"
    if isinstance(image_data, str):
        return None, "剪贴板内容不是图片，请复制图片后重试。"
    return image_data, ""
