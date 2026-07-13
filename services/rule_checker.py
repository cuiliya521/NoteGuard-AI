from __future__ import annotations

import json
import re
from html import escape
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SEVERITY_LABELS = {
    "high": "高风险",
    "medium": "中风险",
    "low": "低风险",
}
VALID_SEVERITIES = set(SEVERITY_LABELS)

SAFE_TERMS = ["1v1", "一对一", "手把手", "线上", "试听", "刘梦亚"]
CONTEXT_EFFECT_TERMS = ["保证", "保过", "满分", "逆袭", "提分", "出分", "分数"]
RESULT_PROMISE_PATTERNS = [
    (
        re.compile(r"(?:\d+|[一二三四五六七八九十]+)天(?:提高|提升|增加|涨)(?:\d+|[一二三四五六七八九十]+)分"),
        "效果承诺",
        "疑似短期量化成绩结果承诺。",
        "学习状态改善",
        "high",
    ),
]


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


def normalize_rule_record(record: dict[str, Any]) -> dict[str, Any]:
    severity = str(record.get("severity", "medium")).strip().lower()
    enabled_value = record.get("enabled", True)
    enabled = enabled_value if isinstance(enabled_value, bool) else str(enabled_value).lower() != "false"

    return {
        "category": str(record.get("category", "未分类")).strip() or "未分类",
        "term": str(record.get("term", "")).strip(),
        "reason": str(record.get("reason", "疑似风险表达")).strip() or "疑似风险表达",
        "suggestion": str(record.get("suggestion", "")).strip(),
        "severity": severity if severity in VALID_SEVERITIES else "medium",
        "enabled": enabled,
    }


def load_rule_records(rule_path: Path) -> list[dict[str, Any]]:
    if not rule_path.exists():
        rule_path.parent.mkdir(parents=True, exist_ok=True)
        rule_path.write_text("[]\n", encoding="utf-8")

    with rule_path.open("r", encoding="utf-8") as file:
        raw_rules = json.load(file)

    if not isinstance(raw_rules, list):
        raise ValueError("规则文件格式错误：根节点必须是数组")

    return [
        normalize_rule_record(item)
        for item in raw_rules
        if isinstance(item, dict) and str(item.get("term", "")).strip()
    ]


def save_rule_records(rule_path: Path, records: list[dict[str, Any]]) -> None:
    normalized_records = [normalize_rule_record(record) for record in records]
    temporary_path = rule_path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(normalized_records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(rule_path)


def validate_rule_record(record: dict[str, Any]) -> dict[str, Any]:
    if not str(record.get("term", "")).strip():
        raise ValueError("关键词不能为空")
    if not str(record.get("category", "")).strip():
        raise ValueError("分类不能为空")
    if not str(record.get("reason", "")).strip():
        raise ValueError("原因不能为空")

    normalized = normalize_rule_record(record)
    return normalized


def add_rule_record(rule_path: Path, record: dict[str, Any]) -> None:
    records = load_rule_records(rule_path)
    new_record = validate_rule_record(record)
    if any(item["term"] == new_record["term"] for item in records):
        raise ValueError(f"关键词“{new_record['term']}”已存在，请直接编辑该规则")
    records.append(new_record)
    save_rule_records(rule_path, records)


def update_rule_record(
    rule_path: Path,
    original_term: str,
    record: dict[str, Any],
) -> None:
    records = load_rule_records(rule_path)
    updated_record = validate_rule_record(record)
    matching_indexes = [
        index for index, item in enumerate(records) if item["term"] == original_term
    ]
    if len(matching_indexes) != 1:
        raise ValueError("未找到可编辑的规则")

    index = matching_indexes[0]
    if any(
        item["term"] == updated_record["term"] and item["term"] != original_term
        for item in records
    ):
        raise ValueError(f"关键词“{updated_record['term']}”已存在")
    records[index] = updated_record
    save_rule_records(rule_path, records)


def delete_rule_record(rule_path: Path, term: str) -> None:
    records = load_rule_records(rule_path)
    remaining_records = [item for item in records if item["term"] != term]
    if len(remaining_records) == len(records):
        raise ValueError("未找到要删除的规则")
    save_rule_records(rule_path, remaining_records)


def get_severity_label(severity: str) -> str:
    return SEVERITY_LABELS.get(severity, "中风险")


def is_safe_term(term: str) -> bool:
    return term in SAFE_TERMS


def load_rules(rule_path: Path) -> list[Rule]:
    try:
        records = load_rule_records(rule_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return []

    return [
        Rule(
            category=item["category"],
            term=item["term"],
            reason=item["reason"],
            suggestion=item["suggestion"],
            severity=item["severity"],
        )
        for item in records
        if item["enabled"] and not is_safe_term(item["term"])
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


def build_pattern_findings(
    text: str,
    position: str,
    existing_findings: list[Finding],
) -> list[Finding]:
    pattern_findings: list[Finding] = []
    occupied_ranges = [
        (item.start, item.end)
        for item in existing_findings
        if item.position == position
    ]
    for pattern, category, reason, suggestion, severity in RESULT_PROMISE_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span()
            if any(start < occupied_end and end > occupied_start for occupied_start, occupied_end in occupied_ranges):
                continue
            pattern_findings.append(
                Finding(
                    term=match.group(),
                    position=position,
                    category=category,
                    reason=reason,
                    suggestion=suggestion,
                    severity=severity,
                    start=start,
                    end=end,
                )
            )
            occupied_ranges.append((start, end))
    return pattern_findings


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
            build_pattern_findings(
                text=text,
                position=position,
                existing_findings=findings,
            )
        )
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
    low_count = sum(1 for item in findings if item.severity == "low")

    parts = [f"共发现 {len(findings)} 处疑似风险表达"]
    if high_count:
        parts.append(f"高风险 {high_count} 处")
    if medium_count:
        parts.append(f"中风险 {medium_count} 处")
    if low_count:
        parts.append(f"低风险提示 {low_count} 处")

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
