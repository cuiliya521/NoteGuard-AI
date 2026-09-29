"""V2 review workflow. No persistence; human approval is required before recheck."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from services.rule_checker import Finding, Rule, check_text


@dataclass(frozen=True)
class SemanticIssue:
    location: str
    excerpt: str
    reason: str
    severity: str


@dataclass(frozen=True)
class SemanticReview:
    issues: tuple[SemanticIssue, ...] = ()
    available: bool = False
    error: str = ""


@dataclass(frozen=True)
class Draft:
    title: str
    body: str
    reason: str
    source: str
    error: str = ""
    confirmation_items: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowState:
    original_title: str
    original_body: str
    rules: tuple[Rule, ...]
    original_findings: tuple[Finding, ...]
    semantic: SemanticReview
    path: str  # clear, needs_decision, suggestion_unavailable, rejected, accepted
    decision_reason: str
    suggestion: Draft | None = None
    final_title: str = ""
    final_body: str = ""
    final_findings: tuple[Finding, ...] = ()
    final_semantic: SemanticReview | None = None


SemanticReviewer = Callable[[str, str], SemanticReview]
DraftMaker = Callable[[str, str, tuple[Finding, ...], tuple[SemanticIssue, ...]], Draft | None]


def start_workflow(
    title: str, body: str, rules: list[Rule],
    semantic_reviewer: SemanticReviewer, draft_maker: DraftMaker,
) -> WorkflowState:
    if not (title.strip() or body.strip()):
        raise ValueError("请先输入标题或正文。")
    findings = tuple(check_text(title, body, rules))
    semantic = _review_semantics(semantic_reviewer, title, body)
    needs_change = bool(findings or semantic.issues)
    if not needs_change:
        reason = "规则未命中；语义检查未发现明显问题，保留原文。" if semantic.available else (
            "规则未命中；语义检查不可用，仅能给出规则范围内的结果，不能视为全面通过。"
        )
        return WorkflowState(title, body, tuple(rules), findings, semantic, "clear", reason,
                             final_title=title, final_body=body, final_findings=findings,
                             final_semantic=semantic)
    reason = f"规则命中 {len(findings)} 项、语义问题 {len(semantic.issues)} 项，进入人工确认。"
    try:
        suggestion = draft_maker(title, body, findings, semantic.issues)
    except Exception as exc:
        suggestion = None
        reason += f" 生成建议失败（{type(exc).__name__}），原文保留。"
    if suggestion is None or (suggestion.title == title and suggestion.body == body):
        return WorkflowState(title, body, tuple(rules), findings, semantic,
                             "suggestion_unavailable", reason + " 当前无有效修改建议。")
    return WorkflowState(title, body, tuple(rules), findings, semantic,
                         "needs_decision", reason, suggestion=suggestion)


def decide_workflow(
    state: WorkflowState, decision: str, semantic_reviewer: SemanticReviewer,
    confirmed_draft: Draft | None = None,
) -> WorkflowState:
    if state.path != "needs_decision" or state.suggestion is None:
        raise ValueError("当前没有待确认的修改建议。")
    if decision == "reject":
        return replace(state, path="rejected", decision_reason="用户选择保留原文；原风险未消除。",
                       final_title=state.original_title, final_body=state.original_body,
                       final_findings=state.original_findings, final_semantic=state.semantic)
    if decision != "accept":
        raise ValueError("未知的用户决策。")
    draft = confirmed_draft if confirmed_draft is not None else state.suggestion
    if not (draft.title.strip() or draft.body.strip()):
        raise ValueError("建议稿为空，无法采用。")
    if state.original_title.strip() and not draft.title.strip():
        raise ValueError("确认版标题为空，不能丢失原文标题。")
    if state.original_body.strip() and not draft.body.strip():
        raise ValueError("确认版正文为空，不能丢失原文正文。")
    # Recheck the exact candidate shown to and accepted by the user.
    findings = tuple(check_text(draft.title, draft.body, list(state.rules)))
    semantic = _review_semantics(semantic_reviewer, draft.title, draft.body)
    if findings or semantic.issues:
        reason = f"已采用并复检，仍有 {len(findings)} 项规则命中、{len(semantic.issues)} 项语义问题；尚未完全通过。"
    elif not semantic.available:
        reason = "已采用并复检，规则未命中；语义复检不可用，不能标记为全面通过。"
    else:
        reason = "已采用并复检，规则与语义检查均未发现明显问题；仍需人工发布前判断。"
    return replace(state, path="accepted", decision_reason=reason, final_title=draft.title,
                   final_body=draft.body, final_findings=findings, final_semantic=semantic)


def _review_semantics(reviewer: SemanticReviewer, title: str, body: str) -> SemanticReview:
    try:
        result = reviewer(title, body)
        if not isinstance(result, SemanticReview):
            raise ValueError("语义结果格式错误")
        return result
    except Exception as exc:
        return SemanticReview(error=f"{type(exc).__name__}: {exc}")
