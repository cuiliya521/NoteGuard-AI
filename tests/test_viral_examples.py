from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from services.viral_examples import load_viral_examples


class ViralExamplesTests(unittest.TestCase):
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
