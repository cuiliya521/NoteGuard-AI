from __future__ import annotations

from functools import lru_cache
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from io import BytesIO
import logging
import re
from statistics import mean
from typing import Any


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class OcrExtractionResult:
    lines: list[str]
    error: str
    average_confidence: float | None
    engine: str
    cover_text: str = ""
    vision_lines: tuple[str, ...] = ()
    vision_context: dict[str, Any] = field(default_factory=dict)


def is_paddle_ocr_available() -> bool:
    try:
        import paddle  # noqa: F401
        from paddleocr import PaddleOCR  # noqa: F401

        return True
    except Exception:
        return False


def is_tesseract_ocr_available() -> bool:
    try:
        import pytesseract
        from PIL import Image  # noqa: F401

        pytesseract.get_tesseract_version()
        return "chi_sim" in pytesseract.get_languages(config="")
    except Exception:
        return False


def is_ocr_available() -> bool:
    return is_paddle_ocr_available() or is_tesseract_ocr_available()


def get_available_ocr_engine() -> str:
    if is_paddle_ocr_available():
        return "paddleocr"
    if is_tesseract_ocr_available():
        return "tesseract-chi_sim"
    return "unavailable"


def get_ocr_dependency_message() -> str:
    missing: list[str] = []
    if not is_paddle_ocr_available():
        missing.append("PaddleOCR 中文模型未安装或不可用")
    if not is_tesseract_ocr_available():
        missing.append("Tesseract chi_sim 中文语言包未安装或不可用")
    if not missing:
        return ""
    return "；".join(missing) + "。可继续手动输入封面文字。"


def assess_text_quality(lines: list[str], average_confidence: float | None = None) -> str:
    text = "".join(lines).strip()
    if len(text) < 2:
        return "未识别到足够的文字。"

    chinese_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    symbol_count = len(re.findall(r"[^\u4e00-\u9fffA-Za-z0-9\s，。！？：】【、】【（）()、,.!?-]", text))

    if chinese_count < 2 and latin_count >= 4:
        return "识别结果几乎没有中文，可能是乱码或中文识别模型未配置。"
    if re.search(r"([^\s])\1{3,}", text) or re.search(r"(.{2,4})\1{2,}", text):
        return "识别结果存在大量重复字符，可能是乱码。"
    if symbol_count > max(4, len(text) // 3):
        return "识别结果包含过多无意义符号，可能是乱码。"
    if average_confidence is not None and average_confidence < 25:
        return "OCR 置信度过低，识别结果不可靠。"
    return ""


def _open_image(image: Any) -> Any:
    from PIL import Image

    image_type = type(image).__name__
    byte_size: int | None = None
    if isinstance(image, bytes):
        byte_size = len(image)
        img = Image.open(BytesIO(image))
    elif hasattr(image, "getvalue"):
        image_value = image.getvalue()
        byte_size = len(image_value) if isinstance(image_value, (bytes, bytearray)) else None
        img = Image.open(BytesIO(image_value))
    elif hasattr(image, "read"):
        img = Image.open(image)
    else:
        img = Image.open(image)
    LOGGER.warning(
        "OCR input decoded: type=%s bytes=%s format=%s size=%sx%s mode=%s",
        image_type,
        byte_size if byte_size is not None else "unknown",
        getattr(img, "format", None) or "unknown",
        img.width,
        img.height,
        img.mode,
    )
    rgb_image = img.convert("RGB")
    LOGGER.warning(
        "OCR input converted: size=%sx%s mode=%s",
        rgb_image.width,
        rgb_image.height,
        rgb_image.mode,
    )
    return rgb_image


def _build_preprocessed_variants(img: Any) -> list[tuple[str, Any]]:
    """Create bounded OCR variants for covers with mixed font sizes and backgrounds."""
    try:
        from PIL import ImageEnhance, ImageFilter, ImageOps

        width, height = img.size
        max_side = max(width, height)
        if max_side > 2400:
            ratio = 2400 / max_side
            compressed = img.resize(
                (max(1, int(width * ratio)), max(1, int(height * ratio)))
            )
        else:
            compressed = img.copy()
        scale = min(3.0, max(1.5, 1800 / max(1, min(compressed.size))))
        enlarged = compressed.resize(
            (
                max(1, int(compressed.width * scale)),
                max(1, int(compressed.height * scale)),
            )
        )
        grayscale = ImageOps.grayscale(enlarged)
        contrasted = ImageEnhance.Contrast(grayscale).enhance(2.0)
        sharpened = contrasted.filter(ImageFilter.SHARPEN)
        thresholded = contrasted.point(lambda pixel: 255 if pixel > 155 else 0)
        return [
            ("compressed", compressed),
            ("enlarged", enlarged),
            ("grayscale", grayscale),
            ("contrast", sharpened),
            ("threshold", thresholded),
        ]
    except Exception:
        return [("original", img)]


def _candidate_score(lines: list[str], confidence: float | None) -> float:
    text = "".join(lines)
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    useful = len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text))
    return chinese * 4 + useful + (confidence or 0) * 0.35


