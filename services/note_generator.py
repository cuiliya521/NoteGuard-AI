from __future__ import annotations

import hashlib
from io import BytesIO
import json
import re
from typing import Any

from PIL import Image, UnidentifiedImageError

from services.rewriter import review_title_candidates, rewrite_with_local_rules
from services.rule_checker import Finding, Rule, check_text


CONTENT_DIRECTIONS = (
    "自动判断",
    "家长痛点型",
    "老师经验型",
    "课程介绍型",
    "干货分享型",
    "案例复盘型",
    "家长共鸣型",
)

GENERATION_MODES = ("根据图片生成", "根据文字生成")
IMAGE_GENERATION_STRUCTURE = (
    "图片驱动模式必须按‘用户痛点 → 已确认的老师身份背书 → 课程/服务介绍 "
    "→ 已确认的优势 → 自然行动引导’组织。创作者资料未确认的背书、案例和数据必须省略。"
)

LENGTH_RANGES = {
    "300—500字": (300, 500),
    "500—700字": (500, 700),
    "700—1000字": (700, 1000),
}

IMAGE_NOTE_MIN_CHARS = 800
IMAGE_NOTE_MAX_CHARS = 1000
IMAGE_NOTE_TITLE_COUNT = 3

IMAGE_CONTENT_STRUCTURES = {
    "教学经验": "家长真实困惑 → 具体课堂或教学场景 → 老师观察 → 问题原因 → 可执行做法 → 适用边界 → 评论区交流",
    "学生成果案例": "案例起点（家长关心的问题） → 已确认的学习过程与方法 → 可验证变化 → 案例边界 → 可复用做法 → 评论区问题",
    "课程服务": "家长真实困惑与使用场景 → 课程解决思路 → 已确认的课程方式与服务价值 → 适用人群 → 温和行动引导",
    "学习方法分享": "具体学习问题 → 常见误区 → 老师判断 → 可执行步骤/清单 → 使用场景 → 评论区问题",
}

_DIRECTION_STRUCTURES = {
    "自动判断": (
        "根据素材判断最强切入点，在场景、观点、方法、可信资料和自然引导之间灵活组织。",
        "先找素材中最具体的问题，再选择经验、方法或服务信息展开，避免套用固定段落顺序。",
    ),
    "家长痛点型": (
        "从家长正在经历的具体困扰切入，再解释原因、给出方法，最后自然带出可用服务。",
        "先呈现一个真实陪学场景，用核心判断回应焦虑，再提供步骤和温和行动建议。",
    ),
    "老师经验型": (
        "从已保存的真实教学观察切入，依次给出判断依据、方法和适用场景。",
        "先提出一个常见误区，再用已保存的老师资料和教学方法解释如何调整。",
    ),
    "课程介绍型": (
        "先说明课程解决的具体学习问题，再展开形式、方法和服务特点，避免卖点堆砌。",
        "用学习场景引出服务价值，将课程形式分散融入方法说明，最后自然说明下一步。",
    ),
    "干货分享型": (
        "先给出明确观点，再拆解可执行方法、适用场景和常见误区。",
        "从一个具体问题切入，用清晰步骤或观察维度展开，服务信息只作必要补充。",
    ),
    "案例复盘型": (
        "仅复盘用户实际提供的案例素材，按问题、过程、观察和可借鉴方法展开，不补造结果。",
        "从已有案例中的关键转折或问题切入，解释采取的过程与方法，不虚构反馈和数据。",
    ),
    "家长共鸣型": (
        "从陪学中的情绪或沟通场景切入，先建立理解，再给出判断和可执行建议。",
        "先回应家长常见的无力感或困惑，再解释问题成因、调整方法和支持方式。",
    ),
}


def get_structure_guidance(direction: str, seed: str) -> str:
    structures = _DIRECTION_STRUCTURES.get(
        direction,
        _DIRECTION_STRUCTURES["自动判断"],
    )
    digest = hashlib.sha256(f"{direction}:{seed}".encode("utf-8")).hexdigest()
    return structures[int(digest, 16) % len(structures)]


