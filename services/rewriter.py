from __future__ import annotations

import hashlib
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
class FormatPreservingChange:
    original: str
    replacement: str
    location: str


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


@dataclass(frozen=True)
class LineReviewItem:
    item_id: str
    original_text: str
    context: str
    position: str
    category: str
    severity: str
    reason: str
    replacement_text: str


PHRASE_REPLACEMENTS = {
    "数学思维": "数理思维",
}


def clean_rewritten_text(text: str, preserve_layout: bool = False) -> str:
    """Remove obvious artifacts introduced by local term replacements."""
    if preserve_layout:
        return text or ""

    cleaned = re.sub(r"[\t\f\v ]+", " ", text or "").strip()
    cleaned = re.sub(r"(?<=[\u4e00-\u9fff])[\t ]+(?=[\u4e00-\u9fff])", "", cleaned)

    # Collapse adjacent repeated Chinese words or short phrases, for example 思维思维.
    while True:
        updated = re.sub(r"([\u4e00-\u9fff]{1,6})\1", r"\1", cleaned)
        if updated == cleaned:
            break
        cleaned = updated

    cleaned = re.sub(r"([，。！？、；：,!.?;:])\1+", r"\1", cleaned)
    return cleaned


def _find_context_span(text: str, start: int, end: int) -> tuple[int, int]:
    boundaries = "\n。！？!?；;"
    left = max((text.rfind(char, 0, start) for char in boundaries), default=-1) + 1
    right_candidates = [
        index + 1
        for char in boundaries
        if (index := text.find(char, end)) != -1
    ]
    right = min(right_candidates, default=len(text))

    while left < right and text[left].isspace():
        left += 1
    while right > left and text[right - 1].isspace():
        right -= 1
    return left, right


