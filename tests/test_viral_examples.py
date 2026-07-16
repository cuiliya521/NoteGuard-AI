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
                [{"title": "初二数学怎么学", "content": "方法分享"}],
            )

    def test_corrupt_file_degrades_to_empty_examples(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "viral_examples.json"
            path.write_text("not json", encoding="utf-8")

            self.assertEqual(load_viral_examples(path), [])


if __name__ == "__main__":
    unittest.main()
