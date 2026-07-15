from io import BytesIO
import json
import unittest
from unittest.mock import patch

from PIL import Image

from services.image_input import normalize_image_input
from services.llm import (
    VIRAL_IMAGE_ANALYSIS_PROMPT,
    analyze_viral_image,
    parse_viral_image_analysis_response,
)
from services.viral_analyzer import (
    IMAGE_INFERENCE_NOTICE,
    build_viral_image_context,
    can_analyze_viral_input,
    store_viral_image_payload,
)


def image_bytes(color: str) -> bytes:
    image = Image.new("RGB", (100, 150), color=color)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def valid_image_analysis(**extra) -> str:
    payload = {
        "attraction_points": ["主题文字直接"],
        "layout_structure": {
            "headline_position": "建议主标题位于上部",
            "text_hierarchy": "建议减少层级",
            "information_density": "文字信息适中",
            "visual_focus": "可能以主标题为焦点",
            "element_relationship": "现有信息不足",
        },
        "copy_structure": {
            "target_audience": "家长",
            "pain_point": "数学学习困难",
            "credibility": "未提供",
            "service_information": "出现1V1",
        },
        "risk_points": [],
        "reusable_elements": ["具体问题"],
        "avoid_copying": ["效果承诺"],
        **extra,
    }
    return json.dumps(payload, ensure_ascii=False)


class ViralAnalysisTests(unittest.TestCase):
    def test_link_failure_does_not_block_manual_input(self) -> None:
        self.assertTrue(can_analyze_viral_input("手动标题", ""))
        self.assertTrue(can_analyze_viral_input("", "手动正文"))

    def test_uploaded_image_enters_viral_image_state(self) -> None:
        payload = normalize_image_input(image_bytes("red"), "upload")
        state: dict[str, object] = {}

        self.assertTrue(store_viral_image_payload(state, payload))
        self.assertEqual(state["viral_image_hash"], payload.image_hash)
        self.assertEqual(state["viral_image_width"], 100)

    def test_same_image_does_not_repeat_processing(self) -> None:
        payload = normalize_image_input(image_bytes("red"), "clipboard")
        state: dict[str, object] = {}
        store_viral_image_payload(state, payload)
        state["viral_image_ocr_lines"] = ["已有OCR"]

        self.assertFalse(store_viral_image_payload(state, payload))
        self.assertEqual(state["viral_image_ocr_lines"], ["已有OCR"])

    def test_new_image_clears_previous_results(self) -> None:
        first = normalize_image_input(image_bytes("red"), "upload")
        second = normalize_image_input(image_bytes("blue"), "clipboard")
        state: dict[str, object] = {}
        store_viral_image_payload(state, first)
        state["viral_image_ocr_lines"] = ["旧文字"]
        state["viral_image_analysis"] = {"old": True}

        self.assertTrue(store_viral_image_payload(state, second))
        self.assertNotIn("viral_image_ocr_lines", state)
        self.assertNotIn("viral_image_analysis", state)

    def test_image_analysis_declares_non_multimodal_boundary(self) -> None:
        state = {
            "viral_image_width": 100,
            "viral_image_height": 150,
            "viral_image_text": "数学1V1",
        }
        context = build_viral_image_context(state)

        self.assertEqual(
            context["analysis_capability"],
            "ocr_dimensions_and_user_description_only",
        )
        self.assertIn("属于推断", IMAGE_INFERENCE_NOTICE)
        self.assertIn("没有多模态视觉模型", VIRAL_IMAGE_ANALYSIS_PROMPT)

    def test_unverifiable_performance_metrics_are_rejected(self) -> None:
        content = valid_image_analysis(
            attraction_points=["预计CTR会提升"],
        )

        self.assertIsNone(parse_viral_image_analysis_response(content))

    def test_whitelisted_result_does_not_expose_unknown_fields(self) -> None:
        content = valid_image_analysis(ctr="25%", exposure="100万")
        result = parse_viral_image_analysis_response(content)

        self.assertIsNotNone(result)
        self.assertNotIn("ctr", result)
        self.assertNotIn("exposure", result)

    def test_ai_failure_returns_none_without_exception(self) -> None:
        with patch("services.llm.get_deepseek_api_key", return_value=""):
            result = analyze_viral_image({"ocr_text": "数学学习"})

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
