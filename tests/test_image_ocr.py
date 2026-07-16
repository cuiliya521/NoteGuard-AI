from unittest.mock import patch
import unittest

from services.image_ocr import (
    assess_text_quality,
    extract_text_with_status,
    get_available_ocr_engine,
)


class ImageOcrTests(unittest.TestCase):
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
