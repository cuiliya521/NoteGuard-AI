from __future__ import annotations

import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services.content_context import build_content_context, build_publish_diagnosis, build_publish_readiness
from services.llm import generate_title_candidates
from services.rule_checker import Finding


class ContentAdvisorTests(unittest.TestCase):
    def test_suggested_text_only_replaces_matched_expression(self) -> None:
        import app

        source = "初二数学30天提高50分，分享每天复盘的方法。"
        start = source.index("30天提高50分")
        finding = Finding(
            term="30天提高50分",
            position="标题",
            category="效果承诺",
            reason="结果承诺缺少依据",
            suggestion="30天学习调整记录",
            severity="high",
            start=start,
            end=start + len("30天提高50分"),
        )

        rendered = app.build_suggested_text_html(source, [finding], "标题")

        self.assertIn("30天学习调整记录", rendered)
        self.assertNotIn("30天提高50分", rendered)
        self.assertIn("初二数学", rendered)
        self.assertIn("分享每天复盘的方法", rendered)
        self.assertEqual(rendered.count('class="diff-insert"'), 1)

    def test_cover_ocr_text_uses_same_minimal_comparison(self) -> None:
        import app

        cover_text = "保证提分 一对一数学辅导"
        finding = Finding(
            term="保证提分",
            position="正文",
            category="效果承诺",
            reason="绝对化承诺",
            suggestion="分享提分方法",
            severity="high",
            start=0,
            end=4,
        )

        rendered = app.build_suggested_text_html(cover_text, [finding], "正文")

        self.assertIn("分享提分方法", rendered)
        self.assertIn("一对一数学辅导", rendered)

    def test_audit_feedback_has_delivery_sections(self) -> None:
        import app

        title_finding = Finding(
            term="30天提高50分",
            position="标题",
            category="效果承诺",
            reason="结果承诺缺少可验证依据",
            suggestion="改为真实过程和可验证变化",
            severity="high",
            start=8,
            end=16,
        )
        cover_finding = Finding(
            term="保证提分",
            position="正文",
            category="绝对化表达",
            reason="封面使用绝对化承诺",
            suggestion="改为经验分享",
            severity="medium",
            start=0,
            end=4,
        )

        feedback = app.build_audit_feedback(
            [title_finding],
            [cover_finding],
            {"why": "影响用户信任", "priority": "先修改标题承诺"},
        )

        for section in ("标题问题", "正文问题", "封面问题", "风险说明", "修改建议"):
            self.assertIn(section, feedback)
        self.assertIn("封面“保证提分”", feedback)

    def test_top_audit_issues_prioritize_high_severity(self) -> None:
        import app

        findings = [
            Finding("普通提醒", "正文", "表达", "一般问题", "稍后处理", "low", 0, 4),
            Finding("强承诺", "标题", "效果承诺", "重要问题", "优先修改", "high", 0, 3),
        ]

        issues = app.build_top_audit_issues(
            findings,
            [],
            {"problem": "用户定位不清", "priority": "补充目标年级"},
        )

        self.assertEqual(len(issues), 3)
        self.assertEqual(issues[0]["priority"], "P0")
        self.assertEqual(issues[0]["position"], "标题")

    def test_primary_diagnosis_uses_publish_language_not_audit_language(self) -> None:
        context = build_content_context(
            title="数学差生逆袭秘籍！30天提高50分",
            content="孩子数学成绩不好怎么办？老师分享学习方法。",
            cover_text="",
            cover_visual=None,
            creator_profile={},
        )

        result = build_publish_diagnosis(context)

        combined = " ".join(result.values())
        for forbidden in ("审核", "违规", "风险词", "安全改写"):
            self.assertNotIn(forbidden, combined)
        self.assertIn("年级", result["problem"])
        self.assertIn("为什么", "为什么影响发布")
        self.assertTrue(result["priority"].strip())

    def test_title_generation_retries_when_first_result_contains_original(self) -> None:
        original = "数学差生逆袭秘籍！30天提高50分"
        responses = [
            {"titles": [original, "候选2", "候选3", "候选4", "候选5"]},
            {
                "titles": [
                    "初二数学成绩不好？先看学习方法",
                    "初二孩子数学成绩不好，学习方法怎么选",
                    "数学成绩不好怎么办？初二家长先看方法",
                    "初二数学学习方法，先从成绩问题说起",
                    "孩子数学成绩不好？初二阶段这样找方法",
                ]
            },
        ]

        class FakeCompletions:
            def __init__(self) -> None:
                self.calls = 0

            def create(self, **kwargs):
                payload = responses[self.calls]
                self.calls += 1
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload, ensure_ascii=False)))]
                )

        completions = FakeCompletions()
        fake_client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        fake_openai = SimpleNamespace(OpenAI=lambda **kwargs: fake_client)
        with (
            patch("services.llm.get_deepseek_api_key", return_value="test-key"),
            patch("services.llm.print_deepseek_diagnostics"),
            patch.dict(sys.modules, {"openai": fake_openai}),
        ):
            titles = generate_title_candidates(
                original,
                "孩子数学成绩不好怎么办？老师分享学习方法。",
                [],
                creator_profile={"target_grades": "初二"},
            )

        self.assertEqual(completions.calls, 2)
        self.assertTrue(titles)
        self.assertNotIn(original, titles)
        self.assertIn("初二数学", titles[0])

    def test_problem_level_review_does_not_render_word_audit(self) -> None:
        import app

        review = app.build_problem_level_review(
            "数学差生逆袭秘籍！30天提高50分",
            "孩子数学成绩不好怎么办？老师分享学习方法。",
            [],
        )

        self.assertEqual(review["count"], 2)
        self.assertNotEqual(review["title_suggestion"], "数学差生逆袭秘籍！30天提高50分")
        self.assertIn("数学", review["title_suggestion"])
        self.assertNotIn("学习者", review["title_suggestion"])
        self.assertTrue(any("结果承诺" in problem for problem in review["title_problems"]))

    def test_publish_readiness_uses_coarse_product_score(self) -> None:
        context = build_content_context(
            title="数学差生逆袭秘籍！30天提高50分",
            content="孩子数学成绩不好怎么办？老师分享学习方法。",
            cover_text="",
            cover_visual=None,
            creator_profile={},
        )
        diagnosis = build_publish_diagnosis(context)

        readiness = build_publish_readiness(context, diagnosis)

        self.assertGreaterEqual(readiness["score"], 40)
        self.assertEqual(readiness["score"] % 5, 0)
        self.assertIn("用户定位", readiness["basis"])
        self.assertTrue(readiness["deductions"])
        self.assertTrue(all(item["points"] > 0 for item in readiness["deductions"]))

    def test_unconfigured_image_status_is_user_friendly(self) -> None:
        import app

        with (
            patch.object(app, "image_analysis_capability", return_value=(False, "None")),
            patch.object(app, "is_development_mode", return_value=False),
            patch.object(app.st, "error") as error_mock,
        ):
            app.render_image_analysis_status("")

        message = error_mock.call_args.args[0]
        self.assertEqual(message, "图片文字识别失败，请检查OCR环境")

    def test_unconfigured_image_analysis_reports_none(self) -> None:
        import app

        with (
            patch.object(app, "get_available_ocr_engine", return_value="unavailable"),
            patch.object(app, "is_vision_text_available", return_value=False),
        ):
            available, source = app.image_analysis_capability()

        self.assertFalse(available)
        self.assertEqual(source, "None")

    def test_stale_content_context_module_is_reloaded(self) -> None:
        import app

        stale_module = SimpleNamespace()

        def reload_module(module):
            module.build_publish_diagnosis = lambda context: {"problem": "reloaded"}
            return module

        with (
            patch.object(app, "content_context_service", stale_module),
            patch.object(app.importlib, "invalidate_caches"),
            patch.object(app.importlib, "reload", side_effect=reload_module) as reload_mock,
        ):
            function = app._load_content_context_function("build_publish_diagnosis")

        self.assertEqual(function({})["problem"], "reloaded")
        reload_mock.assert_called_once_with(stale_module)


if __name__ == "__main__":
    unittest.main()
