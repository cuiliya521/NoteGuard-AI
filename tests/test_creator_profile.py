import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from services import history
from services.creator_profile import (
    build_creator_profile_context,
    empty_creator_profile,
    load_creator_profile,
    save_creator_profile,
)


class CreatorProfileTests(unittest.TestCase):
    def test_missing_creator_profile_creates_blank_template(self) -> None:
        with TemporaryDirectory() as directory:
            profile_path = Path(directory) / "data" / "creator_profile.json"
            profile = load_creator_profile(profile_path)

            self.assertTrue(profile_path.exists())
            self.assertEqual(profile, empty_creator_profile())

    def test_creator_context_only_contains_saved_fields(self) -> None:
        with TemporaryDirectory() as directory:
            profile_path = Path(directory) / "creator_profile.json"
            save_creator_profile(
                profile_path,
                {
                    "name": "测试老师",
                    "subjects": "数学",
                    "pricing": "",
                    "unknown_field": "不得保存",
                },
            )

            context = build_creator_profile_context(load_creator_profile(profile_path))
            self.assertEqual(context, {"name": "测试老师", "subjects": "数学"})
            self.assertNotIn("unknown_field", context)
            self.assertNotIn("pricing", context)

    def test_corrupt_profile_and_history_files_fall_back_to_empty(self) -> None:
        with TemporaryDirectory() as directory:
            profile_path = Path(directory) / "creator_profile.json"
            profile_path.write_text("{bad", encoding="utf-8")
            self.assertEqual(load_creator_profile(profile_path), empty_creator_profile())

            history_path = Path(directory) / "history.json"
            with patch.object(history, "HISTORY_PATH", history_path):
                self.assertEqual(history.load_history(), [])
                history_path.write_text(json.dumps({"invalid": True}), encoding="utf-8")
                self.assertEqual(history.load_history(), [])
