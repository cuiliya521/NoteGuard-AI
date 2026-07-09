from __future__ import annotations

import json
from html import escape
from dataclasses import dataclass
from pathlib import Path


SEVERITY_LABELS = {
    "high": "高风险",
    "medium": "中风险",
    "low": "低风险",
}

SAFE_TERMS = ["1v1", "一对一", "手把手", "线上", "试听", "刘梦亚"]
CONTEXT_EFFECT_TERMS = ["保证", "保过", "满分", "逆袭", "提分", "出分", "分数"]


@dataclass(frozen=True)
class Rule:
    category: str
    term: str
    reason: str
    suggestion: str
    severity: str


@dataclass(frozen=True)
class Finding:
    term: str
    position: str
    category: str
    reason: str
    suggestion: str
    severity: str
    start: int
    end: int


def get_severity_label(severity: str) -> str:
    return SEVERITY_LABELS.get(severity, "中风险")


def is_safe_term(term: str) -> bool:
    return term in SAFE_TERMS


def load_rules(rule_path: Path) -> list[Rule]:
    with rule_path.open("r", encoding="utf-8") as file:
        raw_rules = json.load(file)

    return [
        Rule(
            category=str(item.get("category", "未分类")),
            term=str(item.get("term", "")).strip(),
            reason=str(item.get("reason", "疑似风险表达")),
            suggestion=str(item.get("suggestion", "")).strip(),
            severity=str(item.get("severity", "medium")),
        )
        for item in raw_rules
        if str(item.get("term", "")).strip()
        and not is_safe_term(str(item.get("term", "")).strip())
    ]


def find_safe_terms(text: str) -> list[str]:
    lower_text = text.lower()
    hits: list[str] = []
    for term in SAFE_TERMS:
        if term == "1v1":
            if term in lower_text:
                hits.append(term)
            continue
        if term in text:
            hits.append(term)
    return hits


def build_safe_term_hits(title: str, body: str = "") -> list[str]:
    full_text = f"{title or ''}\n{body or ''}"
    return find_safe_terms(full_text)


def build_context_findings(
    text: str,
    position: str,
    safe_terms: list[str],
    existing_findings: list[Finding],
) -> list[Finding]:
    if not safe_terms:
        return []

    context_findings: list[Finding] = []
    existing_ranges = {
        (item.position, item.term, item.start, item.end)
        for item in existing_findings
    }
    safe_term_text = "、".join(safe_terms)

    for term in CONTEXT_EFFECT_TERMS:
        start = 0
        while True:
            index = text.find(term, start)
            if index == -1:
                break

            end = index + len(term)
            finding_key = (position, term, index, end)
            if finding_key not in existing_ranges:
                context_findings.append(
                    Finding(
                        term=term,
                        position=position,
                        category="卖点组合复核",
                        reason=(
                            f"可用卖点词“{safe_term_text}”与效果承诺词“{term}”同时出现，"
                            "建议人工复核，避免形成夸大效果表达。"
                        ),
                        suggestion="",
                        severity="medium",
                        start=index,
                        end=end,
                    )
                )
            start = end

    return context_findings


def check_text(title: str, body: str, rules: list[Rule]) -> list[Finding]:
    findings: list[Finding] = []
    fields = [("标题", title or ""), ("正文", body or "")]
    ordered_rules = sorted(rules, key=lambda item: len(item.term), reverse=True)

    for position, text in fields:
        occupied_ranges: list[tuple[int, int]] = []
        for rule in ordered_rules:
            start = 0
            while True:
                index = text.find(rule.term, start)
                if index == -1:
                    break
                end = index + len(rule.term)

                has_overlap = any(
                    index < occupied_end and end > occupied_start
                    for occupied_start, occupied_end in occupied_ranges
                )
                if has_overlap:
                    start = end
                    continue

                findings.append(
                    Finding(
                        term=rule.term,
                        position=position,
                        category=rule.category,
                        reason=rule.reason,
                        suggestion=rule.suggestion,
                        severity=rule.severity,
                        start=index,
                        end=end,
                    )
                )
                occupied_ranges.append((index, end))
                start = end

        findings.extend(
            build_context_findings(
                text=text,
                position=position,
                safe_terms=find_safe_terms(text),
                existing_findings=findings,
            )
        )

    return sorted(
        findings,
        key=lambda item: (
            0 if item.position == "标题" else 1,
            item.start,
            -len(item.term),
        ),
    )


def build_risk_summary(findings: list[Finding]) -> str:
    if not findings:
        return "未发现规则库中的疑似风险词，仍建议人工复核后发布。"

    high_count = sum(1 for item in findings if item.severity == "high")
    medium_count = sum(1 for item in findings if item.severity == "medium")

    parts = [f"共发现 {len(findings)} 处疑似风险表达"]
    if high_count:
        parts.append(f"高风险 {high_count} 处")
    if medium_count:
        parts.append(f"中风险 {medium_count} 处")

    return "，".join(parts) + "。建议按替换话术修改后再人工复核。"


def build_highlighted_text(text: str, findings: list[Finding], position: str) -> str:
    position_findings = sorted(
        [item for item in findings if item.position == position],
        key=lambda item: item.start,
    )
    if not position_findings:
        return escape(text or "").replace("\n", "<br>")

    fragments: list[str] = []
    cursor = 0
    for finding in position_findings:
        fragments.append(escape(text[cursor:finding.start]))
        fragments.append(
            '<span class="risk-highlight">'
            f"{escape(text[finding.start:finding.end])}"
            "</span>"
        )
        cursor = finding.end

    fragments.append(escape(text[cursor:]))
    return "".join(fragments).replace("\n", "<br>")


def build_risk_detail_rows(findings: list[Finding]) -> list[dict[str, str]]:
    return [
        {
            "风险词": item.term,
            "风险等级": get_severity_label(item.severity),
            "分类": item.category,
            "原因": item.reason,
            "建议替换": item.suggestion or "建议删除、弱化或重新表述",
        }
        for item in findings
    ]
