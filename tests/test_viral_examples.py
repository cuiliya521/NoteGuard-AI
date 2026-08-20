from pathlib import Path
from tempfile import TemporaryDirectory
import json
import re
import unittest

from services.viral_examples import (
    build_cover_visual_analysis,
    build_case_comparison,
    build_combined_case_analysis,
    delete_viral_case,
    filter_viral_cases,
    load_viral_cases,
    load_viral_examples,
    load_method_models,
    save_method_model,
    save_viral_case,
    update_viral_case_operation,
    update_viral_case_tags,
)


class ViralExamplesTests(unittest.TestCase):
    def test_public_examples_keep_structure_without_private_business_markers(self) -> None:
        path = Path(__file__).resolve().parents[1] / "data" / "viral_examples.json"
        examples = load_viral_examples(path)
        serialized = json.dumps(examples, ensure_ascii=False)

        self.assertEqual(len(examples), 3)
        self.assertTrue(all(example["structure"] for example in examples))
        self.assertTrue(all(example["opening_style"] for example in examples))
        self.assertTrue(all(example["conversion_style"] for example in examples))
        self.assertIn("公开Demo", serialized)
        self.assertIsNone(re.search(r"\d+\s*(?:元|r)/", serialized, re.IGNORECASE))
        self.assertIsNone(re.search(r"20\d{2}[年.-]", serialized))
        self.assertIsNone(re.search(r"\d+节免费", serialized))

    def test_missing_file_is_created_as_empty_list(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "viral_examples.json"

            self.assertEqual(load_viral_examples(path), [])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), [])

    def test_invalid_records_are_ignored_and_fields_are_normalized(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "viral_examples.json"
            path.write_text(
                json.dumps(
                    [
                        {"title": "  初二数学怎么学  ", "content": "  方法分享  "},
                        {"title": "", "content": ""},
                        "invalid",
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                load_viral_examples(path),
                [
                    {
                        "title": "初二数学怎么学",
                        "content": "方法分享",
                        "category": "",
                        "structure": "",
                        "opening_style": "",
                        "pain_points": "",
                        "selling_points": "",
                        "conversion_style": "",
                    }
                ],
            )

    def test_extended_style_fields_are_preserved(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "viral_examples.json"
            record = {
                "title": "初二数学总卡壳",
                "content": "家长场景开头，再拆方法。",
                "category": "精准筛选型",
                "structure": "痛点→分析→方法→服务",
                "opening_style": "目标用户+问题场景",
                "pain_points": "陪学费力",
                "selling_points": "线上陪练",
                "conversion_style": "咨询学习规划",
            }
            path.write_text(json.dumps([record], ensure_ascii=False), encoding="utf-8")

            self.assertEqual(load_viral_examples(path), [record])

    def test_corrupt_file_degrades_to_empty_examples(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "viral_examples.json"
            path.write_text("not json", encoding="utf-8")

            self.assertEqual(load_viral_examples(path), [])

    def test_saved_case_keeps_material_cover_analysis_and_tags(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "viral_case_library.json"
            saved = save_viral_case(
                path,
                {
                    "original_material": {
                        "source": "公开链接",
                        "title": "初二数学复盘",
                        "cover_image": "https://example.com/cover.jpg",
                        "content_images": ["https://example.com/body-1.jpg"],
                    },
                    "title": "初二数学复盘",
                    "content": "从一道错题开始复盘。",
                    "cover": {"ocr_text": "初二数学", "image_data": "data:image/png;base64,abc"},
                    "analysis": {"text": {"score": 82}, "image": {}},
                    "tags": ["初二数学", "方法分享", "初二数学"],
                    "tag_dimensions": {
                        "subject": "初中数学",
                        "audience": "初中生家长",
                        "content_type": "方法分享",
                        "scenario": "错题复盘",
                    },
                    "model": {
                        "model_name": "初二数学内容模型",
                        "content_type": "学习方法分享",
                    },
                },
            )

            self.assertTrue(saved["id"])
            self.assertEqual(saved["tags"], ["初二数学", "方法分享"])
            self.assertEqual(
                saved["tag_dimensions"],
                {
                    "subject": "初中数学",
                    "audience": "初中生家长",
                    "content_type": "方法分享",
                    "scenario": "错题复盘",
                },
            )
            self.assertEqual(saved["model"]["content_type"], "学习方法分享")
            self.assertEqual(saved["original_material"]["cover_image"], "https://example.com/cover.jpg")
            self.assertEqual(
                saved["original_material"]["content_images"],
                ["https://example.com/body-1.jpg"],
            )
            self.assertEqual(load_viral_cases(path), [saved])

    def test_cover_visual_analysis_uses_only_available_evidence(self) -> None:
        result = build_cover_visual_analysis(
            {
                "ocr_text": "孩子数学成绩下降怎么办\n初中数学\n12年教学经验",
                "description": "浅色背景、黑色字，老师人物位于右侧并避让文字区域，整体高对比",
            },
            {
                "first_glance": "孩子数学成绩下降怎么办",
                "trust_building": "12年教学经验",
            },
        )

        self.assertEqual(result["font_hierarchy"]["primary"], "孩子数学成绩下降怎么办")
        self.assertEqual(result["font_hierarchy"]["secondary"], "初中数学 / 12年教学经验")
        self.assertEqual(result["color_analysis"]["background_color"], "浅色")
        self.assertEqual(result["color_analysis"]["text_color"], "黑色")
        self.assertEqual(result["subject_position"]["position"], "右侧")
        self.assertEqual(result["visual_focus"][0], "孩子数学成绩下降怎么办")
        self.assertIn("基于图片尺寸、OCR文字位置和图片描述推断", result["basis_notice"])

    def test_cover_visual_analysis_does_not_invent_unobserved_colors_or_people(self) -> None:
        result = build_cover_visual_analysis(
            {"ocr_text": "初二数学复盘"},
            {},
        )

        self.assertEqual(result["color_analysis"]["primary_color"], "")
        self.assertEqual(result["color_analysis"]["contrast"], "")
        self.assertEqual(result["subject_position"]["person_present"], "无法确认")
        self.assertEqual(result["subject_position"]["position"], "无法确认")

    def test_visual_fields_are_saved_and_legacy_cases_get_empty_defaults(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "viral_case_library.json"
            visual = build_cover_visual_analysis(
                {"ocr_text": "主标题\n辅助信息"},
                {"first_glance": "主标题"},
            )
            saved = save_viral_case(
                path,
                {
                    "title": "视觉案例",
                    "cover_visual_analysis": visual,
                },
            )
            path.write_text(
                json.dumps([saved, {"id": "legacy", "title": "旧案例"}], ensure_ascii=False),
                encoding="utf-8",
            )

            cases = load_viral_cases(path)

            self.assertEqual(cases[0]["cover_visual_analysis"]["visual_focus"], ["主标题", "辅助信息"])
            self.assertEqual(cases[1]["cover_visual_analysis"]["visual_focus"], [])
            self.assertEqual(cases[1]["cover_visual_analysis"]["font_hierarchy"]["primary"], "")

    def test_structured_model_is_derived_from_existing_analysis(self) -> None:
        from app import build_viral_model

        model = build_viral_model(
            "初二数学错题怎么复盘",
            "分享三个错题复盘步骤。",
            {
                "title_analysis": {
                    "target_audience": "初二学生家长",
                    "pain_point": "错题反复出现",
                    "click_attraction": "获得复盘方法",
                },
                "structure_analysis": {
                    "opening": "从家长发现错题反复切入",
                    "middle": "拆解三个复盘步骤",
                    "ending": "邀请家长交流卡点",
                },
                "viral_reasons": ["用具体教学过程建立信任"],
            },
            None,
            ["初二数学", "方法分享"],
        )

        self.assertEqual(model["content_type"], "学习方法分享")
        self.assertEqual(model["user_pain"], "错题反复出现")
        self.assertIn("初二学生家长", model["title_structure"])
        self.assertTrue(model["reusable_title_formula"])

    def test_empty_case_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "viral_case_library.json"

            with self.assertRaises(ValueError):
                save_viral_case(path, {})

    def test_old_cases_with_missing_or_malformed_fields_remain_readable(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "viral_case_library.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "id": "legacy-1",
                            "title": "旧版案例",
                            "content": None,
                            "tags": "初中数学",
                            "cover": None,
                            "analysis": None,
                        },
                        {
                            "id": "legacy-image",
                            "cover": {"ocr_text": "初二数学提分方法"},
                        },
                        {},
                        "invalid",
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            cases = load_viral_cases(path)

            self.assertEqual(len(cases), 2)
            self.assertEqual(cases[0]["title"], "旧版案例")
            self.assertEqual(cases[0]["content"], "")
            self.assertEqual(cases[0]["tags"], ["初中数学"])
            self.assertEqual(cases[0]["cover"], {})
            self.assertEqual(cases[0]["analysis"], {})
            self.assertEqual(cases[0]["source_info"]["platform"], "")
            self.assertEqual(cases[0]["operation_review"]["verification_status"], "待验证")
            self.assertEqual(cases[0]["operation_review"]["viral_level"], "普通")
            self.assertEqual(cases[0]["operation_review"]["actual_metrics"]["likes"], "")
            self.assertEqual(cases[1]["cover"]["ocr_text"], "初二数学提分方法")
            self.assertTrue(cases[0]["id"].startswith("legacy-"))

    def test_cases_can_be_searched_and_filtered_by_four_dimensions(self) -> None:
        cases = [
            {
                "title": "初中数学暑假招生案例",
                "content": "面向家长的方法分享",
                "tags": ["招生"],
                "tag_dimensions": {
                    "subject": "数学",
                    "audience": "初中家长",
                    "content_type": "招生转化",
                    "scenario": "暑假招生",
                },
                "operation_review": {"verification_status": "已验证有效"},
            },
            {
                "title": "高中英语阅读方法",
                "content": "学习方法",
                "tags": [],
                "tag_dimensions": {
                    "subject": "英语",
                    "audience": "高中家长",
                    "content_type": "学习方法",
                    "scenario": "日常运营",
                },
            },
        ]

        matched = filter_viral_cases(
            cases,
            query="暑假",
            subject="数学",
            audience="初中家长",
            content_type="招生转化",
            verification_status="已验证有效",
        )

        self.assertEqual([case["title"] for case in matched], ["初中数学暑假招生案例"])

    def test_case_tags_can_be_updated_without_reanalysis(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "viral_case_library.json"
            saved = save_viral_case(path, {"title": "旧标签案例", "analysis": {"text": {"score": 80}}})

            updated = update_viral_case_tags(
                path,
                saved["id"],
                {
                    "subject": "数学",
                    "audience": "初中家长",
                    "content_type": "招生转化",
                    "scenario": "寒假招生",
                },
                ["数学", "招生"],
            )

            self.assertEqual(updated["tag_dimensions"]["scenario"], "寒假招生")
            self.assertEqual(updated["analysis"], {"text": {"score": 80}})
            self.assertEqual(load_viral_cases(path)[0]["tags"], ["数学", "招生"])

    def test_filter_matches_one_value_inside_multi_select_classification(self) -> None:
        cases = [
            {
                "title": "家长与学生案例",
                "tags": [],
                "tag_dimensions": {
                    "subject": "数学",
                    "audience": "家长、学生",
                    "content_type": "方法技巧",
                    "scenario": "考试节点、成绩提升",
                },
            }
        ]

        self.assertEqual(
            filter_viral_cases(cases, audience="家长", scenario="成绩提升"),
            cases,
        )

    def test_operation_review_can_be_updated_without_changing_analysis(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "viral_case_library.json"
            saved = save_viral_case(
                path,
                {"title": "初中数学案例", "analysis": {"text": {"score": 85}}},
            )

            updated = update_viral_case_operation(
                path,
                saved["id"],
                {
                    "platform": "小红书",
                    "original_url": "https://example.com/note",
                    "publish_date": "2026-07-01",
                    "source_account": "数学老师",
                },
                {
                    "save_reason": "家长痛点具体",
                    "verification_status": "已验证有效",
                    "viral_level": "爆款",
                    "actual_metrics": {"likes": "120", "favorites": 80, "comments": "12"},
                    "conversion": "收到3条咨询",
                    "notes": "晚间发布",
                },
            )

            self.assertEqual(updated["source_info"]["platform"], "小红书")
            self.assertEqual(updated["operation_review"]["actual_metrics"]["likes"], 120)
            self.assertEqual(updated["operation_review"]["verification_status"], "已验证有效")
            self.assertEqual(updated["operation_review"]["viral_level"], "爆款")
            self.assertEqual(updated["analysis"], {"text": {"score": 85}})
            self.assertEqual(load_viral_cases(path)[0]["operation_review"]["notes"], "晚间发布")

    def test_invalid_manual_metrics_and_status_fall_back_safely(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "viral_case_library.json"
            saved = save_viral_case(
                path,
                {
                    "title": "旧运营数据",
                    "operation_review": {
                        "verification_status": "未知状态",
                        "actual_metrics": {"likes": "not-a-number", "favorites": -3},
                    },
                },
            )

            self.assertEqual(saved["operation_review"]["verification_status"], "待验证")
            self.assertEqual(saved["operation_review"]["actual_metrics"]["likes"], "")
            self.assertEqual(saved["operation_review"]["actual_metrics"]["favorites"], 0)

    def test_case_delete_requires_an_existing_id(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "viral_case_library.json"
            first = save_viral_case(path, {"title": "保留案例"})
            second = save_viral_case(path, {"title": "删除案例"})

            self.assertFalse(delete_viral_case(path, "missing"))
            self.assertTrue(delete_viral_case(path, second["id"]))
            self.assertEqual([case["id"] for case in load_viral_cases(path)], [first["id"]])

    def test_case_list_deduplication_keeps_latest_without_changing_source_records(self) -> None:
        from app import deduplicate_viral_cases_for_display

        cases = [
            {
                "id": "old-id",
                "title": "旧链接记录",
                "created_at": "2026-07-01 10:00:00",
                "source_info": {"original_url": "https://example.com/note/1"},
            },
            {
                "id": "new-id",
                "title": "新链接记录",
                "created_at": "2026-07-03 10:00:00",
                "source_info": {"original_url": "https://example.com/note/1/"},
            },
            {
                "id": "same-id",
                "title": "旧ID记录",
                "created_at": "2026-07-01 12:00:00",
            },
            {
                "id": "same-id",
                "title": "新ID记录",
                "created_at": "2026-07-04 12:00:00",
            },
            {
                "id": "unique",
                "title": "独立案例",
                "created_at": "",
            },
        ]

        visible = deduplicate_viral_cases_for_display(cases)

        self.assertEqual(
            [case["title"] for case in visible],
            ["新ID记录", "新链接记录", "独立案例"],
        )
        self.assertEqual(len(cases), 5)

    def test_combined_analysis_counts_only_saved_case_structures(self) -> None:
        cases = []
        for index in range(3):
            cases.append(
                {
                    "id": f"case-{index}",
                    "title": f"初中数学案例 {index}",
                    "tag_dimensions": {
                        "subject": "数学",
                        "audience": "初中家长",
                        "content_type": "招生转化",
                        "scenario": "暑假招生",
                    },
                    "analysis": {
                        "text": {
                            "title_analysis": {
                                "target_audience": "初中家长",
                                "pain_point": "成绩下降",
                                "click_attraction": "获得解决方法",
                            },
                            "structure_analysis": {
                                "opening": "提出家长问题",
                                "middle": "解释原因并提供方法",
                                "ending": "邀请咨询",
                            },
                            "copyable_template": "很多家长发现……其实问题在于……可以这样解决……",
                        }
                    },
                    "model": {
                        "trust_building": "老师经验",
                        "reusable_title_formula": "孩子___怎么办？老师总结___个方法",
                    },
                    "cover_visual_analysis": {
                        "visual_focus": ["痛点标题"],
                        "color_analysis": {"contrast": "高明度差"},
                        "subject_position": {"position": "右侧"},
                        "information_layers": ["第一层：痛点", "第二层：方法"],
                    },
                }
            )

        analysis = build_combined_case_analysis(cases)

        self.assertEqual(analysis["source_count"], 3)
        self.assertEqual(analysis["title_patterns"][0]["count"], 3)
        self.assertEqual(analysis["pain_points"][0], {"value": "成绩下降", "count": 3})
        self.assertEqual(analysis["content_patterns"][0]["count"], 3)
        self.assertEqual(analysis["title_templates"][0]["count"], 3)
        self.assertIn("数学", analysis["suggested_applicability"])
        self.assertIn({"value": "第一视觉：痛点标题", "count": 3}, analysis["visual_patterns"])
        self.assertIn({"value": "主体位置：右侧", "count": 3}, analysis["visual_patterns"])

    def test_combined_analysis_requires_multiple_cases(self) -> None:
        with self.assertRaises(ValueError):
            build_combined_case_analysis([{"id": "only-one"}])

    def test_case_comparison_uses_saved_analysis_fields(self) -> None:
        cases = [
            {
                "id": "case-a",
                "title": "初二数学成绩上不去怎么办",
                "analysis": {
                    "text": {
                        "title_analysis": {"pain_point": "成绩上不去"},
                        "structure_analysis": {
                            "opening": "家长问题切入",
                            "middle": "原因与方法",
                            "ending": "评论交流",
                        },
                    },
                    "image": {
                        "first_glance": "成绩问题",
                        "information_hierarchy": "主标题居中",
                        "trust_building": "教师经验",
                        "conversion_elements": ["评论咨询"],
                    },
                },
                "model": {"title_structure": "痛点 + 人群 + 方法"},
            },
            {
                "id": "case-b",
                "title": "初二数学复盘方法",
                "analysis": {
                    "text": {
                        "title_analysis": {"pain_point": "成绩上不去"},
                        "structure_analysis": {
                            "opening": "案例切入",
                            "middle": "步骤拆解",
                            "ending": "收藏提醒",
                        },
                    },
                    "image": {
                        "first_glance": "复盘方法",
                        "layout_method": "上标题下步骤",
                        "trust_building": "真实作业",
                        "conversion_elements": "领取清单",
                    },
                },
                "model": {"title_structure": "问题 + 方法 + 结果"},
            },
        ]

        comparison = build_case_comparison(cases)

        self.assertEqual(comparison["case_ids"], ["case-a", "case-b"])
        self.assertEqual(len(comparison["title_rows"]), 2)
        self.assertEqual(comparison["common_pains"], [{"value": "成绩上不去", "count": 2}])
        self.assertEqual(comparison["cover_rows"][1]["核心文字位置"], "上标题下步骤")
        self.assertEqual(comparison["body_rows"][0]["中段展开方式"], "原因与方法")

    def test_case_comparison_requires_two_to_five_cases(self) -> None:
        with self.assertRaises(ValueError):
            build_case_comparison([{"id": "only-one"}])
        with self.assertRaises(ValueError):
            build_case_comparison([{"id": str(index)} for index in range(6)])

    def test_legacy_review_statuses_are_mapped_to_v18_statuses(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "viral_case_library.json"
            path.write_text(
                json.dumps(
                    [
                        {"id": "legacy-pending", "title": "旧待复盘", "operation_review": {"verification_status": "未验证"}},
                        {"id": "legacy-general", "title": "旧表现一般", "operation_review": {"verification_status": "表现一般"}},
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            cases = load_viral_cases(path)

            self.assertEqual(cases[0]["operation_review"]["verification_status"], "待验证")
            self.assertEqual(cases[1]["operation_review"]["verification_status"], "不推荐复用")

    def test_method_model_can_be_saved_and_reopened(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "viral_method_models.json"
            analysis = {
                "source_case_ids": ["case-1", "case-2"],
                "source_count": 2,
                "title_patterns": [{"value": "目标用户 + 具体问题", "count": 2}],
            }

            saved = save_method_model(
                path,
                {
                    "name": "初中数学招生模型",
                    "source_case_ids": analysis["source_case_ids"],
                    "applicability": "初中数学招生",
                    "core_structure": "痛点 + 专业身份 + 解决方案",
                    "analysis": analysis,
                },
            )

            self.assertEqual(saved["status"], "已沉淀模型")
            self.assertEqual(saved["source_count"], 2)
            self.assertEqual(load_method_models(path), [saved])


if __name__ == "__main__":
    unittest.main()
