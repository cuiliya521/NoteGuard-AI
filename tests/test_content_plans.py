from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from services.content_plans import (
    build_content_plan,
    build_plan_reference_cases,
    load_content_plans,
    save_content_plan,
)


class ContentPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.method = {
            "id": "method-1",
            "name": "家长痛点解决型",
            "source_count": 2,
            "applicability": "初中数学 · 家长",
            "core_structure": "痛点 → 方法 → 证明 → 行动",
            "analysis": {
                "title_templates": [
                    {"value": "目标用户 + 具体问题 + 方法价值", "count": 2},
                ],
                "content_patterns": [
                    {"value": "问题引入 → 真实案例 → 方法展示 → 行动入口", "count": 2},
                ],
                "visual_patterns": [
                    {"value": "大标题突出问题，人物位于侧边", "count": 2},
                ],
            },
        }
        self.inputs = {
            "product_name": "初二数学学习规划",
            "target_user": "初二学生家长",
            "usage_scenario": "期中考试后",
            "core_selling_point": "真实错题复盘与学习计划",
            "problem_to_solve": "听懂但考试不会做",
        }

    def test_plan_uses_saved_method_and_real_inputs(self) -> None:
        plan = build_content_plan(self.method, self.inputs)

        self.assertEqual(plan["method"]["name"], "家长痛点解决型")
        self.assertEqual(plan["method"]["source_count"], 2)
        self.assertIn("初二学生家长", plan["content_direction"])
        self.assertEqual(
            plan["recommended_structure"],
            "问题引入 → 真实案例 → 方法展示 → 行动入口",
        )
        self.assertEqual(plan["title_directions"], ["目标用户 + 具体问题 + 方法价值"])
        self.assertIn("大标题突出问题", plan["cover_suggestion"]["visual_focus"])
        self.assertEqual(len(plan["body_framework"]), 4)

    def test_plan_does_not_generate_publish_ready_article(self) -> None:
        plan = build_content_plan(self.method, self.inputs)

        self.assertNotIn("article", plan)
        self.assertNotIn("generated_content", plan)
        self.assertTrue(all("：" in item for item in plan["body_framework"]))

    def test_business_profile_fields_are_reused_in_plan(self) -> None:
        inputs = {
            **self.inputs,
            "business_profile_id": "profile-1",
            "brand_name": "林老师数学",
            "common_pain_points": "错题反复出现",
            "conversion_method": "评论区领取错题清单",
            "promotion_theme": "期中考试后的错题复盘",
        }

        plan = build_content_plan(self.method, inputs)

        self.assertEqual(plan["inputs"]["business_profile_id"], "profile-1")
        self.assertEqual(plan["inputs"]["brand_name"], "林老师数学")
        self.assertEqual(plan["content_direction"], "期中考试后的错题复盘")
        self.assertIn("评论区领取错题清单", plan["body_framework"][-1])

    def test_required_real_inputs_are_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "产品/服务名称"):
            build_content_plan(self.method, {"target_user": "家长"})

    def test_method_source_cases_become_planning_references(self) -> None:
        method = {**self.method, "source_case_ids": ["case-1", "case-2"]}
        references = build_plan_reference_cases(
            method,
            [
                {
                    "id": "case-1",
                    "title": "初二数学错题复盘",
                    "model": {"core_structure": "问题 → 原因 → 方法"},
                },
                {
                    "id": "case-2",
                    "title": "家长真实评价",
                    "operation_review": {"save_reason": "真实反馈建立信任"},
                },
            ],
        )

        self.assertEqual([item["title"] for item in references], ["初二数学错题复盘", "家长真实评价"])
        self.assertEqual(references[0]["reuse_point"], "问题 → 原因 → 方法")
        self.assertEqual(references[1]["reuse_point"], "真实反馈建立信任")

    def test_save_and_load_content_plan(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "content_plans.json"
            plan = build_content_plan(self.method, self.inputs)

            saved = save_content_plan(path, plan)
            loaded = load_content_plans(path)

            self.assertTrue(saved["id"])
            self.assertTrue(saved["created_at"])
            self.assertEqual(loaded[0]["method"]["id"], "method-1")
            self.assertEqual(loaded[0]["inputs"]["product_name"], "初二数学学习规划")

    def test_missing_and_corrupt_files_degrade_safely(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "content_plans.json"
            self.assertEqual(load_content_plans(path), [])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), [])
            path.write_text("not-json", encoding="utf-8")
            self.assertEqual(load_content_plans(path), [])


if __name__ == "__main__":
    unittest.main()