def merge_cover_text(ocr_lines: list[str], vision_lines: list[str]) -> str:
    """Merge both sources with visual-model text first when both are available."""
    merged: list[str] = []
    normalized_seen: set[str] = set()
    normalized_visual = [
        re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", str(line)).lower()
        for line in vision_lines
        if str(line).strip()
    ]
    for source, line in [
        *(("vision", line) for line in vision_lines),
        *(("ocr", line) for line in ocr_lines),
    ]:
        cleaned = re.sub(r"\s+", " ", str(line)).strip()
        normalized = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", cleaned).lower()
        if source == "ocr" and normalized_visual and any(
            SequenceMatcher(None, normalized, visual).ratio() >= 0.35
            for visual in normalized_visual
        ):
            continue
        if cleaned and normalized and normalized not in normalized_seen:
            merged.append(cleaned)
            normalized_seen.add(normalized)
    return "\n".join(merged)


@lru_cache(maxsize=1)
def _get_paddle_reader() -> Any:
    from paddleocr import PaddleOCR

    return PaddleOCR(
        lang="ch",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )


def _paddle_result_data(result: Any) -> dict[str, Any]:
    payload = getattr(result, "json", result)
    if callable(payload):
        payload = payload()
    if isinstance(payload, dict):
        nested = payload.get("res", payload)
        return nested if isinstance(nested, dict) else {}
    return {}


def _extract_with_paddle(img: Any) -> tuple[list[str], float | None]:
    import numpy as np

    image_array = np.asarray(img)
    LOGGER.warning(
        "PaddleOCR input: shape=%s dtype=%s mode=%s size=%s",
        image_array.shape,
        image_array.dtype,
        getattr(img, "mode", "unknown"),
        getattr(img, "size", "unknown"),
    )
    output = _get_paddle_reader().predict(input=image_array)
    lines: list[str] = []
    confidences: list[float] = []
    for result in output:
        data = _paddle_result_data(result)
        texts = data.get("rec_texts", [])
        scores = data.get("rec_scores", [])
        for index, text in enumerate(texts):
            normalized = str(text).strip()
            if normalized:
                lines.append(normalized)
                if index < len(scores):
                    confidences.append(float(scores[index]) * 100)
    return lines, mean(confidences) if confidences else None


def _extract_with_tesseract(img: Any) -> tuple[list[str], float | None]:
    import pytesseract
    from pytesseract import Output

    text = pytesseract.image_to_string(img, lang="chi_sim+eng")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    data = pytesseract.image_to_data(
        img,
        lang="chi_sim+eng",
        output_type=Output.DICT,
    )
    confidences = [
        float(value)
        for value in data.get("conf", [])
        if str(value).strip() not in {"", "-1"}
    ]
    return lines, mean(confidences) if confidences else None