def _build_minimal_replacement(
    context_text: str,
    finding: Finding,
    context_start: int,
) -> str:
    relative_start = finding.start - context_start
    relative_end = finding.end - context_start
    replacement = finding.suggestion or ""

    for phrase, phrase_replacement in sorted(
        PHRASE_REPLACEMENTS.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        term_offset = phrase.find(finding.term)
        phrase_start = relative_start - term_offset
        phrase_end = phrase_start + len(phrase)
        if term_offset >= 0 and phrase_start >= 0 and context_text[phrase_start:phrase_end] == phrase:
            relative_start = phrase_start
            relative_end = phrase_end
            replacement = phrase_replacement
            break

    rewritten = (
        context_text[:relative_start]
        + replacement
        + context_text[relative_end:]
    )
    rewritten = re.sub(r"[\t ]{2,}", " ", rewritten)
    rewritten = re.sub(r"([，。！？、；：,!.?;:])\1+", r"\1", rewritten)
    return rewritten.strip()


def build_line_review_items(
    title: str,
    body: str,
    findings: list[Finding],
) -> list[LineReviewItem]:
    sources = {"标题": title or "", "正文": body or ""}
    items: list[LineReviewItem] = []

    for finding in findings:
        source = sources.get(finding.position, "")
        if not source or finding.start < 0 or finding.end > len(source):
            continue
        context_start, context_end = _find_context_span(
            source,
            finding.start,
            finding.end,
        )
        original_text = source[context_start:context_end]
        line_number = source.count("\n", 0, finding.start) + 1
        item_key = (
            f"{finding.position}:{finding.start}:{finding.end}:"
            f"{finding.term}:{original_text}"
        )
        item_id = hashlib.sha1(item_key.encode("utf-8")).hexdigest()[:12]
        items.append(
            LineReviewItem(
                item_id=item_id,
                original_text=original_text,
                context=f"{finding.position} · 第 {line_number} 行",
                position=finding.position,
                category=finding.category,
                severity=finding.severity,
                reason=finding.reason,
                replacement_text=_build_minimal_replacement(
                    original_text,
                    finding,
                    context_start,
                ),
            )
        )
    return items


def build_supplier_feedback(items: list[LineReviewItem]) -> str:
    if not items:
        return "当前未发现需要修改的问题。"

    sections = []
    for index, item in enumerate(items, start=1):
        sections.append(
            "\n".join(
                [
                    f"问题{index}：",
                    f"原句：{item.original_text}",
                    f"问题：{item.reason}",
                    f"建议修改为：{item.replacement_text}",
                ]
            )
        )
    return "\n\n".join(sections)


def get_line_review_progress(
    items: list[LineReviewItem],
    statuses: dict[str, str],
) -> tuple[int, int, int]:
    total = len(items)
    handled = sum(
        1 for item in items if statuses.get(item.item_id) == "handled"
    )
    return total, handled, total - handled


def rewrite_by_local_rules(text: str, findings: list[Finding], position: str) -> str:
    rewritten = text or ""
    position_findings = [
        finding
        for finding in findings
        if finding.position == position and finding.suggestion
    ]

    replacements: list[tuple[int, int, str]] = []
    for finding in position_findings:
        start, end = finding.start, finding.end
        replacement = finding.suggestion
        for phrase, phrase_replacement in sorted(
            PHRASE_REPLACEMENTS.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            term_offset = phrase.find(finding.term)
            phrase_start = start - term_offset
            phrase_end = phrase_start + len(phrase)
            if (
                term_offset >= 0
                and phrase_start >= 0
                and rewritten[phrase_start:phrase_end] == phrase
            ):
                start, end = phrase_start, phrase_end
                replacement = phrase_replacement
                break
        if any(start < used_end and end > used_start for used_start, used_end, _ in replacements):
            continue
        replacements.append((start, end, replacement))

    for start, end, replacement in sorted(replacements, reverse=True):
        rewritten = rewritten[:start] + replacement + rewritten[end:]

    return clean_rewritten_text(rewritten, preserve_layout=position == "正文")


def _split_lines_with_separators(text: str) -> tuple[list[str], list[str]]:
    parts = re.split(r"(\r\n|\r|\n)", text or "")
    return parts[::2], parts[1::2]


def _line_findings(text: str, findings: list[Finding]) -> list[list[Finding]]:
    lines, separators = _split_lines_with_separators(text)
    grouped: list[list[Finding]] = [[] for _ in lines]
    offset = 0
    for index, line in enumerate(lines):
        line_end = offset + len(line)
        grouped[index] = [
            finding
            for finding in findings
            if finding.start < line_end and finding.end > offset
        ]
        offset = line_end + (len(separators[index]) if index < len(separators) else 0)
    return grouped


def _preserves_non_risk_text(original: str, candidate: str, findings: list[Finding], offset: int) -> bool:
    intervals: list[tuple[int, int]] = []
    for finding in findings:
        start = max(0, finding.start - offset)
        end = min(len(original), finding.end - offset)
        if start < end:
            intervals.append((start, end))
    intervals.sort()

    cursor = 0
    candidate_cursor = 0
    for start, end in intervals:
        protected = original[cursor:start]
        protected_index = candidate.find(protected, candidate_cursor)
        if protected and protected_index == -1:
            return False
        if protected:
            candidate_cursor = protected_index + len(protected)
        cursor = max(cursor, end)

    protected = original[cursor:]
    return not protected or candidate.find(protected, candidate_cursor) != -1


def merge_format_preserving_rewrite(
    original: str,
    candidate: str,
    findings: list[Finding],
    position: str,
) -> str:
    """Accept AI edits only on risk-bearing lines while preserving original layout."""
    position_findings = [item for item in findings if item.position == position]
    if not position_findings or not candidate:
        return original or ""

    original_lines, separators = _split_lines_with_separators(original)
    candidate_lines, candidate_separators = _split_lines_with_separators(candidate)
    local_lines, _ = _split_lines_with_separators(
        rewrite_by_local_rules(original, position_findings, position)
    )
    grouped_findings = _line_findings(original, position_findings)

    same_layout = (
        len(original_lines) == len(candidate_lines)
        and separators == candidate_separators
    )
    result_lines: list[str] = []
    offset = 0
    for index, original_line in enumerate(original_lines):
        line_findings = grouped_findings[index]
        if not line_findings:
            result_lines.append(original_line)
        elif same_layout:
            candidate_line = candidate_lines[index]
            removed_risks = all(item.term not in candidate_line for item in line_findings)
            if removed_risks and _preserves_non_risk_text(
                original_line,
                candidate_line,
                line_findings,
                offset,
            ):
                result_lines.append(candidate_line)
            else:
                result_lines.append(local_lines[index])
        else:
            result_lines.append(local_lines[index])
        offset += len(original_line) + (len(separators[index]) if index < len(separators) else 0)

    fragments: list[str] = []
    for index, line in enumerate(result_lines):
        fragments.append(line)
        if index < len(separators):
            fragments.append(separators[index])
    return "".join(fragments)


def build_format_preserving_changes(
    original_title: str,
    original_body: str,
    rewritten_title: str,
    rewritten_body: str,
) -> list[FormatPreservingChange]:
    changes: list[FormatPreservingChange] = []
    if original_title != rewritten_title:
        changes.append(
            FormatPreservingChange(original_title, rewritten_title, "标题")
        )

    original_lines = (original_body or "").splitlines()
    rewritten_lines = (rewritten_body or "").splitlines()
    for index, original_line in enumerate(original_lines):
        rewritten_line = rewritten_lines[index] if index < len(rewritten_lines) else ""
        if original_line != rewritten_line:
            changes.append(
                FormatPreservingChange(
                    original_line,
                    rewritten_line,
                    f"正文 · 第 {index + 1} 行",
                )
            )
    return changes


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
            title=merge_format_preserving_rewrite(
                title,
                ai_result.get("title") or title,
                findings,
                "标题",
            ),
            body=merge_format_preserving_rewrite(
                body,
                ai_result.get("body") or body,
                findings,
                "正文",
            ),
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
