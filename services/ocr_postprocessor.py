from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


AUTO_CORRECTION_CONFIDENCE = 65.0

COMMON_CORRECTIONS = {
    "思维训炼": "思维训练",
    "数理思唯": "数理思维",
    "数学思唯": "数学思维",
    "学习规画": "学习规划",
    "解题思唯": "解题思维",
    "错提整理": "错题整理",
    "一对辅导": "一对一辅导",
}

EDUCATION_TERMS = {
    "数学思维",
    "数理思维",
    "思维训练",
    "学习规划",
    "学习能力",
    "学习方法",
    "解题思维",
    "解题思路",
    "错题整理",
    "基础薄弱",
    "个性化学习",
    "线上一对一",
    "线上1v1",
}

XIAOHONGSHU_EDUCATION_TERMS = {
    "家长痛点",
    "真实场景",
    "老师介绍",
    "老师背书",
    "课程介绍",
    "课程服务",
    "教学方法",
    "学习经验",
    "封面文案",
    "行动引导",
}


@dataclass(frozen=True)
class OcrCorrectionResult:
    original_text: str
    optimized_text: str
    changes: tuple[str, ...]
    confidence: float | None
    requires_confirmation: bool


def _creator_profile_terms(profile: dict[str, Any] | None) -> set[str]:
    if not profile:
        return set()
    terms: set[str] = set()
    for value in profile.values():
        for term in re.findall(r"[\u4e00-\u9fff]{3,12}|[A-Za-z0-9]{2,12}", str(value)):
            terms.add(term)
    return terms


def build_correction_terms(profile: dict[str, Any] | None = None) -> set[str]:
    return EDUCATION_TERMS | XIAOHONGSHU_EDUCATION_TERMS | _creator_profile_terms(profile)


def _replace_one_character_variants(text: str, terms: set[str]) -> tuple[str, list[str]]:
    optimized = text
    changes: list[str] = []
    for term in sorted(terms, key=len, reverse=True):
        if len(term) < 4 or not re.fullmatch(r"[\u4e00-\u9fff]+", term):
            continue
        for start in range(0, len(optimized) - len(term) + 1):
            candidate = optimized[start : start + len(term)]
            if not re.fullmatch(r"[\u4e00-\u9fff]+", candidate):
                continue
            if candidate in terms:
                continue
            differences = sum(left != right for left, right in zip(candidate, term))
            if differences != 1:
                continue
            optimized = optimized[:start] + term + optimized[start + len(term) :]
            change = f"{candidate} → {term}"
            if change not in changes:
                changes.append(change)
    return optimized, changes


def correct_ocr_text(
    text: str,
    creator_profile: dict[str, Any] | None = None,
    confidence: float | None = None,
) -> OcrCorrectionResult:
    original = (text or "").strip()
    requires_confirmation = confidence is None or confidence < AUTO_CORRECTION_CONFIDENCE
    if not original or requires_confirmation:
        return OcrCorrectionResult(
            original_text=original,
            optimized_text=original,
            changes=(),
            confidence=confidence,
            requires_confirmation=requires_confirmation,
        )

    optimized = original
    changes: list[str] = []
    for wrong, right in sorted(COMMON_CORRECTIONS.items(), key=lambda item: len(item[0]), reverse=True):
        if wrong not in optimized:
            continue
        optimized = optimized.replace(wrong, right)
        changes.append(f"{wrong} → {right}")

    optimized, fuzzy_changes = _replace_one_character_variants(
        optimized,
        build_correction_terms(creator_profile),
    )
    changes.extend(change for change in fuzzy_changes if change not in changes)
    return OcrCorrectionResult(
        original_text=original,
        optimized_text=optimized,
        changes=tuple(changes),
        confidence=confidence,
        requires_confirmation=False,
    )
