from __future__ import annotations

import re
from typing import Any


AUDIT_LANGUAGE = ("审核", "违规", "风险词", "安全改写")


def _first_matching_term(text: str, terms: tuple[str, ...]) -> str:
    return next((term for term in terms if term in text), "")


def build_publish_diagnosis(context: dict[str, Any]) -> dict[str, str]:
    """Turn normalized inputs into concrete Xiaohongshu publishing decisions."""
    title = str(context.get("title", "")).strip()
    content = str(context.get("content", "")).strip()
    cover_text = str(context.get("cover_text", "")).strip()
    profile = context.get("creator_profile") or {}
    visual = context.get("cover_visual") or {}
    dimensions = visual.get("dimensions") or {}
    combined = f"{title}\n{cover_text}\n{content}"
    audience = (
        str(context.get("target_user", "")).strip()
        or profile.get("target_grades", "").strip()
        or profile.get("target_students", "").strip()
        or "尚未明确具体年级或年龄段的学生家长"
    )

    subjects = ("数学", "语文", "英语", "物理", "化学", "生物", "竞赛")
    cover_subject = _first_matching_term(cover_text, subjects)
    body_subject = _first_matching_term(f"{title}\n{content}", subjects)
    has_audience_signal = bool(
        re.search(r"(?:\d{1,2}\s*[-—至到]\s*\d{1,2}\s*岁|小[一二三四五六]|初[一二三]|高[一二三]|小学|初中|高中|家长)", combined)
    )
    pain_terms = ("成绩", "分数", "不及格", "上不去", "不会", "听不懂", "错题", "拖后腿", "基础薄弱", "考试")
    value_terms = ("方法", "步骤", "习惯", "清单", "技巧", "复盘", "经验")
    title_has_pain = bool(_first_matching_term(title, pain_terms))
    title_has_value = bool(_first_matching_term(title, value_terms))
    teacher_focused = any(term in f"{title}\n{cover_text}" for term in ("老师", "教学经验", "一对一", "辅导", "课程", "收费"))
    promise_term = _first_matching_term(combined, ("保证", "一定", "必", "逆袭", "提高50分", "免费试听", "加微信"))

    visual_issues = [str(item).strip() for item in visual.get("issues", []) if str(item).strip()]
    visual_suggestions = [str(item).strip() for item in visual.get("suggestions", []) if str(item).strip()]
    if cover_subject and body_subject and cover_subject != body_subject:
        problem = f"封面聚焦“{cover_subject}”，但标题和正文主要在讲“{body_subject}”，用户点开后会发现内容定位不一致。"
        why = "封面负责建立点击预期，正文没有兑现同一个学科问题时，用户更容易快速退出。"
        priority = f"先统一封面、标题和正文，都围绕“{body_subject}”的同一个学习场景展开。"
    elif visual_issues:
        problem = visual_issues[0]
        why = "这个问题会让家长在信息流中难以快速判断内容是否与自己的孩子相关，以及点开后能获得什么。"
        priority = visual_suggestions[0] if visual_suggestions else "先把目标家长、孩子的具体学习问题和可获得的方法写进标题与封面主文案。"
    elif teacher_focused and not title_has_pain:
        problem = "标题或封面主要介绍老师、课程或服务，没有先呈现家长正在面对的具体学习问题。"
        why = "家长通常先判断内容是否对应孩子的现状，过早介绍服务会降低点击意愿，也更像广告。"
        priority = "先把孩子的年级、学科和当前卡点放到标题前半句，再把老师经验作为正文中的可信依据。"
    elif not has_audience_signal:
        problem = "标题、封面和正文没有明确写出适用年级或年龄段，家长无法在3秒内判断这篇内容是否适合自己的孩子。"
        why = "缺少目标人群会同时削弱搜索匹配和点击判断，内容价值再清楚也容易被非目标用户略过。"
        priority = "先在标题或封面补充具体年级、年龄段和学科，例如“初二数学”，再说明孩子正在遇到的问题。"
    elif not title_has_pain:
        problem = "标题说明了内容主题，但没有写出家长最关心的具体学习困扰。"
        why = "用户看不到与自己孩子现状直接相关的痛点，就缺少立即点开的理由。"
        priority = "先把正文里最具体的成绩、考试、错题或学习状态放进标题，并保留一个明确的方法价值。"
    elif not title_has_value:
        problem = "标题写出了孩子的问题，但没有说明用户点开后能获得什么具体方法或判断依据。"
        why = "只有痛点没有价值预期，会制造焦虑，却不能形成稳定的阅读动力。"
        priority = "在标题后半句补充可获得的方法、步骤或清单，但不要承诺确定的成绩结果。"
    elif promise_term:
        problem = f"“{promise_term}”把注意力放在确定结果或强营销动作上，容易削弱教育内容的可信度。"
        why = "家长更需要看到适用场景、真实过程和可执行方法，过强承诺会让内容像广告。"
        priority = "保留成绩问题带来的结果感，同时改为方法、过程或检查清单，避免承诺确定效果。"
    else:
        pain = str(context.get("pain_point", "")).strip() or "孩子当前的具体学习卡点"
        problem = f"标题、封面和正文主题基本一致，但“{pain[:32]}”还没有在标题前半句形成清晰的点击理由。"
        why = "家长需要先看到与孩子现状对应的问题，再判断这篇内容是否值得继续阅读。"
        priority = "把目标年级、学科卡点和正文提供的方法压缩成一句具体标题，并让封面使用同一核心信息。"

    result = {
        "target_user": audience,
        "problem": problem,
        "why": why,
        "priority": priority,
    }
    for key, value in result.items():
        if key != "target_user" and any(term in value for term in AUDIT_LANGUAGE):
            result[key] = "当前发布信息没有把目标家长、孩子的具体学习问题和可获得的方法连成同一条清晰主线。"
    return result


