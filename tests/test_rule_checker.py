import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from services.rule_checker import (
    add_rule_record,
    check_text,
    delete_rule_record,
    load_rule_records,
    load_rules,
    update_rule_record,
)


RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "rules.json"


class RuleCheckerTests(unittest.TestCase):
    def test_public_rules_keep_generic_education_risk_detection(self) -> None:
        records = load_rule_records(RULES_PATH)
        terms = {record["term"] for record in records}

        self.assertIn("保证提分", terms)
        self.assertIn("100%有效", terms)
        self.assertIn("差生", terms)
        self.assertTrue(
            {"效果承诺", "绝对化表达", "权威背书", "人群表达"}
            <= {record["category"] for record in records}
        )
        self.assertTrue(all("Demo" not in record["term"] for record in records))

    def test_rule_add_disable_and_delete(self) -> None:
        with TemporaryDirectory() as directory:
            rule_path = Path(directory) / "data" / "rules.json"
            record = {
                "term": "测试承诺",
                "category": "测试",
                "reason": "用于验证规则管理流程",
                "suggestion": "测试表达",
                "severity": "high",
                "enabled": True,
            }

            add_rule_record(rule_path, record)
            self.assertTrue(check_text("测试承诺", "", load_rules(rule_path)))

            update_rule_record(rule_path, "测试承诺", {**record, "enabled": False})
            self.assertFalse(check_text("测试承诺", "", load_rules(rule_path)))

            delete_rule_record(rule_path, "测试承诺")
            self.assertEqual(load_rule_records(rule_path), [])

    def test_missing_empty_and_corrupt_rule_files_do_not_raise(self) -> None:
        with TemporaryDirectory() as directory:
            rule_path = Path(directory) / "data" / "rules.json"
            self.assertEqual(load_rules(rule_path), [])
            self.assertTrue(rule_path.exists())

            rule_path.write_text("", encoding="utf-8")
            self.assertEqual(load_rules(rule_path), [])

            rule_path.write_text(json.dumps({"invalid": True}), encoding="utf-8")
            self.assertEqual(load_rules(rule_path), [])
