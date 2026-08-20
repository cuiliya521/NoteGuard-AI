from unittest.mock import patch
from io import BytesIO
import unittest

from PIL import Image, ImageDraw

from services.image_ocr import (
    OcrExtractionResult,
    _build_preprocessed_variants,
    assess_text_quality,
    extract_cover_text_details,
    extract_text_with_status,
    get_available_ocr_engine,
    merge_cover_text,
)


class ImageOcrTests(unittest.TestCase):
    @staticmethod
    def _cover_image_bytes() -> bytes:
        image = Image.new("RGB", (900, 1200), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((80, 180, 820, 420), fill="black")
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    def test_available_engine_prefers_paddle_and_falls_back_to_tesseract(self) -> None:
        with (
            patch("services.image_ocr.is_paddle_ocr_available", return_value=True),
            patch("services.image_ocr.is_tesseract_ocr_available", return_value=True),
        ):
            self.assertEqual(get_available_ocr_engine(), "paddleocr")

        with (
            patch("services.image_ocr.is_paddle_ocr_available", return_value=False),
            patch("services.image_ocr.is_tesseract_ocr_available", return_value=True),
        ):
            self.assertEqual(get_available_ocr_engine(), "tesseract-chi_sim")

    def test_ocr_quality_rejects_empty_garbled_repeated_and_low_confidence_text(self) -> None:
        self.assertEqual(assess_text_quality([]), "未识别到足够的文字。")
        self.assertIn("几乎没有中文", assess_text_quality(["abcdef"]))
        self.assertIn("重复字符", assess_text_quality(["哈哈哈哈哈哈"]))
        self.assertIn("无意义符号", assess_text_quality(["数学@@@###$$$"]))
        self.assertIn("置信度过低", assess_text_quality(["数学学习"], average_confidence=10))

    def test_missing_ocr_dependency_degrades_without_exception(self) -> None:
        with (
            patch("services.image_ocr.is_ocr_available", return_value=False),
            patch("services.image_ocr.is_paddle_ocr_available", return_value=False),
            patch("services.image_ocr.is_tesseract_ocr_available", return_value=False),
        ):
            lines, message = extract_text_with_status(b"not-an-image")

        self.assertEqual(lines, [])
        self.assertIn("PaddleOCR", message)
        self.assertIn("chi_sim", message)

    @patch("services.image_ocr._open_image", return_value=object())
    @patch("services.image_ocr.is_tesseract_ocr_available", return_value=True)
    @patch("services.image_ocr.is_paddle_ocr_available", return_value=True)
    @patch("services.image_ocr._extract_with_tesseract")
    @patch("services.image_ocr._extract_with_paddle", return_value=(["数学学习"], 95))
    def test_paddle_is_preferred_over_tesseract(
        self,
        paddle_extract,
        tesseract_extract,
        paddle_available,
        tesseract_available,
        open_image,
    ) -> None:
        lines, message = extract_text_with_status(b"image")

        self.assertEqual(lines, ["数学学习"])
        self.assertEqual(message, "")
        paddle_extract.assert_called_once()
        tesseract_extract.assert_not_called()

    @patch("services.image_ocr._open_image", return_value=object())
    @patch("services.image_ocr.is_tesseract_ocr_available", return_value=True)
    @patch("services.image_ocr.is_paddle_ocr_available", return_value=True)
    @patch("services.image_ocr._extract_with_tesseract", return_value=(["封面文字"], 90))
    @patch("services.image_ocr._extract_with_paddle", side_effect=RuntimeError("model unavailable"))
    def test_tesseract_fallback_when_paddle_fails(
        self,
        paddle_extract,
        tesseract_extract,
        paddle_available,
        tesseract_available,
        open_image,
    ) -> None:
        lines, message = extract_text_with_status(b"image")

        self.assertEqual(lines, ["封面文字"])
        self.assertEqual(message, "")
        paddle_extract.assert_called_once()
        tesseract_extract.assert_called_once()

    def test_preprocessing_builds_multiple_ocr_attempts(self) -> None:
        image = Image.open(BytesIO(self._cover_image_bytes())).convert("RGB")
        variants = _build_preprocessed_variants(image)

        self.assertGreaterEqual(len(variants), 5)
        self.assertEqual(
            {name for name, _ in variants},
            {"compressed", "enlarged", "grayscale", "contrast", "threshold"},
        )
        self.assertGreater(variants[1][1].width, image.width)

    def test_visual_fallback_returns_cover_text_for_chinese_cover(self) -> None:
        empty_ocr = OcrExtractionResult(
            [],
            "local OCR unavailable",
            None,
            "unavailable",
        )
        visual_result = {
            "cover_title": ["孩子数学学习方法"],
            "small_text": ["家长可用的三步复盘清单"],
            "labels": ["小学数学"],
            "badges": ["免费试听"],
            "content_type": "学习方法分享",
            "visual_scene": "教育方法信息卡",
            "education_value": "提供可执行的复盘方法",
            "evidence": "画面包含方法标题和步骤说明",
        }
        with patch("services.image_ocr.extract_text_details", return_value=empty_ocr):
            result = extract_cover_text_details(
                self._cover_image_bytes(),
                vision_reader=lambda image: visual_result,
            )

        self.assertTrue(result.cover_text.strip())
        self.assertIn("孩子数学学习方法", result.cover_text)
        self.assertIn("家长可用的三步复盘清单", result.cover_text)
        self.assertEqual(result.vision_context["content_type"], "学习方法分享")

    def test_visual_text_has_priority_when_sources_overlap(self) -> None:
        merged = merge_cover_text(
            ["30天保证提分", "小学数学"],
            ["30天学习调整记录", "小学数学"],
        )

        self.assertEqual(merged.splitlines()[0], "30天学习调整记录")
        self.assertNotIn("30天保证提分", merged)
        self.assertEqual(merged.count("小学数学"), 1)