def build_publish_readiness(context: dict[str, Any], diagnosis: dict[str, str]) -> dict[str, Any]:
    """Return a coarse publishing-readiness band without audit-style precision."""
    title = str(context.get("title", "")).strip()
    content = str(context.get("content", "")).strip()
    combined = f"{title}\n{context.get('cover_text', '')}\n{content}"
    deductions: list[dict[str, Any]] = []
    if not title:
        deductions.append({"reason": "缺少可用于信息流展示的标题", "points": 25})
    if not str(context.get("target_user", "")).strip():
        deductions.append({"reason": "没有明确适用年级、阶段或目标家长", "points": 15})
    if not any(term in title for term in ("成绩", "分数", "不会", "错题", "基础", "考试", "上不去")):
        deductions.append({"reason": "标题没有呈现具体学习问题", "points": 10})
    if not any(term in title for term in ("方法", "步骤", "关键", "习惯", "清单", "原因", "怎么")):
        deductions.append({"reason": "标题没有说明点开后能获得什么", "points": 10})
    if any(term in combined for term in ("保证", "一定", "30天提高", "提高50分", "免费试听", "加微信")):
        deductions.append({"reason": "存在确定结果或强营销表达", "points": 15})
    if len(content) < 80:
        deductions.append({"reason": "正文较短，问题、原因和方法还不完整", "points": 10})
    score = 100 - sum(item["points"] for item in deductions)
    score = max(40, min(90, round(score / 5) * 5))
    return {
        "score": score,
        "factor": diagnosis.get("problem", "标题、封面和正文还需要统一发布信息。"),
        "deductions": deductions,
        "basis": "用户定位、点击理由、内容结构、信任表达",
    }


def build_content_context(
    *,
    title: str,
    content: str,
    cover_text: str,
    cover_visual: dict[str, Any] | None,
    creator_profile: dict[str, str] | None,
) -> dict[str, Any]:
    """Create the single normalized input consumed by downstream analysis."""
    visual = dict(cover_visual or {})
    profile = dict(creator_profile or {})
    dimensions = visual.get("dimensions") or {}
    normalized_cover_text = (cover_text or "").strip()
    age_match = re.search(
        r"(\d{1,2}\s*[-—至到]\s*\d{1,2}\s*岁)",
        f"{normalized_cover_text}\n{title}\n{content}",
    )
    first_cover_line = next(
        (line.strip() for line in normalized_cover_text.splitlines() if line.strip()),
        "",
    )
    first_content_line = next(
        (line.strip() for line in (content or "").splitlines() if line.strip()),
        "",
    )
    return {
        "title": (title or "").strip(),
        "content": (content or "").strip(),
        "cover_text": normalized_cover_text,
        "cover_visual": visual,
        "creator_profile": profile,
        "visual_topic": dimensions.get("core_selling_point") or first_cover_line or (title or "").strip(),
        "target_user": (
            f"{age_match.group(1)}孩子家长"
            if age_match
            else profile.get("target_grades", "").strip()
            or profile.get("target_students", "").strip()
        ),
        "pain_point": dimensions.get("parent_pain") or first_content_line,
    }
