from __future__ import annotations

from functools import lru_cache
from io import BytesIO
import logging
import re
from statistics import mean
from typing import Any


LOGGER = logging.getLogger(__name__)


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

    if isinstance(image, bytes):
        img = Image.open(BytesIO(image))
    elif hasattr(image, "getvalue"):
        img = Image.open(BytesIO(image.getvalue()))
    elif hasattr(image, "read"):
        img = Image.open(image)
    else:
        img = Image.open(image)
    return img.convert("RGB")


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

    output = _get_paddle_reader().predict(input=np.asarray(img))
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


def extract_text_with_status(image: Any) -> tuple[list[str], str]:
    if not is_ocr_available():
        return [], get_ocr_dependency_message()

    try:
        img = _open_image(image)
    except Exception:
        return [], "图片文件无法读取，请重新上传有效的 PNG、JPEG 或 WEBP 图片。"

    quality_errors: list[str] = []
    engines = (
        ("PaddleOCR", is_paddle_ocr_available, _extract_with_paddle),
        ("Tesseract", is_tesseract_ocr_available, _extract_with_tesseract),
    )
    for engine_name, available, extractor in engines:
        if not available():
            continue
        try:
            lines, confidence = extractor(img)
            quality_error = assess_text_quality(lines, confidence)
            if not quality_error:
                return lines, ""
            quality_errors.append(quality_error)
        except Exception as error:
            LOGGER.warning("%s OCR failed: %s", engine_name, error)

    if quality_errors:
        return [], quality_errors[-1] + " 可继续手动输入封面文字。"
    return [], "OCR 初始化或识别失败，请检查模型安装；也可继续手动输入封面文字。"


def extract_text(image: Any) -> list[str]:
    lines, _ = extract_text_with_status(image)
    return lines
