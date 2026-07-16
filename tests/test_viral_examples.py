from pathlib import Path
from tempfile import TemporaryDirectory
import json
import re
import unittest

from services.viral_examples import load_viral_examples


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


if __name__ == "__main__":
    unittest.main()
