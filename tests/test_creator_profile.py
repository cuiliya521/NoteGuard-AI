import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from services import history
from services.creator_profile import (
    PROFILE_FIELDS,
    build_creator_profile_context,
    empty_creator_profile,
    load_creator_profile,
    save_creator_profile,
)


class CreatorProfileTests(unittest.TestCase):
    def test_public_demo_profile_keeps_complete_field_structure(self) -> None:
        demo_path = Path(__file__).resolve().parents[1] / "data" / "creator_profile.demo.json"
        demo_profile = json.loads(demo_path.read_text(encoding="utf-8"))

        self.assertEqual(set(demo_profile), set(PROFILE_FIELDS))
        self.assertTrue(all(str(demo_profile[field]).strip() for field in PROFILE_FIELDS))
        self.assertIn("公开Demo", demo_profile["name"])

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

    def test_blank_local_profile_uses_public_demo_fallback(self) -> None:
        with TemporaryDirectory() as directory:
            profile_path = Path(directory) / "creator_profile.json"
            demo_path = Path(directory) / "creator_profile.demo.json"
            demo_profile = {
                field: f"Demo {field}"
                for field in empty_creator_profile()
            }
            demo_path.write_text(
                json.dumps(demo_profile, ensure_ascii=False),
                encoding="utf-8",
            )

            profile = load_creator_profile(profile_path, fallback_path=demo_path)

            self.assertEqual(profile, demo_profile)

    def test_saved_local_profile_takes_priority_over_demo(self) -> None:
        with TemporaryDirectory() as directory:
            profile_path = Path(directory) / "creator_profile.json"
            demo_path = Path(directory) / "creator_profile.demo.json"
            save_creator_profile(profile_path, {"name": "用户已保存老师"})
            save_creator_profile(demo_path, {"name": "Demo老师"})

            profile = load_creator_profile(profile_path, fallback_path=demo_path)

            self.assertEqual(profile["name"], "用户已保存老师")

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

    def test_history_record_contains_line_review_without_external_document(self) -> None:
        record = history.create_history_record(
            record_id="review-1",
            title="测试标题",
            body="测试正文",
            safety_score=80,
            risk_level="中风险",
            risk_items=[{"风险词": "测试"}],
            rewritten_title="安全标题",
            rewritten_body="安全正文",
            line_review_items=[{"item_id": "item-1", "original_text": "测试正文"}],
            line_review_statuses={"item-1": "handled"},
        )

        self.assertEqual(record["risk_count"], 1)
        self.assertEqual(record["line_review_statuses"], {"item-1": "handled"})
        self.assertNotIn("external_document", record)
