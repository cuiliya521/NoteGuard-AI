from __future__ import annotations

from importlib import import_module
import logging
from typing import Any, Callable


LOGGER = logging.getLogger(__name__)
PASTE_UNAVAILABLE_MESSAGE = "图片粘贴功能暂不可用，请使用文件上传。"


def log_paste_component_error(error: Exception, context: str) -> None:
    LOGGER.error(
        "Image paste component failed during %s: %s",
        context,
        error,
        exc_info=(type(error), error, error.__traceback__),
    )


def load_paste_image_button() -> tuple[Callable[..., Any] | None, str]:
    try:
        module = import_module("streamlit_paste_button")
        return module.paste_image_button, ""
    except Exception as error:
        log_paste_component_error(error, "import")
        return None, PASTE_UNAVAILABLE_MESSAGE


def extract_pasted_image(result: Any) -> tuple[Any | None, str]:
    if result is None:
        return None, "剪贴板中没有可用图片，请先复制图片后重试。"

    image_data = getattr(result, "image_data", None)
    if image_data is None:
        return None, "剪贴板中没有可用图片，请先复制图片后重试。"
    if isinstance(image_data, str):
        return None, "剪贴板内容不是图片，请复制图片后重试。"
    return image_data, ""
