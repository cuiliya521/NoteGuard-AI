from __future__ import annotations

from copy import deepcopy
from typing import Callable, TypeVar


T = TypeVar("T")


DEMO_TITLES = [
    "初中数学成绩上不去？先检查学习方法",
    "孩子数学总拖后腿？先找到适合的方法",
    "小学高年级到初中，数学学习方法怎么选",
    "线上1v1数学辅导，家长先看学习方法是否适合",
    "孩子数学提升不明显？复盘每天1小时怎么学",
]

DEMO_COVER_ANALYSIS = {
    "score": 82,
    "attraction": 4,
    "dimensions": {
        "title_attraction": "主题明确，数字化表达便于快速理解。",
        "parent_pain": "覆盖了家长对错题反复和复习低效的关注。",
        "information_density": "信息量适中，建议保留一个核心结论。",
        "marketing_risk": "避免使用保证提分、必学等绝对化表达。",
        "core_selling_point": "可执行的三步复盘方法。",
        "visual_hierarchy": "主标题两行内，数字和关键词使用品牌红强调。",
        "mobile_readability": "正文控制在两处辅助信息，留足边距。",
    },
    "issues": ["原文效果承诺较强", "副标题信息略多"],
    "suggestions": ["将结果承诺改为方法价值", "突出“3步复盘”作为唯一视觉焦点"],
    "recommended_copy": "数学错题怎么复盘？\n家长可用的3步检查清单",
}

DEMO_VIRAL_ANALYSIS = {
    "score": 86,
    "title_analysis": {
        "pain_point": "以反复出错和复习低效切入，痛点具体。",
        "target_audience": "明确面向需要陪学方法的家长。",
        "click_attraction": "问题句加数字清单，降低理解成本。",
    },
    "structure_analysis": {
        "opening": "用常见陪学场景建立共鸣，再指出问题不一定是粗心。",
        "middle": "按定位原因、拆解步骤、复盘反馈三段展开，每段给出动作。",
        "ending": "用轻量提问邀请交流，不制造焦虑或承诺结果。",
    },
    "viral_reasons": ["痛点场景具体", "信息结构清晰", "建议可以立即执行"],
    "copyable_template": "具体场景提问 → 纠正常见误区 → 3个可执行步骤 → 温和行动引导",
    "suggestions": ["标题避免结果承诺", "正文增加真实操作示例", "结尾保持低压力互动"],
}

DEMO_VIRAL_IMAGE_ANALYSIS = {
    "cover_text_structure": "问题句主标题 + 数字型方法提示 + 适用人群说明",
    "information_hierarchy": "一级信息是数学错题问题，二级信息是3步复盘方法，三级信息是适用人群。",
    "layout_method": "主标题集中在上方，数字重点居中，辅助说明放在下方形成三级阅读顺序。",
    "first_glance": "孩子错题反复，以及可以获得一套3步复盘方法。",
    "click_factors": ["直接命中错题反复的家长困扰", "用“3步”降低理解门槛"],
    "trust_building": "以清晰的方法步骤建立专业可信度，不依赖未经证实的成绩承诺。",
    "user_pain_expression": "直接写出孩子错题反复、复习没有抓手的具体困扰。",
    "conversion_elements": [],
    "reusable_template": "【具体学习问题】+【数字型方法】+【适用年级或人群】",
    "attraction_points": ["数字关键词形成视觉焦点", "标题与家长痛点直接相关"],
    "layout_structure": {
        "headline_position": "上方居中，两行内",
        "text_hierarchy": "主标题、数字重点、辅助说明三级",
        "information_density": "适中",
        "visual_focus": "“3步复盘”",
        "element_relationship": "浅色背景承托文字，红色只用于重点",
    },
    "copy_structure": {
        "target_audience": "小学高年级至初中学生家长",
        "pain_point": "错题反复、复习没有抓手",
        "credibility": "以方法步骤建立可信度，不虚构背书",
        "service_information": "Demo不展示价格或效果承诺",
    },
    "risk_points": ["避免“30天提高50分”等确定性效果表达"],
    "avoid_copying": ["未经证实的成绩数据", "绝对化承诺"],
    "reusable_elements": ["数字型信息层级", "问题句标题", "清单式内容结构"],
}

