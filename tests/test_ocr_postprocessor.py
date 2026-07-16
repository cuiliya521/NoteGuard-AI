import unittest

from services.ocr_postprocessor import correct_ocr_text


class OcrPostprocessorTests(unittest.TestCase):
    def test_common_education_terms_are_corrected_at_high_confidence(self) -> None:
        result = correct_ocr_text(
            "思维训炼\n数理思唯",
            confidence=90,
        )

        self.assertEqual(result.optimized_text, "思维训练\n数理思维")
        self.assertEqual(result.original_text, "思维训炼\n数理思唯")
        self.assertFalse(result.requires_confirmation)

    def test_creator_profile_terms_can_correct_one_character_variant(self) -> None:
        result = correct_ocr_text(
            "某地一线教字",
            creator_profile={"personal_experience": "某地一线教学"},
            confidence=88,
        )

        self.assertEqual(result.optimized_text, "某地一线教学")

    def test_low_confidence_keeps_original_text_for_confirmation(self) -> None:
        result = correct_ocr_text("思维训炼", confidence=40)

        self.assertEqual(result.optimized_text, "思维训炼")
        self.assertTrue(result.requires_confirmation)
        self.assertEqual(result.changes, ())


if __name__ == "__main__":
    unittest.main()
