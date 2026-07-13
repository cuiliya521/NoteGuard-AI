from __future__ import annotations

import re
from io import BytesIO
from statistics import mean
from typing import Any


def is_ocr_available() -> bool:
    try:
        import pytesseract
        from PIL import Image  # noqa: F401

        pytesseract.get_tesseract_version()
        return "chi_sim" in pytesseract.get_languages(config="")
    except Exception:
        return False


def assess_text_quality(lines: list[str], average_confidence: float | None = None) -> str:
    text = "".join(lines).strip()
    if len(text) < 2:
        return "未识别到足够的文字。"

    chinese_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    symbol_count = len(re.findall(r"[^\u4e00-\u9fffA-Za-z0-9\s，。！？：、】【（）()、,.!?-]", text))

    if chinese_count < 2 and latin_count >= 4:
        return "识别结果几乎没有中文，可能是乱码或中文识别模型未配置。"
    if re.search(r"([^\s])\1{3,}", text) or re.search(r"(.{2,4})\1{2,}", text):
        return "识别结果存在大量重复字符，可能是乱码。"
    if symbol_count > max(4, len(text) // 3):
        return "识别结果包含过多无意义符号，可能是乱码。"
    if average_confidence is not None and average_confidence < 25:
        return "OCR 置信度过低，识别结果不可靠。"
    return ""


def extract_text_with_status(image: Any) -> tuple[list[str], str]:
    if not is_ocr_available():
        return [], "OCR 依赖或中文识别模型未安装。"

    try:
        from PIL import Image
        import pytesseract
        from pytesseract import Output

        if isinstance(image, bytes):
            img = Image.open(BytesIO(image))
        elif hasattr(image, "getvalue"):
            img = Image.open(BytesIO(image.getvalue()))
        elif hasattr(image, "read"):
            img = Image.open(image)
        else:
            img = Image.open(image)

        img = img.convert("RGB")
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
        quality_error = assess_text_quality(
            lines,
            mean(confidences) if confidences else None,
        )
        if quality_error:
            return [], quality_error
        return lines, ""
    except Exception:
        return [], "暂未成功识别图片文字。"


def extract_text(image: Any) -> list[str]:
    lines, _ = extract_text_with_status(image)
    return lines
