import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from services.llm import (
    generate_content_lab_draft,
    parse_content_lab_draft_response,
)


def draft_payload() -> dict:
    return {
        "titles": ["标题一", "标题二", "标题三", "标题四", "标题五"],
        "cover_copy": {
            "main_title": "初二数学错题怎么复盘",
            "subtitle": "从反复出错到找到原因",
            "visual_suggestion": "主标题优先，副标题补充场景",
        },
        "body": {
            "opening_hook": "期中考试后，先别急着刷更多题。",
            "user_pain": "不少家长发现孩子同类题反复出错。",
            "real_experience": "依据已确认的教学观察说明常见情况。",
            "solution": "先按题型归类，再记录错误原因。",
            "product_intro": "结合真实学习规划提供复盘支持。",
            "action_guide": "可以从最近一张试卷开始整理。",
            "full_text": "期中考试后，先别急着刷更多题。\n\n先按题型归类，再记录错误原因。\n\n"
            + "围绕真实错题梳理原因并记录调整过程。" * 50,
        },
        "publishing": {
            "tags": ["#初二数学", "#错题复盘", "#学习方法", "#家长教育", "#期中考试"],
            "comment_question": "你家孩子最常在哪类题上反复出错？",
            "timing_advice": "结合账号历史活跃时段测试。",
            "reused_points": ["问题引入 → 方法展示 → 行动入口"],
        },
    }


class ContentLabGenerationTests(unittest.TestCase):
    def test_parser_keeps_complete_publish_sections(self) -> None:
        parsed = parse_content_lab_draft_response(
            json.dumps(draft_payload(), ensure_ascii=False)
        )

        self.assertEqual(len(parsed["titles"]), 5)
        self.assertEqual(parsed["cover_copy"]["main_title"], "初二数学错题怎么复盘")
        self.assertIn("先按题型归类", parsed["body"]["full_text"])
        self.assertEqual(len(parsed["publishing"]["tags"]), 5)
        self.assertEqual(
            parsed["publishing"]["comment_question"],
            "你家孩子最常在哪类题上反复出错？",
        )

    def test_generation_receives_material_profile_method_and_plan(self) -> None:
        captured: dict[str, object] = {}
        response_content = json.dumps(draft_payload(), ensure_ascii=False)

        class FakeCompletions:
            def create(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=response_content))]
                )

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.chat = SimpleNamespace(completions=FakeCompletions())

        material = {
            "has_uploaded_image": True,
            "ocr_text": "初二数学错题复盘",
            "ai_recognition": {"target_user": "初二学生家长"},
        }
        profile = {"product_name": "数学学习规划", "target_user": "初二学生家长"}
        method = {"id": "method-1", "name": "问题解决型"}
        plan = {"content_direction": "期中考试后的错题复盘"}

        with (
            patch.dict(sys.modules, {"openai": SimpleNamespace(OpenAI=FakeOpenAI)}),
            patch("services.llm.get_deepseek_api_key", return_value="test-key"),
            patch("services.llm.print_deepseek_diagnostics"),
        ):
            result = generate_content_lab_draft(plan, material, profile, method)

        request = json.loads(captured["messages"][1]["content"])
        self.assertTrue(request["material"]["has_uploaded_image"])
        self.assertEqual(request["material"]["ocr_text"], "初二数学错题复盘")
        self.assertEqual(request["business_profile"]["target_user"], "初二学生家长")
        self.assertEqual(request["method_model"]["id"], "method-1")
        self.assertEqual(request["content_plan"]["content_direction"], "期中考试后的错题复盘")
        self.assertEqual(len(result["titles"]), 5)

    def test_incomplete_result_is_rejected(self) -> None:
        incomplete = draft_payload()
        incomplete["titles"] = ["只有一个标题"]

        self.assertIsNone(
            parse_content_lab_draft_response(json.dumps(incomplete, ensure_ascii=False))
        )

    def test_body_outside_publish_length_is_rejected(self) -> None:
        too_long = draft_payload()
        too_long["body"]["full_text"] = "内容" * 751

        self.assertIsNone(
            parse_content_lab_draft_response(json.dumps(too_long, ensure_ascii=False))
        )

    def test_generation_retries_when_body_looks_like_analysis_report(self) -> None:
        captured_prompts: list[str] = []
        report_style = draft_payload()
        report_style["body"]["full_text"] = (
            "根据案例，本文分析用户痛点和转化路径。" + "这是一段结构分析。" * 120
        )
        publish_style = draft_payload()
        responses = [
            json.dumps(report_style, ensure_ascii=False),
            json.dumps(publish_style, ensure_ascii=False),
        ]

        class FakeCompletions:
            def create(self, **kwargs):
                captured_prompts.append(kwargs["messages"][0]["content"])
                content = responses.pop(0)
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
                )

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.chat = SimpleNamespace(completions=FakeCompletions())

        with (
            patch.dict(sys.modules, {"openai": SimpleNamespace(OpenAI=FakeOpenAI)}),
            patch("services.llm.get_deepseek_api_key", return_value="test-key"),
            patch("services.llm.print_deepseek_diagnostics"),
        ):
            result = generate_content_lab_draft(
                {"content_direction": "错题复盘"},
                {"ocr_text": "初二数学错题复盘"},
                {"target_user": "初二学生家长"},
                {"name": "问题解决型"},
            )

        self.assertIsNotNone(result)
        self.assertEqual(len(captured_prompts), 2)
        self.assertIn("标题结构", captured_prompts[0])
        self.assertIn("开头方式", captured_prompts[0])
        self.assertIn("用户痛点表达", captured_prompts[0])
        self.assertIn("信任建立方式", captured_prompts[0])
        self.assertIn("转化路径", captured_prompts[0])
        self.assertNotIn("本文分析", result["body"]["full_text"])

    def test_generation_retries_short_body_until_publish_length_passes(self) -> None:
        captured_user_prompts: list[str] = []
        first_short = draft_payload()
        first_short["body"]["full_text"] = "示例正文" * 120
        second_short = draft_payload()
        second_short["body"]["full_text"] = "示例正文" * 190
        complete = draft_payload()
        responses = [
            json.dumps(first_short, ensure_ascii=False),
            json.dumps(second_short, ensure_ascii=False),
            json.dumps(complete, ensure_ascii=False),
        ]

        class FakeCompletions:
            def create(self, **kwargs):
                captured_user_prompts.append(kwargs["messages"][1]["content"])
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content=responses.pop(0))
                        )
                    ]
                )

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.chat = SimpleNamespace(completions=FakeCompletions())

        with (
            patch.dict(sys.modules, {"openai": SimpleNamespace(OpenAI=FakeOpenAI)}),
            patch("services.llm.get_deepseek_api_key", return_value="test-key"),
            patch("services.llm.print_deepseek_diagnostics"),
        ):
            result = generate_content_lab_draft(
                {"content_direction": "错题复盘"},
                {"ocr_text": "初二数学错题复盘"},
                {"target_user": "初二学生家长"},
                {"name": "问题解决型"},
            )

        self.assertIsNotNone(result)
        self.assertEqual(len(captured_user_prompts), 3)
        self.assertIn("800至1500", captured_user_prompts[1])
        self.assertIn("1100至1300", captured_user_prompts[2])
        self.assertGreaterEqual(len(result["body"]["full_text"]), 800)


if __name__ == "__main__":
    unittest.main()