DEMO_PRE_PUBLISH_REPORT = {
    "score": 84,
    "title_analysis": {
        "strengths": ["目标人群和主题清晰", "具备明确的信息价值"],
        "problems": ["原始标题包含确定性效果承诺"],
        "suggestions": ["改用方法、场景或清单表达"],
    },
    "body_analysis": {
        "structure": "场景—原因—方法—行动，层级完整。",
        "user_pain": "准确覆盖家长对错题反复和学习节奏的关注。",
        "marketing_risk": "需删除保证性结果和未经确认的数据。",
    },
    "cover_analysis": {
        "click_attraction": "主题清晰，数字重点醒目。",
        "information_density": "适中，适合移动端快速阅读。",
        "suggestions": ["只保留一个核心卖点", "避免使用成绩提升承诺"],
    },
    "final_advice": ["使用安全版标题和正文", "发布前核对案例与数据来源", "保留温和互动引导"],
}

DEMO_NOTE_IMAGE_ANALYSIS = {
    "cover_theme": "数学错题复盘方法",
    "visual_elements": ["浅色信息卡", "红色数字重点", "三步清单"],
    "target_audience": "需要陪学方法的小学高年级至初中学生家长",
    "selling_direction": "提供可执行的学习复盘方法",
    "content_type": "学习方法分享",
    "teacher_cues": "以步骤拆解体现专业性，不使用虚构背书",
    "analysis_basis": "Demo结果基于脱敏示例封面文字与公开示例描述。",
}

DEMO_VIRAL_EXAMPLE_ANALYSIS = {
    "category": "教育方法",
    "opening_style": "从家长熟悉的陪学场景切入",
    "structure": ["提出具体问题", "解释常见误区", "给出三步方法", "温和互动"],
    "pain_expression": "用具体场景描述困扰，不放大焦虑",
    "emotional_trigger": "理解和可操作感",
    "teacher_ip_style": "专业、克制、有温度",
    "method_style": "清单化步骤",
    "service_style": "只介绍可确认的支持方式",
    "conversion_style": "邀请交流学习情况",
    "layout_style": "短句分段与数字小标题",
    "analysis_basis": "Demo结果来自脱敏案例结构，不复刻原文。",
}


def build_demo_note(expected_title_count: int = 5) -> dict[str, object]:
    count = max(1, min(expected_title_count, len(DEMO_TITLES)))
    return {
        "titles": DEMO_TITLES[:count],
        "body": (
            "孩子同一道题反复出错，不一定只是粗心。\n\n"
            "可以先做一次简单复盘：\n"
            "1️⃣ 找到卡住的具体步骤\n"
            "2️⃣ 让孩子说出自己的思路\n"
            "3️⃣ 隔天用一道同类题再确认\n\n"
            "比起反复刷题，先看清问题发生在哪里，往往更容易建立稳定的学习节奏。"
        ),
        "action": "你家更常遇到哪一种错题情况？可以先从一个具体步骤开始记录。",
        "comment_question": "你家孩子最常在哪一类数学题上反复出错？",
        "tags": ["学习方法", "数学学习", "错题复盘", "家长陪学", "教育内容"],
    }


def demo_result(value: T) -> T:
    """Return an isolated copy so session mutations never affect shared demo data."""
    return deepcopy(value)


def resolve_demo_or_live(demo_enabled: bool, demo_value: T, live_call: Callable[[], T]) -> T:
    """Guarantee that a live provider is not invoked while Demo mode is enabled."""
    if demo_enabled:
        return demo_result(demo_value)
    return live_call()
