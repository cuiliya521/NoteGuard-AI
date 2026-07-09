from __future__ import annotations

from dataclasses import dataclass

from services.llm import get_last_error, rewrite_content
from services.rule_checker import Finding


@dataclass(frozen=True)
class RewriteChange:
    original: str
    replacement: str
    reason: str
    position: str


@dataclass(frozen=True)
class RewriteResult:
    title: str
    body: str
    source: str
    reason: str
    error: str


def rewrite_by_local_rules(text: str, findings: list[Finding], position: str) -> str:
    rewritten = text or ""
    position_findings = [
        finding
        for finding in findings
        if finding.position == position and finding.suggestion
    ]

    seen_terms: set[str] = set()
    for finding in position_findings:
        if finding.term in seen_terms:
            continue
        rewritten = rewritten.replace(finding.term, finding.suggestion)
        seen_terms.add(finding.term)

    return rewritten


def rewrite_all(title: str, body: str, findings: list[Finding]) -> RewriteResult:
    ai_result = rewrite_content(title=title, body=body, risk_items=findings)
    if ai_result:
        return RewriteResult(
            title=ai_result.get("title") or title,
            body=ai_result.get("body") or body,
            source="deepseek",
            reason=ai_result.get("reason", ""),
            error="",
        )

    return RewriteResult(
        title=rewrite_by_local_rules(title, findings, "标题"),
        body=rewrite_by_local_rules(body, findings, "正文"),
        source="local",
        reason="",
        error=get_last_error(),
    )


def rewrite_by_rules(text: str, findings: list[Finding], position: str) -> str:
    position_findings = [
        finding
        for finding in findings
        if finding.position == position
    ]
    title = text if position == "标题" else ""
    body = text if position == "正文" else ""
    ai_result = rewrite_content(title=title, body=body, risk_items=position_findings)

    if ai_result:
        rewritten_text = ai_result.get("title") if position == "标题" else ai_result.get("body")
        if rewritten_text:
            return rewritten_text

    return rewrite_by_local_rules(text, findings, position)


def build_rewrite_reason(finding: Finding) -> str:
    if finding.category == "效果承诺" or "承诺" in finding.reason:
        return "避免效果承诺"

    if "人群" in finding.reason or finding.term in {"孩子", "娃", "宝贝"}:
        return "降低人群表达风险"

    if finding.severity == "high":
        return "降低高风险表达"

    return "降低审核风险"


def build_rewrite_changes(findings: list[Finding], position: str) -> list[RewriteChange]:
    changes: list[RewriteChange] = []
    seen_terms: set[str] = set()

    for finding in findings:
        if finding.position != position or not finding.suggestion:
            continue
        if finding.term in seen_terms:
            continue

        changes.append(
            RewriteChange(
                original=finding.term,
                replacement=finding.suggestion,
                reason=build_rewrite_reason(finding),
                position=position,
            )
        )
        seen_terms.add(finding.term)

    return changes


def build_rewrite_note(findings: list[Finding]) -> str:
    return build_rewrite_status_note(findings, source="local", error="")


def build_rewrite_status_note(
    findings: list[Finding],
    source: str,
    error: str = "",
) -> str:
    source_label = "AI智能改写" if source == "deepseek" else "本地规则改写"

    if source == "deepseek":
        return f"{source_label}：已调用 DeepSeek 生成改写建议。"

    replaceable = [item for item in findings if item.suggestion]
    unreplaceable = [item for item in findings if not item.suggestion]
    error_note = f" DeepSeek 未启用或调用失败：{error}" if error else ""

    if not findings:
        return f"{source_label}：当前内容未命中规则库风险词，基础改写保持原文。{error_note}"

    if replaceable and not unreplaceable:
        return f"{source_label}：已根据规则库完成基础替换。{error_note}"

    if replaceable and unreplaceable:
        return f"{source_label}：已替换有明确建议的风险词；无替换建议的词建议人工删除或重新表达。{error_note}"

    return f"{source_label}：命中的风险词暂无明确替换建议，建议人工删除或弱化表达。{error_note}"
