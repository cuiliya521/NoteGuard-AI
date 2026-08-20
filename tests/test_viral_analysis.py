from io import BytesIO
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

from services.image_input import normalize_image_input
from services.llm import (
    VIRAL_IMAGE_ANALYSIS_PROMPT,
    analyze_cover,
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
    def test_cover_description_is_sent_as_independent_ai_context(self) -> None:
        captured: dict[str, object] = {}
        response_content = json.dumps(
            {
                "score": 80,
                "attraction": 4,
                "dimensions": {},
                "issues": [],
                "suggestions": [],
                "recommended_copy": "数学学习方法",
            },
            ensure_ascii=False,
        )

        class FakeCompletions:
            def create(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=response_content))]
                )

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.chat = SimpleNamespace(completions=FakeCompletions())

        with (
            patch.dict(sys.modules, {"openai": SimpleNamespace(OpenAI=FakeOpenAI)}),
            patch("services.llm.get_deepseek_api_key", return_value="test-key"),
            patch("services.llm.print_deepseek_diagnostics"),
        ):
            result = analyze_cover(
                "数学学习方法",
                [],
                image_description="人物位于画面右侧，背景为课堂",
            )

        payload = json.loads(captured["messages"][1]["content"])
        self.assertEqual(payload["cover_text"], "数学学习方法")
        self.assertEqual(payload["image_description"], "人物位于画面右侧，背景为课堂")
        self.assertEqual(result["score"], 80)

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

    def test_image_breakdown_keeps_seven_research_fields(self) -> None:
        content = valid_image_analysis(
            cover_text_structure="问题句主标题 + 数字方法 + 人群说明",
            information_hierarchy="痛点、方法、适用人群",
            layout_method="主标题上置，辅助信息下置",
            first_glance="初二数学提分方法",
            click_factors=["明确年级", "给出3个方法"],
            trust_building="通过老师经验与方法过程建立信任",
            user_pain_expression="指出孩子错题反复的具体困扰",
            conversion_elements=["评论区领取复盘清单"],
            reusable_template="年级痛点 + 数字方法 + 适用人群",
        )

        result = parse_viral_image_analysis_response(content)

        self.assertIsNotNone(result)
        self.assertEqual(result["cover_text_structure"], "问题句主标题 + 数字方法 + 人群说明")
        self.assertEqual(result["information_hierarchy"], "痛点、方法、适用人群")
        self.assertEqual(result["layout_method"], "主标题上置，辅助信息下置")
        self.assertEqual(result["first_glance"], "初二数学提分方法")
        self.assertEqual(result["click_factors"], ["明确年级", "给出3个方法"])
        self.assertEqual(result["trust_building"], "通过老师经验与方法过程建立信任")
        self.assertEqual(result["user_pain_expression"], "指出孩子错题反复的具体困扰")
        self.assertEqual(result["conversion_elements"], ["评论区领取复盘清单"])
        self.assertEqual(result["reusable_template"], "年级痛点 + 数字方法 + 适用人群")

    def test_legacy_image_analysis_gets_research_field_fallbacks(self) -> None:
        result = parse_viral_image_analysis_response(valid_image_analysis())

        self.assertIsNotNone(result)
        self.assertEqual(result["first_glance"], "可能以主标题为焦点")
        self.assertEqual(result["click_factors"], ["主题文字直接"])
        self.assertEqual(result["user_pain_expression"], "数学学习困难")
        self.assertEqual(result["conversion_elements"], ["出现1V1"])
        self.assertIn("家长", result["reusable_template"])

    def test_ai_failure_returns_none_without_exception(self) -> None:
        with patch("services.llm.get_deepseek_api_key", return_value=""):
            result = analyze_viral_image({"ocr_text": "数学学习"})

        self.assertIsNone(result)

    def test_image_analysis_retries_network_failure_and_keeps_safe_diagnostics(self) -> None:
        attempts = {"count": 0}

        class FakeCompletions:
            def create(self, **kwargs):
                attempts["count"] += 1
                if attempts["count"] < 3:
                    raise ConnectionError("temporary network failure")
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content=valid_image_analysis())
                        )
                    ]
                )

        class FakeOpenAI:
            init_kwargs: list[dict] = []

            def __init__(self, **kwargs):
                self.init_kwargs.append(kwargs)
                self.chat = SimpleNamespace(completions=FakeCompletions())

        with (
            patch.dict(sys.modules, {"openai": SimpleNamespace(OpenAI=FakeOpenAI)}),
            patch("services.llm.get_deepseek_api_key", return_value="test-key"),
            patch("services.llm.print_deepseek_diagnostics"),
            patch("services.llm.time.sleep"),
        ):
            result = analyze_viral_image(
                {
                    "ocr_text": "初二数学",
                    "image_width": 1080,
                    "image_height": 1440,
                    "image_bytes_size": 204800,
                }
            )

        self.assertIsNotNone(result)
        self.assertEqual(attempts["count"], 3)
        self.assertTrue(all(item["max_retries"] == 0 for item in FakeOpenAI.init_kwargs))
        self.assertTrue(all(item["timeout"] == 20.0 for item in FakeOpenAI.init_kwargs))


if __name__ == "__main__":
    unittest.main()
