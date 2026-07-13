from __future__ import annotations

import re
from dataclasses import dataclass

from services.llm import get_last_error, rewrite_content
from services.rule_checker import Finding, Rule, check_text


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


@dataclass(frozen=True)
class TitleCandidateReview:
    original_title: str
    safe_title: str
    status: str
    risk_terms: tuple[str, ...]
    change_note: str


PHRASE_REPLACEMENTS = {
    "数学思维": "数理思维",
}


def clean_rewritten_text(text: str) -> str:
    """Remove obvious artifacts introduced by local term replacements."""
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    cleaned = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", cleaned)

    # Collapse adjacent repeated Chinese words or short phrases, for example 思维思维.
    while True:
        updated = re.sub(r"([\u4e00-\u9fff]{1,6})\1", r"\1", cleaned)
        if updated == cleaned:
            break
        cleaned = updated

    cleaned = re.sub(r"([，。！？、；：,!.?;:])\1+", r"\1", cleaned)
    return cleaned


def rewrite_by_local_rules(text: str, findings: list[Finding], position: str) -> str:
    rewritten = text or ""
    for phrase, replacement in sorted(
        PHRASE_REPLACEMENTS.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        rewritten = rewritten.replace(phrase, replacement)

    position_findings = [
        finding
        for finding in findings
        if finding.position == position and finding.suggestion
    ]

    seen_terms: set[str] = set()
    for finding in sorted(position_findings, key=lambda item: len(item.term), reverse=True):
        if finding.term in seen_terms:
            continue
        rewritten = rewritten.replace(finding.term, finding.suggestion)
        seen_terms.add(finding.term)

    return clean_rewritten_text(rewritten)


def rewrite_all(
    title: str,
    body: str,
    findings: list[Finding],
    creator_profile: dict[str, str] | None = None,
) -> RewriteResult:
    ai_result = rewrite_content(
        title=title,
        body=body,
        risk_items=findings,
        creator_profile=creator_profile,
    )
    if ai_result:
        return RewriteResult(
            title=ai_result.get("title") or title,
            body=ai_result.get("body") or body,
            source="deepseek",
            reason=ai_result.get("reason", ""),
            error="",
        )

    local_result = rewrite_with_local_rules(title, body, findings)
    return RewriteResult(
        title=local_result.title,
        body=local_result.body,
        source=local_result.source,
        reason=local_result.reason,
        error=get_last_error(),
    )


def rewrite_with_local_rules(title: str, body: str, findings: list[Finding]) -> RewriteResult:
    return RewriteResult(
        title=rewrite_by_local_rules(title, findings, "标题"),
        body=rewrite_by_local_rules(body, findings, "正文"),
        source="local",
        reason="",
        error="",
    )


def rewrite_by_rules(
    text: str,
    findings: list[Finding],
    position: str,
    creator_profile: dict[str, str] | None = None,
) -> str:
    position_findings = [
        finding
        for finding in findings
        if finding.position == position
    ]
    title = text if position == "标题" else ""
    body = text if position == "正文" else ""
    ai_result = rewrite_content(
        title=title,
        body=body,
        risk_items=position_findings,
        creator_profile=creator_profile,
    )

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


def _force_replace_remaining_title_risks(title: str, findings: list[Finding]) -> tuple[str, list[str]]:
    rewritten = title
    changes: list[str] = []
    for finding in sorted(findings, key=lambda item: item.start, reverse=True):
        replacement = finding.suggestion or ""
        rewritten = rewritten[:finding.start] + replacement + rewritten[finding.end:]
        change = f"{finding.term} → {replacement or '删除'}"
        if change not in changes:
            changes.append(change)
    return clean_rewritten_text(rewritten), list(reversed(changes))


def review_title_candidates(
    titles: list[str],
    rules: list[Rule],
) -> list[TitleCandidateReview]:
    reviews: list[TitleCandidateReview] = []
    for title in titles:
        original_findings = check_text(title=title, body="", rules=rules)
        if not original_findings:
            reviews.append(
                TitleCandidateReview(
                    original_title=title,
                    safe_title=title,
                    status="安全",
                    risk_terms=(),
                    change_note="已通过当前规则审核。",
                )
            )
            continue

        local_result = rewrite_with_local_rules(title, "", original_findings)
        remaining_findings = check_text(title=local_result.title, body="", rules=rules)
        safe_title, forced_changes = _force_replace_remaining_title_risks(
            local_result.title,
            remaining_findings,
        )
        final_findings = check_text(title=safe_title, body="", rules=rules)
        changes = [
            f"{item.term} → {item.suggestion or '删除'}"
            for item in original_findings
        ]
        for change in forced_changes:
            if change not in changes:
                changes.append(change)

        reviews.append(
            TitleCandidateReview(
                original_title=title,
                safe_title=safe_title or "内容标题建议重新生成",
                status="安全" if not final_findings else "有风险",
                risk_terms=tuple(dict.fromkeys(item.term for item in original_findings)),
                change_note="；".join(changes) or "已根据规则库调整表达。",
            )
        )
    return reviews
