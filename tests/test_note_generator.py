from io import BytesIO
from pathlib import Path
import unittest

from PIL import Image

from services.llm import (
    NOTE_GENERATION_PROMPT,
    NOTE_IMAGE_ANALYSIS_PROMPT,
    build_note_generation_payload,
    parse_note_image_analysis_response,
)
from services.note_generator import (
    GENERATION_MODES,
    IMAGE_GENERATION_STRUCTURE,
    build_image_source_context,
    build_generation_request_key,
    build_publish_version,
    build_rule_constraints,
    can_generate_note,
    finalize_generated_note,
    get_structure_guidance,
    truncate_complete_text,
)
from services.rule_checker import check_text, load_rules


RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "rules.json"


def generated_note(body: str = "数学基础薄弱时，可以先梳理解题步骤。") -> dict:
    return {
        "titles": [
            "孩子数学提分怎么办",
            "数学学习容易忽略什么",
            "三个数学学习方法",
            "老师分享数学学习观察",
            "陪娃学数学时的真实困扰",
        ],
        "body": body,
        "action": "可以结合实际学习情况逐步调整。",
        "tags": ["#数学", "#学习方法", "#家庭教育", "#学习规划", "#教育分享"],
    }


def make_image() -> bytes:
    output = BytesIO()
    Image.new("RGB", (1080, 1440), "white").save(output, format="PNG")
    return output.getvalue()


class NoteGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rules = load_rules(RULES_PATH)

    def test_body_never_exceeds_one_thousand_characters(self) -> None:
        note = generated_note("学习方法。" * 400)
        result = finalize_generated_note(note, self.rules, max_body_chars=1000)

        self.assertLessEqual(len(result["body"]), 1000)
        self.assertTrue(result["body"].endswith(("。", "！", "？", "!", "?")))

    def test_titles_and_body_are_both_reviewed(self) -> None:
        result = finalize_generated_note(
            generated_note("孩子数学提分需要保证有效。"),
            self.rules,
            max_body_chars=700,
        )
        scopes = {item["scope"] for item in result["risk_items"]}

        self.assertIn("标题", scopes)
        self.assertIn("正文", scopes)

    def test_risky_content_is_rewritten_and_reviewed_again(self) -> None:
        result = finalize_generated_note(
            generated_note("孩子数学提分，保证有效。"),
            self.rules,
            max_body_chars=700,
        )

        self.assertFalse(check_text("\n".join(result["titles"]), result["body"], self.rules))
        self.assertTrue(result["passed_second_review"])
        self.assertTrue(result["modifications"])

    def test_empty_profile_does_not_add_invented_experience(self) -> None:
        payload = build_note_generation_payload(
            "初二数学",
            creator_profile={},
            generation_options={},
            source_materials={"current_title": "数学学习"},
            risk_items=[],
        )

        self.assertEqual(payload["creator_profile"], {})
        self.assertNotIn("海淀一线教学12年", str(payload))
        self.assertIn("不得虚构", NOTE_GENERATION_PROMPT)

    def test_different_content_directions_have_different_structures(self) -> None:
        pain = get_structure_guidance("家长痛点型", "初二数学")
        course = get_structure_guidance("课程介绍型", "初二数学")
        sharing = get_structure_guidance("干货分享型", "初二数学")

        self.assertEqual(len({pain, course, sharing}), 3)

    def test_same_direction_does_not_have_one_fixed_opening_structure(self) -> None:
        variants = {
            get_structure_guidance("家长痛点型", f"素材{index}")
            for index in range(20)
        }

        self.assertGreater(len(variants), 1)
        self.assertIn("禁止固定使用", NOTE_GENERATION_PROMPT)

    def test_long_text_keeps_complete_opening_and_ending(self) -> None:
        original = "这是完整开头。" + "方法说明，" * 300 + "这是完整结尾。"
        shortened = truncate_complete_text(original, 500)

        self.assertTrue(shortened.startswith("这是完整开头。"))
        self.assertTrue(shortened.endswith(("。", "！", "？", "!", "?")))
        self.assertLessEqual(len(shortened), 500)

    def test_source_materials_keep_ocr_and_corrected_cover_text(self) -> None:
        source_materials = {
            "ocr_text": "数学学习方法",
            "corrected_cover_text": "初二数学函数学习方法",
            "has_cover_image": True,
        }
        payload = build_note_generation_payload(
            "函数怎么学",
            creator_profile={"name": "刘老师", "pricing": ""},
            generation_options={"content_direction": "干货分享型"},
            source_materials=source_materials,
            risk_items=[],
        )

        self.assertEqual(payload["source_materials"], source_materials)
        self.assertEqual(payload["creator_profile"], {"name": "刘老师"})

    def test_image_generation_keeps_cover_analysis_and_active_rule_constraints(self) -> None:
        cover_analysis = {"score": 82, "core_selling_point": "函数学习方法"}
        context = build_image_source_context(
            make_image(),
            ocr_text="初二函数怎么学",
            corrected_cover_text="",
            cover_analysis=cover_analysis,
        )
        constraints = build_rule_constraints(self.rules)
        context["rule_constraints"] = constraints
        payload = build_note_generation_payload(
            "初二函数",
            creator_profile={"name": "刘老师"},
            generation_options={"generation_mode": "根据图片生成"},
            source_materials={
                "ocr_text": context["ocr_text"],
                "cover_analysis": context["cover_analysis"],
                "rule_constraints": constraints,
            },
            risk_items=[],
        )

        self.assertEqual(context["cover_analysis"], cover_analysis)
        self.assertEqual(payload["source_materials"]["cover_analysis"], cover_analysis)
        self.assertTrue(payload["source_materials"]["rule_constraints"])
        self.assertTrue(
            all("term" in item and "severity" in item for item in constraints)
        )
        self.assertIn("rule_constraints", NOTE_GENERATION_PROMPT)
        self.assertIn("rule_constraints", NOTE_IMAGE_ANALYSIS_PROMPT)

    def test_image_only_mode_can_generate_from_confirmed_ocr(self) -> None:
        context = build_image_source_context(
            make_image(),
            ocr_text="初二数学函数怎么学",
            corrected_cover_text="",
        )

        allowed, error = can_generate_note(
            "根据图片生成",
            topic="",
            title="",
            body="",
            image_context=context,
        )

        self.assertTrue(allowed)
        self.assertEqual(error, "")
        self.assertEqual(context["width"], 1080)
        self.assertEqual(context["height"], 1440)
        self.assertEqual(context["confirmed_cover_text"], "初二数学函数怎么学")
        self.assertEqual(GENERATION_MODES[0], "根据图片生成")

    def test_image_mode_requires_image_and_confirmed_text(self) -> None:
        missing_image = can_generate_note("根据图片生成", "", "", "", {})
        no_text_context = build_image_source_context(make_image(), "", "")
        missing_text = can_generate_note(
            "根据图片生成", "", "", "", no_text_context
        )

        self.assertFalse(missing_image[0])
        self.assertIn("上传", missing_image[1])
        self.assertFalse(missing_text[0])
        self.assertIn("手动补充", missing_text[1])

    def test_image_analysis_parser_and_prompt_do_not_invent_visual_facts(self) -> None:
        parsed = parse_note_image_analysis_response(
            '{"cover_theme":"函数学习","visual_elements":["封面主标题"],'
            '"target_audience":"初二家长","selling_direction":"学习方法",'
            '"content_type":"干货分享","analysis_basis":"基于OCR"}'
        )

        self.assertEqual(parsed["cover_theme"], "函数学习")
        self.assertIn("不得虚构人物", NOTE_IMAGE_ANALYSIS_PROMPT)
        self.assertIn("用户痛点", IMAGE_GENERATION_STRUCTURE)

    def test_image_generation_payload_only_uses_saved_profile_fields(self) -> None:
        image_analysis = {
            "cover_theme": "函数学习",
            "target_audience": "初二家长",
        }
        payload = build_note_generation_payload(
            "",
            creator_profile={"name": "刘老师", "unknown_claim": "带过万名学员"},
            generation_options={"generation_mode": "根据图片生成"},
            source_materials={"image_analysis": image_analysis},
            risk_items=[],
        )

        self.assertEqual(payload["creator_profile"], {"name": "刘老师"})
        self.assertEqual(payload["source_materials"]["image_analysis"], image_analysis)
        self.assertIn("成绩保证", NOTE_GENERATION_PROMPT)

    def test_publish_version_format_is_title_body_and_tags(self) -> None:
        published = build_publish_version(
            "标题",
            "正文",
            "行动引导",
            ["#数学", "#学习方法"],
        )

        self.assertEqual(published, "标题\n\n正文\n\n行动引导\n\n#数学 #学习方法")

    def test_request_key_is_stable_across_normal_reruns(self) -> None:
        payload = {
            "topic": "初二数学",
            "direction": "干货分享型",
            "source": {"ocr_text": "函数学习"},
        }

        self.assertEqual(
            build_generation_request_key(payload),
            build_generation_request_key(dict(payload)),
        )


if __name__ == "__main__":
    unittest.main()
