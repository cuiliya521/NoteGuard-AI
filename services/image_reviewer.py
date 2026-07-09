from __future__ import annotations

from typing import TypedDict

from services.rule_checker import Rule, check_text


class ImageRiskItem(TypedDict):
    word: str
    suggestion: str
    reason: str


class ImageReviewResult(TypedDict):
    enabled: bool
    image_text: str
    risk_words: list[str]
    risk_items: list[ImageRiskItem]
    risk_level: str


def get_image_risk_level(risk_items: list[ImageRiskItem], has_high_risk: bool) -> str:
    if not risk_items:
        return "低风险"
    if has_high_risk:
        return "高风险"
    return "中风险"


def review_image(image_text: str, rules: list[Rule]) -> ImageReviewResult:
    normalized_text = (image_text or "").strip()
    if not normalized_text:
        return {
            "enabled": False,
            "image_text": "",
            "risk_words": [],
            "risk_items": [],
            "risk_level": "未知",
        }

    findings = check_text(title="", body=normalized_text, rules=rules)
    risk_items: list[ImageRiskItem] = []
    seen_words: set[str] = set()
    has_high_risk = False

    for finding in findings:
        if finding.severity == "high":
            has_high_risk = True
        if finding.term in seen_words:
            continue

        risk_items.append(
            {
                "word": finding.term,
                "suggestion": finding.suggestion or "建议删除、弱化或重新表述",
                "reason": finding.reason,
            }
        )
        seen_words.add(finding.term)

    return {
        "enabled": True,
        "image_text": normalized_text,
        "risk_words": [item["word"] for item in risk_items],
        "risk_items": risk_items,
        "risk_level": get_image_risk_level(risk_items, has_high_risk),
    }
