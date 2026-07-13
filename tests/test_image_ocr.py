from unittest.mock import patch
import unittest

from services.image_ocr import assess_text_quality, extract_text_with_status


class ImageOcrTests(unittest.TestCase):
    def test_ocr_quality_rejects_empty_garbled_repeated_and_low_confidence_text(self) -> None:
        self.assertEqual(assess_text_quality([]), "未识别到足够的文字。")
        self.assertIn("几乎没有中文", assess_text_quality(["abcdef"]))
        self.assertIn("重复字符", assess_text_quality(["哈哈哈哈哈哈"]))
        self.assertIn("无意义符号", assess_text_quality(["数学@@@###$$$"]))
        self.assertIn("置信度过低", assess_text_quality(["数学学习"], average_confidence=10))

    def test_missing_ocr_dependency_degrades_without_exception(self) -> None:
        with patch("services.image_ocr.is_ocr_available", return_value=False):
            lines, message = extract_text_with_status(b"not-an-image")

        self.assertEqual(lines, [])
        self.assertIn("OCR", message)
