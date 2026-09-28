import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from services.workflow_ai_v2 import make_draft
from services.workflow_v2 import Draft, SemanticReview, decide_workflow, start_workflow
from services.rule_checker import Rule


RULES = [Rule("效果承诺", "保证提分", "确定性承诺", "学习支持", "high")]
CLEAR = lambda title, body: SemanticReview(available=True)


class WorkflowRegressionTests(unittest.TestCase):
    def test_rule_replacements_are_not_sent_as_business_facts(self):
        with patch("services.workflow_ai_v2._complete", return_value={
            "title": "初二数学", "body": "", "reason": "删除承诺，正文需运营确认事实后补充。",
        }) as complete:
            state = start_workflow("初二数学保证提分", "30天保证提分50分，十万家庭验证有效",
                                   RULES, CLEAR, make_draft)
        payload = complete.call_args.args[1]
        self.assertTrue(payload["rule_findings"])
        self.assertTrue(all("suggestion" not in item for item in payload["rule_findings"]))
        self.assertEqual(state.suggestion.title, "初二数学")
        self.assertEqual(state.suggestion.body, "")
        with self.assertRaisesRegex(ValueError, "确认版正文为空"):
            decide_workflow(state, "accept", CLEAR)
        self.assertEqual(state.path, "needs_decision")

    def test_candidate_cannot_drop_a_field_that_was_present_in_original(self):
        state = start_workflow("保证提分", "原文正文", RULES, CLEAR,
                               lambda *args: Draft("学习支持", "建议正文", "原始理由", "LLM"))
        for incomplete in (Draft("学习支持", "", "", "LLM"),
                           Draft("", "建议正文", "", "LLM")):
            with self.subTest(incomplete=incomplete):
                with self.assertRaises(ValueError):
                    decide_workflow(state, "accept", CLEAR, confirmed_draft=incomplete)
        self.assertEqual(state.path, "needs_decision")

    def test_user_confirmed_text_rechecks_without_relabeling_ai_reason(self):
        state = start_workflow("保证提分", "正文", RULES, CLEAR,
                               lambda *args: Draft("学习支持", "正文", "已删除保证提分", "LLM"))
        final = decide_workflow(state, "accept", CLEAR,
                                confirmed_draft=Draft("继续保证提分", "正文", "已删除保证提分", "LLM"))
        self.assertEqual(state.suggestion.title, "学习支持")
        self.assertEqual(final.suggestion.title, "学习支持")
        self.assertEqual(final.final_title, "继续保证提分")
        self.assertTrue(final.final_findings)
        self.assertIn("尚未完全通过", final.decision_reason)

    def test_model_outcome_deadline_does_not_become_service_duration(self):
        with patch("services.workflow_ai_v2._complete", return_value={
            "title": "30天学习支持", "body": "提供一个月针对性学习支持。",
            "reason": "保留30天真实卖点，未虚构事实或结果。",
        }):
            draft = make_draft("30天保证提分", "一个月后提高50分。", (), ())
        self.assertNotIn("30天", draft.title)
        self.assertNotIn("一个月", draft.body)
        self.assertNotIn("未虚构事实", draft.reason)
        self.assertIn("不能据此推断服务周期", draft.reason)

    def test_explicit_service_duration_is_retained(self):
        with patch("services.workflow_ai_v2._complete", return_value={
            "title": "30天学习支持", "body": "课程为期30天，提供学习支持。", "reason": "删除承诺",
        }):
            draft = make_draft("30天课程，保证提分", "课程为期30天。", (), ())
        self.assertIn("30天", draft.title)
        self.assertIn("30天", draft.body)

    def test_navigation_preserves_pending_fields_and_changed_input_invalidates(self):
        app = AppTest.from_file("app.py").run(timeout=30)
        app.radio(key="workspace_page").set_value("协作审核 V2").run(timeout=30)
        app.text_input(key="v2_title").set_value("保证提分").run(timeout=30)
        app.text_area(key="v2_body").set_value("原文正文").run(timeout=30)
        with patch("services.workflow_ui_v2.review_semantics", CLEAR), patch(
            "services.workflow_ui_v2.make_draft",
            return_value=Draft("学习支持", "建议正文", "AI 原始理由", "LLM"),
        ):
            app.button(key="v2_start").click().run(timeout=30)
        self.assertEqual(app.session_state["v2_state"].path, "needs_decision")
        app.radio(key="workspace_page").set_value("内容审核中心").run(timeout=30)
        app.radio(key="workspace_page").set_value("协作审核 V2").run(timeout=30)
        self.assertEqual(app.text_input(key="v2_title").value, "保证提分")
        self.assertEqual(app.text_area(key="v2_body").value, "原文正文")
        self.assertEqual(app.text_input(key="v2_candidate_title").value, "学习支持")
        self.assertEqual(app.text_area(key="v2_candidate_body").value, "建议正文")
        app.text_area(key="v2_candidate_body").set_value("").run(timeout=30)
        app.button(key="v2_accept").click().run(timeout=30)
        self.assertEqual(app.session_state["v2_state"].path, "needs_decision")
        self.assertTrue(any("确认版正文为空" in error.value for error in app.error))
        app.text_input(key="v2_title").set_value("新的标题").run(timeout=30)
        self.assertNotIn("v2_state", app.session_state)
        self.assertFalse(any("规则与语义检查均未发现明显问题" in x.value for x in app.success))
        self.assertEqual(len(app.exception), 0)


if __name__ == "__main__":
    unittest.main()
