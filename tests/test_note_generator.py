from pathlib import Path
import unittest

from services.llm import NOTE_GENERATION_PROMPT, build_note_generation_payload
from services.note_generator import (
    build_generation_request_key,
    build_publish_version,
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