def extract_text_details(image: Any) -> OcrExtractionResult:
    if not is_ocr_available():
        dependency_error = get_ocr_dependency_message()
        LOGGER.error("OCR runtime unavailable: %s", dependency_error)
        return OcrExtractionResult([], dependency_error, None, "unavailable")

    try:
        img = _open_image(image)
    except Exception:
        LOGGER.exception(
            "OCR image decoding failed: type=%s",
            type(image).__name__,
        )
        return OcrExtractionResult(
            [],
            "图片文件无法读取，请重新上传有效的 PNG、JPEG 或 WEBP 图片。",
            None,
            "unavailable",
        )

    quality_errors: list[str] = []
    variants = _build_preprocessed_variants(img)
    engines = (
        ("PaddleOCR", is_paddle_ocr_available, _extract_with_paddle),
        ("Tesseract", is_tesseract_ocr_available, _extract_with_tesseract),
    )
    for engine_name, available, extractor in engines:
        if not available():
            continue
        valid_candidates: list[tuple[list[str], float | None, str]] = []
        for variant_name, variant in variants:
            try:
                lines, confidence = extractor(variant)
                quality_error = assess_text_quality(lines, confidence)
                if not quality_error:
                    valid_candidates.append((lines, confidence, variant_name))
                else:
                    quality_errors.append(quality_error)
            except Exception:
                LOGGER.exception(
                    "%s OCR failed on %s (size=%s mode=%s)",
                    engine_name,
                    variant_name,
                    getattr(variant, "size", "unknown"),
                    getattr(variant, "mode", "unknown"),
                )
        if valid_candidates:
            lines, confidence, variant_name = max(
                valid_candidates,
                key=lambda candidate: _candidate_score(candidate[0], candidate[1]),
            )
            cover_text = merge_cover_text(lines, [])
            return OcrExtractionResult(
                lines,
                "",
                confidence,
                f"{engine_name}:{variant_name}",
                cover_text=cover_text,
            )

    if quality_errors:
        LOGGER.error("OCR recognition failed quality validation: %s", quality_errors[-1])
        return OcrExtractionResult(
            [],
            quality_errors[-1] + " 可继续手动输入封面文字。",
            None,
            "unavailable",
        )
    initialization_error = "OCR 初始化或识别失败，请检查模型安装；也可继续手动输入封面文字。"
    LOGGER.error(initialization_error)
    return OcrExtractionResult(
        [],
        initialization_error,
        None,
        "unavailable",
    )


def extract_cover_text_details(
    image: Any,
    vision_reader: Any | None = None,
) -> OcrExtractionResult:
    """Run enhanced OCR, then use an optional visual text reader as fallback."""
    ocr_result = extract_text_details(image)
    vision_lines: list[str] = []
    vision_context: dict[str, Any] = {}
    vision_error = ""
    if callable(vision_reader):
        try:
            visual_result = vision_reader(image)
            if isinstance(visual_result, dict):
                vision_context = {
                    key: str(visual_result.get(key, "")).strip()
                    for key in ("content_type", "visual_scene", "education_value", "evidence")
                    if str(visual_result.get(key, "")).strip()
                }
                for key in ("cover_title", "small_text", "labels", "badges"):
                    value = visual_result.get(key, [])
                    if isinstance(value, str):
                        value = [value]
                    if isinstance(value, list):
                        vision_lines.extend(str(item).strip() for item in value if str(item).strip())
            elif isinstance(visual_result, (list, tuple)):
                vision_lines.extend(str(item).strip() for item in visual_result if str(item).strip())
        except Exception as error:
            vision_error = str(error)
            LOGGER.warning("Visual cover text recognition failed: %s", error)

    cover_text = merge_cover_text(ocr_result.lines, vision_lines)
    if cover_text:
        merged_lines = [line for line in cover_text.splitlines() if line.strip()]
        return OcrExtractionResult(
            merged_lines,
            "",
            ocr_result.average_confidence,
            "vision" if vision_lines else ocr_result.engine,
            cover_text=cover_text,
            vision_lines=tuple(vision_lines),
            vision_context=vision_context,
        )
    return OcrExtractionResult(
        [],
        vision_error or ocr_result.error,
        ocr_result.average_confidence,
        ocr_result.engine,
        cover_text="",
        vision_context=vision_context,
    )


def extract_text_with_status(image: Any) -> tuple[list[str], str]:
    result = extract_text_details(image)
    return result.lines, result.error


def extract_text(image: Any) -> list[str]:
    lines, _ = extract_text_with_status(image)
    return lines
