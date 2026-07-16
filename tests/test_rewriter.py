from pathlib import Path
import unittest

from unittest.mock import patch

from services.rewriter import (
    build_format_preserving_changes,
    build_line_review_items,
    build_supplier_feedback,
    get_line_review_progress,
    review_title_candidates,
    rewrite_all,
    rewrite_with_local_rules,
)
from services.rule_checker import check_text, load_rules


RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "rules.json"


class TitleRewriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rules = load_rules(RULES_PATH)

    def test_math_thinking_phrase_is_rewritten_once(self) -> None:
        review = review_title_candidates(
            ["孩子数学思维跟不上，线上1v1辅导真的有效吗？"],
            self.rules,
        )[0]

        self.assertEqual(
            review.safe_title,
            "娃数理思维跟不上，线上1v1辅导真的有效吗？",
        )
        self.assertNotIn("数理思维思维", review.safe_title)

    def test_math_without_thinking_still_uses_subject_replacement(self) -> None:
        review = review_title_candidates(["孩子数学基础薄弱"], self.rules)[0]

        self.assertEqual(review.safe_title, "娃数理思维基础薄弱")

    def test_generated_title_is_rechecked_after_local_safety_rewrite(self) -> None:
        review = review_title_candidates(["数学差生逆袭秘籍！30天提高50分"], self.rules)[0]

        self.assertEqual(review.status, "安全")
        self.assertFalse(check_text(review.safe_title, "", self.rules))

    def test_each_finding_gets_an_independent_review_item(self) -> None:
        title = "孩子数学提分怎么办"
        findings = check_text(title, "", self.rules)
        items = build_line_review_items(title, "", findings)

        self.assertEqual(len(items), len(findings))
        self.assertTrue(all(item.original_text for item in items))
        self.assertTrue(all(item.replacement_text for item in items))

    def test_minimal_rewrite_keeps_normal_sentence_unchanged(self) -> None:
        body = "正常句子保持不变。\n孩子数学基础薄弱。"
        findings = check_text("", body, self.rules)
        result = rewrite_with_local_rules("", body, findings)

        self.assertEqual(result.body, "正常句子保持不变。\n娃数理思维基础薄弱。")

    def test_supplier_feedback_format(self) -> None:
        title = "孩子数学基础薄弱"
        items = build_line_review_items(
            title,
            "",
            check_text(title, "", self.rules),
        )
        feedback = build_supplier_feedback(items)

        self.assertIn("问题1：", feedback)
        self.assertIn("原句：", feedback)
        self.assertIn("问题：", feedback)
        self.assertIn("建议修改为：", feedback)

    def test_review_progress_counts_handled_items(self) -> None:
        title = "孩子数学基础薄弱"
        items = build_line_review_items(
            title,
            "",
            check_text(title, "", self.rules),
        )
        statuses = {item.item_id: "pending" for item in items}
        statuses[items[0].item_id] = "handled"

        self.assertEqual(
            get_line_review_progress(items, statuses),
            (len(items), 1, len(items) - 1),
        )

    def test_complete_safe_version_preserves_lines_emoji_and_tag(self) -> None:
        body = "第一行✨！！\n孩子数学基础薄弱\n#数学学习"
        findings = check_text("", body, self.rules)
        result = rewrite_with_local_rules("", body, findings)

        self.assertEqual(
            result.body,
            "第一行✨！！\n娃数理思维基础薄弱\n#数理思维学习",
        )

    @patch("services.rewriter.rewrite_content")
    def test_ai_rewrite_cannot_rewrite_normal_lines(self, rewrite_content) -> None:
        body = "老师介绍👩‍🏫\n孩子数学基础薄弱\n#数学学习"
        findings = check_text("", body, self.rules)
        rewrite_content.return_value = {
            "title": "",
            "body": "全新开头\n全篇重写\n全新标签",
            "reason": "整体优化",
        }

        result = rewrite_all("", body, findings)

        self.assertEqual(
            result.body,
            "老师介绍👩‍🏫\n娃数理思维基础薄弱\n#数理思维学习",
        )

    @patch("services.rewriter.rewrite_content")
    def test_ai_rewrite_preserves_original_newlines_and_tags(self, rewrite_content) -> None:
        body = "孩子数学基础薄弱\n\n线上1v1陪练✨\n#数学学习"
        findings = check_text("", body, self.rules)
        rewrite_content.return_value = {
            "title": "",
            "body": "娃数理思维基础薄弱\n\n线上1v1陪练✨\n#数理思维学习",
            "reason": "最小修改",
        }

        result = rewrite_all("", body, findings)

        self.assertEqual(result.body.count("\n"), body.count("\n"))
        self.assertIn("线上1v1陪练✨", result.body)
        self.assertTrue(result.body.endswith("#数理思维学习"))

    def test_format_preserving_changes_show_actual_line_locations(self) -> None:
        changes = build_format_preserving_changes(
            "孩子数学",
            "正常行\n孩子数学基础薄弱",
            "娃数理思维",
            "正常行\n娃数理思维基础薄弱",
        )

        self.assertEqual([item.location for item in changes], ["标题", "正文 · 第 2 行"])
        self.assertEqual(changes[1].original, "孩子数学基础薄弱")
        self.assertEqual(changes[1].replacement, "娃数理思维基础薄弱")

    def test_line_review_generation_does_not_write_external_files(self) -> None:
        title = "孩子数学基础薄弱"
        findings = check_text(title, "", self.rules)
        with patch("pathlib.Path.write_text") as write_text:
            build_line_review_items(title, "", findings)

        write_text.assert_not_called()


if __name__ == "__main__":
    unittest.main()
