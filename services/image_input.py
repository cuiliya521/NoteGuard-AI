from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import BytesIO
from typing import Any, MutableMapping

from PIL import Image, UnidentifiedImageError


SUPPORTED_IMAGE_FORMATS = {"PNG", "JPEG", "WEBP"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000

IMAGE_RESULT_STATE_KEYS = (
    "cover_analysis_requested",
    "cover_analysis_key",
    "cover_analysis",
    "cover_analysis_error",
    "cover_ocr_lines",
    "cover_ocr_raw_lines",
    "cover_ocr_optimized_lines",
    "cover_ocr_confidence",
    "cover_ocr_corrections",
    "cover_ocr_requires_confirmation",
    "cover_ocr_attempt_key",
    "cover_ocr_error",
    "cover_ocr_status",
    "cover_auto_analysis_key",
    "cover_analysis_image_key",
    "cover_analysis_text_key",
    "cover_analysis_source",
)


class ImageInputError(ValueError):
    pass


@dataclass(frozen=True)
class ImagePayload:
    source: str
    image_bytes: bytes
    image_hash: str
    image_format: str
    width: int
    height: int


def _read_image_bytes(image: Any, source: str) -> bytes:
    if image is None:
        if source == "clipboard":
            raise ImageInputError("剪贴板中没有可用图片，请先复制图片后重试。")
        raise ImageInputError("请选择需要处理的图片。")

    if isinstance(image, str):
        raise ImageInputError("剪贴板内容不是图片，请复制图片后重试。")
    if isinstance(image, (bytes, bytearray)):
        return bytes(image)
    if isinstance(image, Image.Image):
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()
    if hasattr(image, "getvalue"):
        value = image.getvalue()
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)

    raise ImageInputError("未能读取图片数据，请改用 PNG、JPEG 或 WEBP 图片。")


def normalize_image_input(image: Any, source: str) -> ImagePayload:
    if source not in {"upload", "clipboard"}:
        raise ImageInputError("未知的图片来源。")

    image_bytes = _read_image_bytes(image, source)
    if not image_bytes:
        raise ImageInputError("图片内容为空，请重新选择或粘贴图片。")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ImageInputError("图片超过 20MB，请压缩后再试，以免影响识别速度。")

    try:
        with Image.open(BytesIO(image_bytes)) as opened_image:
            image_format = (opened_image.format or "").upper()
            width, height = opened_image.size
            opened_image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ImageInputError("图片数据已损坏或格式无法识别，请重新复制或上传。") from None

    if image_format not in SUPPORTED_IMAGE_FORMATS:
        raise ImageInputError("暂仅支持 PNG、JPEG 和 WEBP 图片。")
    if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
        raise ImageInputError("图片尺寸过大，请适当缩小后再试。")

    return ImagePayload(
        source=source,
        image_bytes=image_bytes,
        image_hash=hashlib.sha256(image_bytes).hexdigest(),
        image_format=image_format,
        width=width,
        height=height,
    )


def store_image_payload(
    state: MutableMapping[str, Any],
    payload: ImagePayload,
) -> bool:
    is_new_image = state.get("current_image_hash") != payload.image_hash
    state["current_image_source"] = payload.source
    state["current_image_bytes"] = payload.image_bytes
    state["current_image_hash"] = payload.image_hash
    state["current_image_preview"] = payload.image_bytes
    state["uploaded_image_data"] = payload.image_bytes

    if not is_new_image:
        return False

    for key in IMAGE_RESULT_STATE_KEYS:
        state.pop(key, None)
    state["image_text_input"] = ""
    state["draft_image_text"] = ""
    return True
