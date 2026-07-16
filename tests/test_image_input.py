from io import BytesIO
from unittest.mock import patch
import unittest

from PIL import Image

from services.clipboard_image import extract_pasted_image, load_paste_image_button
from services.image_input import (
    ImageInputError,
    normalize_image_input,
    store_image_payload,
)


def make_png(color: str = "red") -> bytes:
    image = Image.new("RGB", (16, 16), color=color)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class UploadedImage:
    def __init__(self, image_bytes: bytes) -> None:
        self._image_bytes = image_bytes

    def getvalue(self) -> bytes:
        return self._image_bytes


class PasteResult:
    def __init__(self, image_data: object) -> None:
        self.image_data = image_data


class ImageInputTests(unittest.TestCase):
    def test_upload_and_clipboard_use_the_same_normalizer(self) -> None:
        image_bytes = make_png()
        uploaded = normalize_image_input(UploadedImage(image_bytes), "upload")
        clipboard_image = Image.open(BytesIO(image_bytes))
        pasted = normalize_image_input(clipboard_image, "clipboard")

        self.assertEqual(uploaded.image_format, "PNG")
        self.assertEqual(pasted.image_format, "PNG")
        self.assertEqual(uploaded.image_hash, pasted.image_hash)

    def test_valid_clipboard_png_has_sha256_hash(self) -> None:
        payload = normalize_image_input(
            Image.open(BytesIO(make_png())),
            "clipboard",
        )

        self.assertEqual(len(payload.image_hash), 64)
        self.assertTrue(payload.image_bytes.startswith(b"\x89PNG"))

    def test_same_image_does_not_clear_or_repeat_processing_state(self) -> None:
        payload = normalize_image_input(make_png(), "clipboard")
        state = {"cover_ocr_lines": ["数学"], "cover_analysis": {"score": 80}}

        self.assertTrue(store_image_payload(state, payload))
        state["cover_ocr_lines"] = ["数学"]
        state["cover_analysis"] = {"score": 80}
        self.assertFalse(store_image_payload(state, payload))
        self.assertEqual(state["cover_ocr_lines"], ["数学"])
        self.assertEqual(state["cover_analysis"]["score"], 80)

    def test_new_image_clears_previous_ocr_and_analysis(self) -> None:
        first = normalize_image_input(make_png("red"), "upload")
        second = normalize_image_input(make_png("blue"), "clipboard")
        state: dict[str, object] = {}
        store_image_payload(state, first)
        state["cover_ocr_lines"] = ["旧文字"]
        state["cover_analysis"] = {"score": 50}

        self.assertTrue(store_image_payload(state, second))
        self.assertNotIn("cover_ocr_lines", state)
        self.assertNotIn("cover_analysis", state)
        self.assertEqual(state["draft_image_text"], "")
        self.assertEqual(state["current_image_source"], "clipboard")

    def test_empty_or_text_clipboard_returns_friendly_error(self) -> None:
        with self.assertRaisesRegex(ImageInputError, "没有可用图片"):
            normalize_image_input(None, "clipboard")
        with self.assertRaisesRegex(ImageInputError, "不是图片"):
            normalize_image_input("clipboard text", "clipboard")

        image, message = extract_pasted_image(PasteResult("clipboard text"))
        self.assertIsNone(image)
        self.assertIn("不是图片", message)

    def test_damaged_image_does_not_raise_unhandled_exception(self) -> None:
        with self.assertRaisesRegex(ImageInputError, "损坏"):
            normalize_image_input(b"not-an-image", "clipboard")

    def test_missing_component_does_not_affect_upload_processing(self) -> None:
        with self.assertLogs("services.clipboard_image", level="ERROR") as logs:
            with patch(
                "services.clipboard_image.import_module",
                side_effect=ModuleNotFoundError("test dependency missing"),
            ):
                paste_button, message = load_paste_image_button()

        uploaded = normalize_image_input(UploadedImage(make_png()), "upload")
        self.assertIsNone(paste_button)
        self.assertIn("文件上传", message)
        self.assertIn("test dependency missing", "\n".join(logs.output))
        self.assertEqual(uploaded.image_format, "PNG")


if __name__ == "__main__":
    unittest.main()
