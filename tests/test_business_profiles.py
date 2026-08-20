from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from services.business_profiles import (
    build_material_profile_suggestion,
    load_business_profiles,
    save_business_profile,
)


class BusinessProfileTests(unittest.TestCase):
    def test_profile_can_be_created_and_updated(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "business_profiles.json"
            saved = save_business_profile(
                path,
                {
                    "product_name": "初二数学规划",
                    "brand_name": "林老师数学",
                    "target_user": "初二学生家长",
                    "common_pain_points": "听懂但不会做题",
                    "usage_scenario": "期中考试后",
                    "conversion_method": "评论区领取诊断清单",
                },
            )
            updated = save_business_profile(
                path,
                {**saved, "usage_scenario": "暑假规划"},
            )

            profiles = load_business_profiles(path)
            self.assertEqual(len(profiles), 1)
            self.assertEqual(updated["id"], saved["id"])
            self.assertEqual(profiles[0]["usage_scenario"], "暑假规划")

    def test_profile_requires_product_and_target_user(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "business_profiles.json"
            with self.assertRaisesRegex(ValueError, "产品/服务名称和目标用户"):
                save_business_profile(path, {"brand_name": "测试品牌"})

    def test_missing_and_corrupt_files_are_safe(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "business_profiles.json"
            self.assertEqual(load_business_profiles(path), [])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), [])
            path.write_text("bad-json", encoding="utf-8")
            self.assertEqual(load_business_profiles(path), [])

    def test_existing_ai_results_map_to_editable_business_fields(self) -> None:
        suggestion = build_material_profile_suggestion(
            title="初二数学错题复盘",
            ocr_text="林老师数学\n期中考试后怎么复盘",
            source_analysis={
                "cover_theme": "初二数学复盘服务",
                "target_audience": "初二学生家长",
                "selling_direction": "真实错题拆解",
                "content_type": "学习方法分享",
                "teacher_cues": "林老师数学",
            },
            image_analysis={
                "user_pain_expression": "错题反复出现",
                "conversion_elements": ["评论区领取错题清单"],
                "copy_structure": {"service_information": "数学学习规划"},
            },
        )

        self.assertEqual(suggestion["product_name"], "数学学习规划")
        self.assertEqual(suggestion["brand_name"], "林老师数学")
        self.assertEqual(suggestion["target_user"], "初二学生家长")
        self.assertEqual(suggestion["usage_scenario"], "学习方法分享")
        self.assertEqual(suggestion["common_pain_points"], "错题反复出现")
        self.assertEqual(suggestion["core_selling_point"], "真实错题拆解")
        self.assertEqual(suggestion["conversion_method"], "评论区领取错题清单")


if __name__ == "__main__":
    unittest.main()