def classify_image_content(
    image_context: dict[str, Any],
    image_analysis: dict[str, Any] | None = None,
) -> str:
    """Classify education image value before choosing a publishing structure."""
    allowed = tuple(IMAGE_CONTENT_STRUCTURES)
    analysis = image_analysis or {}
    explicit = str(analysis.get("content_type") or image_context.get("content_type") or "").strip()
    aliases = {
        "课程推广": "课程服务",
        "案例证明": "学生成果案例",
        "经验分享": "教学经验",
        "知识分享": "学习方法分享",
    }
    explicit = aliases.get(explicit, explicit)
    if explicit in allowed:
        return explicit
    combined = "\n".join(
        str(value)
        for value in (
            image_context.get("confirmed_cover_text", ""),
            image_context.get("visual_scene", ""),
            image_context.get("education_value", ""),
            analysis.get("cover_theme", ""),
            analysis.get("selling_direction", ""),
            " ".join(analysis.get("visual_elements", []) or []),
        )
    )
    if any(term in combined for term in ("课程", "招生", "试听", "课时", "辅导", "1v1", "一对一", "海报")):
        return "课程服务"
    if any(term in combined for term in ("成绩单", "分数", "前后对比", "提升记录", "案例", "进步")):
        return "学生成果案例"
    if any(term in combined for term in ("课堂", "讲课", "板书", "老师", "教学现场", "上课")):
        return "教学经验"
    return "学习方法分享"


def get_image_content_structure(content_type: str) -> str:
    return IMAGE_CONTENT_STRUCTURES.get(content_type, IMAGE_CONTENT_STRUCTURES["学习方法分享"])


def validate_publish_draft_quality(generated: dict[str, Any], content_type: str = "") -> list[str]:
    """Reject marketing-heavy drafts before they reach the publishing UI."""
    titles = [str(item).strip() for item in generated.get("titles", []) if str(item).strip()]
    body = str(generated.get("body", "")).strip()
    opening = body[:160]
    combined = "\n".join([*titles, body])
    issues: list[str] = []
    marketing_opening = ("报名", "咨询课程", "限时", "优惠", "名额", "免费试听", "加微信", "私信领取", "赶紧", "速来")
    if any(term in opening for term in marketing_opening):
        issues.append("正文不能用课程推销或营销动作开头")
    if any(term in combined for term in ("保证", "一定能", "百分百", "100%", "必提分", "包过", "逆袭成功")):
        issues.append("不得包含夸张承诺或绝对结果")
    if any(term in combined for term in ("家长必看", "错过后悔", "震惊", "速看", "最后机会")):
        issues.append("语气不能像营销号")
    if not any(term in body for term in ("可以先", "第一步", "先看", "建议", "方法", "步骤", "复盘", "检查", "1️⃣")):
        issues.append("正文必须提供至少一个可执行方法")
    if content_type == "课程服务" and any(term in opening for term in ("课程", "课时", "价格", "收费", "报名")):
        issues.append("课程服务内容也必须先写家长困惑或学习场景")
    return list(dict.fromkeys(issues))


