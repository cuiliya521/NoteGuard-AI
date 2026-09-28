import unittest

from services.rule_checker import Rule
from services.workflow_v2 import (
    Draft, SemanticIssue, SemanticReview, decide_workflow, start_workflow,
)


RULES = [Rule("效果承诺", "保证提分", "确定性承诺", "提供学习支持", "high"),
         Rule("普通教育表达", "1v1", "需结合上下文", "", "low")]
CLEAR = lambda title, body: SemanticReview(available=True)


class WorkflowV2Tests(unittest.TestCase):
    def test_obvious_risk_accept_then_clean_recheck(self):
        calls = []
        def reviewer(title, body):
            calls.append((title, body))
            return CLEAR(title, body)
        state = start_workflow("保证提分", "数学陪练", RULES, reviewer,
                               lambda *args: Draft("学习支持", "数学陪练", "移除承诺", "test"))
        self.assertEqual(state.path, "needs_decision")
        self.assertEqual(len(calls), 1)
        final = decide_workflow(state, "accept", reviewer)
        self.assertEqual(final.path, "accepted")
        self.assertEqual(final.final_findings, ())
        self.assertEqual(len(calls), 2)
        self.assertEqual(final.original_title, "保证提分")

    def test_clean_content_skips_draft(self):
        def should_not_make_draft(*args):
            self.fail("No-risk path should not make a draft")
        state = start_workflow("初二数学复盘", "整理错题", RULES, CLEAR, should_not_make_draft)
        self.assertEqual(state.path, "clear")
        self.assertEqual(state.final_title, state.original_title)

    def test_low_rule_hit_but_semantics_normal_remains_explainable(self):
        state = start_workflow("1v1 数学陪练", "交流学习方法", RULES, CLEAR,
                               lambda *args: Draft("数学陪练", "交流学习方法", "规则替代", "test"))
        self.assertEqual(state.path, "needs_decision")
        self.assertEqual(len(state.original_findings), 1)
        self.assertFalse(state.semantic.issues)
        self.assertEqual(state.original_findings[0].severity, "low")

    def test_reject_preserves_original_and_risk(self):
        state = start_workflow("保证提分", "原文", RULES, CLEAR,
                               lambda *args: Draft("学习支持", "原文", "建议", "test"))
        final = decide_workflow(state, "reject", CLEAR)
        self.assertEqual(final.final_title, "保证提分")
        self.assertTrue(final.final_findings)
        self.assertEqual(final.path, "rejected")

    def test_recheck_still_has_risk(self):
        state = start_workflow("保证提分", "原文", RULES, CLEAR,
                               lambda *args: Draft("继续保证提分", "原文", "不充分的改写", "test"))
        final = decide_workflow(state, "accept", CLEAR)
        self.assertTrue(final.final_findings)
        self.assertIn("尚未完全通过", final.decision_reason)

    def test_semantic_only_issue_and_candidate(self):
        def reviewer(title, body):
            issues = (SemanticIssue("正文", "内部数据", "未经证实的引用", "medium"),) if "内部数据" in body else ()
            return SemanticReview(issues, available=True)
        state = start_workflow("学习方法", "据内部数据，效果很好", RULES, reviewer,
                               lambda *args: Draft("学习方法", "分享错题整理方法", "移除未经证实的数据", "test"))
        self.assertEqual(state.path, "needs_decision")
        final = decide_workflow(state, "accept", reviewer)
        self.assertEqual(final.final_semantic.issues, ())

    def test_llm_exception_and_unavailable_draft_do_not_fake_pass(self):
        def broken(*args):
            raise ConnectionError("API unavailable")
        no_risk = start_workflow("学习方法", "错题整理", RULES, broken, broken)
        self.assertEqual(no_risk.path, "clear")
        self.assertIn("不能视为全面通过", no_risk.decision_reason)
        risk = start_workflow("保证提分", "正文", RULES, broken, broken)
        self.assertEqual(risk.path, "suggestion_unavailable")
        self.assertTrue(risk.original_findings)
        self.assertFalse(risk.semantic.available)

    def test_recheck_llm_unavailable_is_not_full_pass(self):
        state = start_workflow("保证提分", "正文", RULES, CLEAR,
                               lambda *args: Draft("学习支持", "正文", "移除承诺", "test"))
        final = decide_workflow(state, "accept", lambda *args: SemanticReview(error="API unavailable"))
        self.assertIn("不能标记为全面通过", final.decision_reason)

    def test_blank_input_and_double_decision_rejected(self):
        with self.assertRaises(ValueError):
            start_workflow("", " ", RULES, CLEAR, lambda *args: None)
        state = start_workflow("保证提分", "正文", RULES, CLEAR,
                               lambda *args: Draft("学习支持", "正文", "建议", "test"))
        final = decide_workflow(state, "reject", CLEAR)
        with self.assertRaises(ValueError):
            decide_workflow(final, "accept", CLEAR)


if __name__ == "__main__":
    unittest.main()
