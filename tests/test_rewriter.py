from pathlib import Path
import unittest

from services.rewriter import review_title_candidates
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


if __name__ == "__main__":
    unittest.main()