def build_generation_request_key(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_rule_constraints(rules: list[Rule]) -> list[dict[str, str]]:
    return [
        {
            "term": rule.term,
            "severity": rule.severity,
            "category": rule.category,
            "reason": rule.reason,
            "suggestion": rule.suggestion,
        }
        for rule in rules
        if rule.term.strip()
    ]


def build_image_source_context(
    image_bytes: bytes,
    ocr_text: str,
    corrected_cover_text: str,
    cover_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not image_bytes:
        return {}

    image_format = ""
    width = 0
    height = 0
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image_format = (image.format or "").upper()
            width, height = image.size
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return {}

    confirmed_text = (corrected_cover_text or "").strip() or (ocr_text or "").strip()
    cover_analysis = cover_analysis or {}
    return {
        "image_hash": hashlib.sha256(image_bytes).hexdigest(),
        "image_format": image_format,
        "width": width,
        "height": height,
        "aspect_ratio": round(width / height, 3) if height else 0,
        "ocr_text": (ocr_text or "").strip(),
        "confirmed_cover_text": confirmed_text,
        "cover_analysis": cover_analysis,
        "content_type": str(cover_analysis.get("content_type", "")).strip(),
        "visual_scene": str(cover_analysis.get("visual_scene", "")).strip(),
        "education_value": str(cover_analysis.get("education_value", "")).strip(),
        "analysis_boundary": (
            "当前不传输图片像素给模型；图片结论仅基于 OCR、用户修正文字、"
            "尺寸比例和已有封面分析。"
        ),
    }


def can_generate_note(
    generation_mode: str,
    topic: str,
    title: str,
    body: str,
    image_context: dict[str, Any],
) -> tuple[bool, str]:
    if generation_mode == "根据图片生成":
        if not image_context:
            return False, "请先上传一张封面图片。"
        if not str(image_context.get("confirmed_cover_text", "")).strip():
            return False, "图片文字未识别成功，请在封面文字框中手动补充后再生成。"
        return True, ""

    if any((topic.strip(), title.strip(), body.strip())):
        return True, ""
    return False, "请先补充标题、正文或主题关键词。"


def truncate_complete_text(text: str, max_chars: int = 1000) -> str:
    normalized = (text or "").strip()
    limit = min(max(1, int(max_chars)), 1000)
    if len(normalized) <= limit:
        return normalized

    candidate = normalized[:limit]
    boundaries = [candidate.rfind(mark) for mark in "。！？!?\n"]
    boundary = max(boundaries)
    if boundary >= int(limit * 0.6):
        return candidate[: boundary + 1].rstrip()

    shortened = candidate[: limit - 1].rstrip("，、；：,;: ")
    return f"{shortened}。"


def _finding_note(finding: Finding) -> str:
    return f"{finding.term} → {finding.suggestion or '删除'}"


def _force_remaining_replacements(text: str, findings: list[Finding]) -> str:
    rewritten = text
    for finding in sorted(findings, key=lambda item: item.start, reverse=True):
        rewritten = (
            rewritten[: finding.start]
            + (finding.suggestion or "")
            + rewritten[finding.end :]
        )
    return rewritten


def make_generated_text_safe(
    text: str,
    rules: list[Rule],
    position: str,
) -> tuple[str, list[Finding], list[Finding], list[str]]:
    original = text or ""
    initial_findings = check_text(
        title=original if position == "标题" else "",
        body=original if position != "标题" else "",
        rules=rules,
    )
    rewritten = original
    changes: list[str] = []

    for _ in range(3):
        current_findings = check_text(
            title=rewritten if position == "标题" else "",
            body=rewritten if position != "标题" else "",
            rules=rules,
        )
        if not current_findings:
            break
        for finding in current_findings:
            note = _finding_note(finding)
            if note not in changes:
                changes.append(note)

        local_result = rewrite_with_local_rules(
            rewritten if position == "标题" else "",
            rewritten if position != "标题" else "",
            current_findings,
        )
        rewritten = local_result.title if position == "标题" else local_result.body
        remaining = check_text(
            title=rewritten if position == "标题" else "",
            body=rewritten if position != "标题" else "",
            rules=rules,
        )
        if remaining:
            rewritten = _force_remaining_replacements(rewritten, remaining)

    final_findings = check_text(
        title=rewritten if position == "标题" else "",
        body=rewritten if position != "标题" else "",
        rules=rules,
    )
    return rewritten.strip(), initial_findings, final_findings, changes


def _risk_rows(findings: list[Finding], scope: str) -> list[dict[str, str]]:
    return [
        {
            "scope": scope,
            "term": finding.term,
            "severity": finding.severity,
            "category": finding.category,
            "reason": finding.reason,
            "suggestion": finding.suggestion or "删除或弱化表达",
        }
        for finding in findings
    ]


def build_publish_version(
    title: str,
    body: str,
    action: str,
    tags: list[str],
    include_action: bool = True,
    include_tags: bool = True,
    comment_question: str = "",
) -> str:
    body_parts = [body.strip()]
    if include_action and action.strip():
        body_parts.append(action.strip())
    if comment_question.strip() and comment_question.strip() != action.strip():
        body_parts.append(comment_question.strip())
    sections = [title.strip(), "\n\n".join(part for part in body_parts if part)]
    if include_tags and tags:
        sections.append(" ".join(tags))
    return "\n\n".join(section for section in sections if section)


def finalize_generated_note(
    generated: dict[str, Any],
    rules: list[Rule],
    max_body_chars: int,
    include_action: bool = True,
    include_tags: bool = True,
    expected_title_count: int = 5,
) -> dict[str, Any]:
    expected_title_count = max(1, min(int(expected_title_count), 5))
    raw_titles = [str(item).strip() for item in generated.get("titles", []) if str(item).strip()]
    title_reviews = review_title_candidates(raw_titles, rules)
    final_titles: list[str] = []
    title_review_rows: list[dict[str, Any]] = []
    risk_items: list[dict[str, str]] = []
    modifications: list[str] = []
    second_review_findings: list[dict[str, str]] = []

    for review in title_reviews:
        original_title_findings = check_text(
            title=review.original_title,
            body="",
            rules=rules,
        )
        safe_title, initial, final, changes = make_generated_text_safe(
            review.safe_title,
            rules,
            "标题",
        )
        risk_items.extend(_risk_rows(original_title_findings or initial, "标题"))
        second_review_findings.extend(_risk_rows(final, "标题"))
        final_status = "安全" if not final else "有风险"
        if final_status == "安全" and safe_title:
            final_titles.append(safe_title)
        combined_changes = list(dict.fromkeys([review.change_note, *changes]))
        modifications.extend(
            f"标题：{change}"
            for change in combined_changes
            if change and change != "已通过当前规则审核。"
        )
        title_review_rows.append(
            {
                "original_title": review.original_title,
                "safe_title": safe_title,
                "status": final_status,
                "risk_terms": list(review.risk_terms),
                "change_note": "；".join(combined_changes),
            }
        )

    raw_body = truncate_complete_text(
        str(generated.get("body", "")),
        max_chars=max_body_chars,
    )
    safe_body, body_initial, body_final, body_changes = make_generated_text_safe(
        raw_body,
        rules,
        "正文",
    )
    safe_body = truncate_complete_text(safe_body, max_chars=max_body_chars)
    body_final = check_text(title="", body=safe_body, rules=rules)
    risk_items.extend(_risk_rows(body_initial, "正文"))
    second_review_findings.extend(_risk_rows(body_final, "正文"))
    modifications.extend(f"正文：{change}" for change in body_changes)

    raw_action = str(generated.get("action", "")).strip()
    safe_action, action_initial, action_final, action_changes = make_generated_text_safe(
        raw_action,
        rules,
        "正文",
    )
    risk_items.extend(_risk_rows(action_initial, "行动引导"))
    second_review_findings.extend(_risk_rows(action_final, "行动引导"))
    modifications.extend(f"行动引导：{change}" for change in action_changes)

    raw_comment_question = str(generated.get("comment_question", "")).strip()
    safe_comment_question, comment_initial, comment_final, comment_changes = make_generated_text_safe(
        raw_comment_question,
        rules,
        "正文",
    )
    risk_items.extend(_risk_rows(comment_initial, "评论区问题"))
    second_review_findings.extend(_risk_rows(comment_final, "评论区问题"))
    modifications.extend(f"评论区问题：{change}" for change in comment_changes)

    safe_tags: list[str] = []
    for raw_tag in generated.get("tags", []):
        tag = str(raw_tag).strip()
        if not tag:
            continue
        safe_tag, tag_initial, tag_final, tag_changes = make_generated_text_safe(
            tag,
            rules,
            "正文",
        )
        safe_tag = re.sub(r"\s+", "", safe_tag)
        if safe_tag and not safe_tag.startswith("#"):
            safe_tag = f"#{safe_tag}"
        if safe_tag:
            safe_tags.append(safe_tag)
        risk_items.extend(_risk_rows(tag_initial, "标签"))
        second_review_findings.extend(_risk_rows(tag_final, "标签"))
        modifications.extend(f"标签：{change}" for change in tag_changes)

    final_titles = final_titles[:expected_title_count]
    safe_tags = safe_tags[:5]
    passed = (
        not second_review_findings
        and len(final_titles) == expected_title_count
        and bool(safe_body)
        and len(safe_tags) == 5
    )
    primary_title = final_titles[0] if final_titles else ""
    publish_body = "\n\n".join(
        part
        for part in (
            safe_body,
            safe_action if include_action else "",
            safe_comment_question if safe_comment_question != safe_action else "",
        )
        if part
    )
    publish_text = build_publish_version(
        primary_title,
        safe_body,
        safe_action,
        safe_tags,
        include_action=include_action,
        include_tags=include_tags,
        comment_question=safe_comment_question,
    )

    return {
        "titles": final_titles,
        "body": safe_body,
        "action": safe_action,
        "comment_question": safe_comment_question,
        "tags": safe_tags,
        "publish_body": publish_body,
        "publish_text": publish_text,
        "title_reviews": title_review_rows,
        "risk_items": risk_items,
        "modifications": list(dict.fromkeys(modifications)),
        "second_review_findings": second_review_findings,
        "passed_second_review": passed,
        "body_char_count": len(safe_body),
    }


def validate_image_note_format(
    generated: dict[str, Any],
    min_chars: int = IMAGE_NOTE_MIN_CHARS,
    max_chars: int = IMAGE_NOTE_MAX_CHARS,
) -> list[str]:
    body = str(generated.get("body", "")).strip()
    issues: list[str] = []
    if len(body) < min_chars:
        issues.append(f"正文少于 {min_chars} 字")
    if len(body) > max_chars:
        issues.append(f"正文超过 {max_chars} 字")

    emoji_markers = ("👇", "😭", "😣", "❌", "⚠️", "👩‍🏫", "✅", "⭐", "📌", "👉")
    if not any(marker in body for marker in emoji_markers):
        issues.append("正文缺少适量 emoji")
    if not all(marker in body for marker in ("1️⃣", "2️⃣", "3️⃣")):
        issues.append("正文缺少 1️⃣2️⃣3️⃣ 方法拆解")

    paragraphs = [part.strip() for part in re.split(r"\n+", body) if part.strip()]
    if any(len(paragraph) > 100 for paragraph in paragraphs):
        issues.append("存在超过 100 字的长段落")
    return issues
