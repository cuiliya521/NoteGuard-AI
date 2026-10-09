"""Adapter regressions with real V2 rules; semantic doubles are NOT online acceptance."""
import json
from pathlib import Path
import pytest
from services.forest_paper_v2 import Workspace, WorkspaceRegistry
from services.rule_checker import load_rules
from services.workflow_v2 import Draft, SemanticReview, SemanticIssue

TITLE = "30天保证提分50分！初二数学必看"
BODY = "初二数学线上1v1陪练，保证每位学员一个月提高50分。\n我们会结合错题复盘学习方法。"
DRAFT = {"title": "初二数学必看", "body": "初二数学线上1v1陪练。\n我们会结合错题复盘学习方法。"}


def reviewer(title, body):
    # A semantic test double; rule checking always executes the actual V2 engine.
    return SemanticReview((SemanticIssue("正文", "保证", "测试语义承诺", "high"),) if "保证" in body else (), True)


@pytest.fixture
def work():
    rules = load_rules(Path(__file__).resolve().parents[1] / "data/rules.json")
    return Workspace(rules, reviewer, lambda *a: Draft(**DRAFT, source="TEST_DOUBLE", reason="test"))


def event(work, action, doc=None, eid=None, version=None):
    value = {"id": eid or f"{action}-{work.version}", "version": work.version if version is None else version,
             "action": action}
    if doc is not None:
        value["document"] = doc
    return value


def audit(work):
    return work.handle(event(work, "audit", {"title": TITLE, "body": BODY}))


def test_original_real_rules_and_independent_draft(work):
    value = audit(work)
    assert value["original"]["body"] == BODY
    assert value["original_review"]["rules"]
    assert value["draft"]["body"] == DRAFT["body"]
    assert value["final"] is None
    assert value["draft_diff"]


def test_reject_preserves_risks(work):
    before = audit(work)
    after = work.handle(event(work, "reject"))
    assert after["path"] == "rejected"
    assert before["original_review"] == after["original_review"]
    assert after["final"] is None


@pytest.mark.parametrize("action", ["accept", "edit_accept"])
def test_adopt_checks_exact_whole_candidate(work, action):
    audit(work)
    candidate = {**DRAFT, "body": DRAFT["body"] + "保证一个月提高50分。"}
    after = work.handle(event(work, action, candidate))
    expected = DRAFT if action == "accept" else candidate
    assert after["final"] == expected
    assert after["final_review"]["revision"] == after["final_revision"]
    assert after["draft"]["body"] == DRAFT["body"]  # never overwrite AI candidate
    assert after["original"]["body"] == BODY
    if action == "edit_accept":
        assert after["final_review"]["rules"]
    else:
        assert after["final_review"]["message"] == "未发现明显风险"


def test_cancel_edit_keeps_valid_recheck(work):
    audit(work)
    adopted = work.handle(event(work, "accept"))
    unchanged = work.handle(event(work, "cancel_edit", {"title": "unsaved", "body": "unsaved"}))
    assert unchanged == adopted


def test_save_unchanged_final_keeps_result(work):
    audit(work)
    adopted = work.handle(event(work, "accept"))
    value = work.handle(event(work, "save_final", dict(DRAFT)))
    assert value["final_review"] == adopted["final_review"]
    assert value["final_revision"] == adopted["final_revision"]


def test_change_final_invalidates_old_review_and_repeated_rechecks(work):
    audit(work)
    work.handle(event(work, "accept"))
    for body, risky in [(DRAFT["body"] + "保证一个月提高50分。", True), (DRAFT["body"], False)] * 2:
        pending = work.handle(event(work, "save_final", {**DRAFT, "body": body}))
        assert pending["final_review"] is None and pending["final_status"] == "pending"
        checked = work.handle(event(work, "recheck"))
        assert bool(checked["final_review"]["rules"]) == risky
        assert checked["final_review"]["revision"] == checked["final_revision"]
        assert checked["original"]["body"] == BODY
        assert checked["draft"]["body"] == DRAFT["body"]


def test_semantic_failure_does_not_pass_then_retry(work):
    audit(work)
    work.reviewer = lambda *a: SemanticReview(error="TimeoutError: secret request detail")
    value = work.handle(event(work, "accept"))
    assert value["final_status"] == "failed"
    assert value["final_review"]["semantic_available"] is False
    assert "未发现明显风险" not in value["final_review"]["message"]
    assert "secret request detail" not in json.dumps(value)
    work.reviewer = reviewer
    assert work.handle(event(work, "recheck"))["final_status"] == "completed"


def test_duplicate_submit_calls_engine_once(work):
    count = []
    work.reviewer = lambda *a: (count.append(1) or reviewer(*a))
    value = event(work, "audit", {"title": TITLE, "body": BODY})
    work.handle(value)
    work.handle(value)
    assert len(count) == 1


def test_old_version_cannot_replace_new_result(work):
    audit(work)
    stale = event(work, "accept")
    work.handle(event(work, "reject"))
    with pytest.raises(ValueError, match="版本已变化"):
        work.handle(stale)
    assert work.state.path == "rejected"


@pytest.mark.parametrize("action", ["audit", "edit_accept", "save_final"])
def test_empty_body_blocked_without_state_loss(work, action):
    if action != "audit":
        audit(work)
    if action == "save_final":
        work.handle(event(work, "accept"))
    before = work.snapshot()
    with pytest.raises(ValueError, match="正文不能为空"):
        work.handle(event(work, action, {"title": "title", "body": " \n "}))
    assert work.snapshot() == before


def test_refresh_restores_server_results_not_browser_submitted_results(work):
    registry = WorkspaceRegistry()
    registry.items[work.token] = work
    audit(work)
    work.handle(event(work, "accept"))
    restored, found = registry.acquire(work.token, work.rules)
    assert found and restored.snapshot() == work.snapshot()
    expired, found = WorkspaceRegistry(ttl=-1).acquire(work.token, work.rules)
    assert not found and expired.state is None


def test_source_and_failures_are_explicit(work):
    work.reviewer = lambda *a: SemanticReview(error="provider response containing credentials")
    work.drafter = lambda *a: Draft(**DRAFT, source="本地规则", reason="fallback", error="SECRET")
    value = audit(work)
    assert value["original_review"]["status"] == "partial_failure"
    assert value["draft"]["source"] == "本地规则"
    assert "SECRET" not in json.dumps(value)


def test_streamlit_entry_loads_without_exception():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file("experiments/v2_forest_paper/app.py").run(timeout=20)
    assert not app.exception
    assert any("noteguard_forest_paper_v2" in str(e.proto) for e in app.get("component_instance"))
