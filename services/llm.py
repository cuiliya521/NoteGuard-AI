from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
LAST_ERROR = ""

SYSTEM_PROMPT = """
你是为小红书教育行业创作者服务的「AI 内容审核 + 安全改写」编辑。
你拥有教育行业文案、家长沟通、小红书内容规范、教育广告规范和内容审核经验。

改写目标：
不是简单删除风险词，而是在降低违规风险的同时，最大程度保留原文的转化能力、课程卖点、阅读吸引力和真实分享感。
输出应像真实的小红书教育老师写给家长的文案：有温度、有沟通感、有营销吸引力，但不过度承诺。

必须尽量保留的内容：
1. 科目：数学、英语、语文等。
2. 年级和学习阶段。
3. 真实学习场景。
4. 课程形式：1v1、一对一、陪练、辅导、线上学习等。
5. 方法特色：解题思路、学习方法、学习习惯、答题训练等。
6. 服务特点：学习支持、学习规划、个性化陪伴、阶段复盘等。
7. 原文的核心卖点和作者想表达的内容。

改写原则：
1. 优先保证阅读流畅和自然表达。
2. 可以调整语序、拆句、合并句子、补充连接词或整体重写一句。
3. 保持作者原本表达意图，不凭空新增师资、案例、优惠、价格、名额或不存在的服务。
4. 不要逐字替换，不要机械改写，不要把文案改成审核报告。
5. 不要为了规避风险而删除全部营销卖点；优先优化风险表达，保留课程价值。

风险词优化规则：
请结合上下文自然改写，不要生硬地逐词替换。可优先参考以下方向：
- 孩子 → 娃 / 学员
- 学生 → 学员
- 差生 → 基础薄弱 / 薄弱阶段
- 提分 → 学习效果提升 / 成绩改善
- 提高 XX 分 → 学习变化明显 / 学习表现提升
- 保证有效 → 根据情况调整 / 帮助提升

教育行业合规边界：
1. 禁止绝对化承诺、保证结果、虚假案例、夸大效果。
2. 避免保过、包过、保证提分、满分、第一名、冠军、状元、100%、最快、秒会等确定性或绝对化表达。
3. 可以保留“数学基础薄弱”“线上 1v1 陪练”“个性化学习支持”等正常卖点，但不得与结果保证绑定。
4. 对成绩、能力、学习效果的表达，改为过程性、支持性、可能性表达，不暗示确定结果。
5. 不要违规引导私信、加微信、报名、承诺名额或承诺结果。

结合规则库：
输入中的 risk_items 是当前程序传入的审核规则命中项，包含风险词、建议替换、原因。
请参考这些规则进行修改，但不要简单替换词语。
如果 risk_items 包含 suggestion，可参考其方向并结合上下文自然改写。
如果某个风险词没有 suggestion，应删除、弱化或改写为更安全的表达。
如果风险项属于卖点组合复核，优先弱化夸大效果部分，尽量保留正常课程卖点。

标题优化：
标题要符合小红书阅读习惯，自然、有信息量、有吸引力，不要像广告口号或审核说明。
可以使用疑问句、经验分享、方法分享、场景切入等形式。
例如，原题“孩子数学提分怎么办”，可改写为：
- “数学基础薄弱的娃，如何逐步建立解题思路？”
- “分享几个帮助学员改善数理学习状态的方法”
请根据上下文灵活改写，不要固定套模板。

正文优化：
正文要自然、像真人写，保持阅读节奏和家长沟通感。
保留科目、阶段、场景、课程形式、方法和服务特点。
不要只替换风险词；应将句子整体改写得顺畅、可信、有吸引力。

示例：
原文：本人专收数理差生，每天1小时线上1v1，从拖后腿到黑马！
不要改成：分享一个提升数理思维的方法。
更合适的方向：帮助数学基础薄弱娃建立解题思路，每天1小时线上1v1陪练，逐步改善学习状态。

最终自检：
1. 是否保留了原文的核心卖点和转化信息。
2. 是否仍包含效果承诺、保证结果、夸张宣传、违规营销或绝对化表达。
3. 是否避免了虚假案例和无法验证的说法。
4. 是否自然、有温度、有家长沟通感，且不像 AI 机械替换。
5. 是否已根据 risk_items 优化风险表达。

创作者资料：
如果输入中包含 creator_profile，只能使用其中明确填写的身份、科目、服务、价格、经历、公开案例和行动引导。未填写的信息不得补造，不得虚构带课数量、效果数据、家长反馈或个人经历。

输出要求：
1. 必须输出合法 JSON。
2. 不要输出 Markdown、代码块或 JSON 以外的解释。
3. 保持现有字段完全兼容。

输出 JSON：
{
"title":"",
"body":"",
"reason":""
}
""".strip()

TITLE_GENERATION_PROMPT = """
你是一名资深小红书教育赛道内容策划。你的任务是根据用户提供的教育内容和 risk_items，生成高点击、合规、适合家长用户阅读的标题。

标题必须具备：
1. 家长痛点：抓住成绩停滞、基础薄弱、学习习惯、陪伴困难等真实关注点。
2. 真实场景：保留科目、年级、学习阶段、日常学习场景或课程形式。
3. 情绪共鸣：让家长感到“这正是我家正在遇到的问题”。
4. 好奇心和具体问题：有点击吸引力，但不故弄玄虚。
5. 可读性：自然、清晰，像真实小红书教育老师或家长分享，不像硬广。

请按以下顺序生成恰好 5 个标题。titles 数组中的每一项只写标题正文，不要自行添加类型标签：
1. 痛点型：直击家长的具体学习困扰。
2. 好奇型：用一个合规的关键问题或容易忽略的点引发好奇。
3. 干货型：突出学习方法、观察角度或可分享的经验。
4. 老师经验型：体现真实教学观察或陪伴经验，不虚构资历。
5. 家长共鸣型：体现家长在陪学、沟通或学习状态上的共鸣。

标题规则：
1. 尽量保留原文中合规的年级、科目、学习场景、家长关注问题、1v1、陪练、辅导、方法特色和服务特点。
2. 参考 risk_items 避开当前风险表达，并自然改写，不要机械替换。
3. 不使用保证、必胜、逆袭、保过、包过、满分、100%有效、短期暴涨、30天提高多少分等绝对化或效果承诺表达。
4. 不虚构案例、结果、师资、价格、名额或服务。
5. 不要写成广告口号，不要使用夸张感叹号堆砌。
6. 不得虚构教学经历、带课人数、家长反馈、有效率、成绩数据、短期结果或任何用户未提供的事实。
7. 如果 creator_profile 为空，不要补造老师身份、课程价格、服务承诺或案例；如果有资料，只能使用资料中明确公开的信息。

示例方向：
不要：数学30天提高50分
可以：数学成绩一直上不去，可能忽略了这个关键问题

不要：专收差生
可以：帮助数学基础薄弱孩子找到学习方法

只输出合法 JSON，不要 Markdown、代码块或额外解释：
{"titles": ["标题1", "标题2", "标题3", "标题4", "标题5"]}
""".strip()

COVER_ANALYSIS_PROMPT = """
你是一名小红书教育赛道封面内容策划。请根据封面 OCR 识别文字和当前 risk_items，分析这张封面是否适合家长用户在手机端快速阅读，并给出合规、可执行的优化建议。

分析必须覆盖：
1. 标题吸引力：是否清楚、有具体问题、有点击意愿。
2. 家长痛点：是否命中真实学习困扰或陪学场景。
3. 信息量：是否有足够关键信息，是否堆砌或空泛。
4. 营销风险：是否包含效果承诺、绝对化表达或 risk_items 中的风险词。
5. 核心卖点：是否明确且容易被家长理解。
6. 字号和层级：主标题、补充信息是否适合手机端快速扫读。
7. 手机端阅读体验：文字是否适合短句、大字、快速扫读。

要求：
1. 不虚构图片中不存在的信息。
2. 推荐封面文案要简洁、适合手机端展示、面向家长用户，并避开效果承诺。
3. 点击吸引力用 1 到 5 的整数表示。
4. 评分范围是 0 到 100。
5. 存在问题和优化建议各给 1 到 3 条，语言具体、可执行。

只输出合法 JSON，不要 Markdown、代码块或额外解释：
{
  "score": 80,
  "attraction": 4,
  "dimensions": {
    "title_attraction": "",
    "parent_pain": "",
    "information_density": "",
    "marketing_risk": "",
    "core_selling_point": "",
    "visual_hierarchy": "",
    "mobile_readability": ""
  },
  "issues": [""],
  "suggestions": [""],
  "recommended_copy": ""
}
""".strip()

NOTE_GENERATION_PROMPT = """
你是一名资深小红书教育赛道内容策划。请根据用户提供的主题、creator_profile 和 generation_options，生成一篇面向家长用户、可直接发布的小红书教育笔记。

内容要求：
1. 以真实学习或陪学场景切入，准确呈现家长可能遇到的困扰。
2. 正文提供自然、具体的经验分享和可执行的观察或方法，不虚构个人经历、教学资历、数据或案例。
3. 语气像真实教育老师或家长分享，有温度、有节奏，不写成硬广或审核报告。
4. 标题有点击吸引力，但避免夸张标题党和过度营销。
5. 不使用保证、保过、包过、逆袭、满分、提分承诺、100%有效、短期暴涨、第一名、冠军、状元等违规营销或绝对化表达。
6. 不出现引导私信、加微信、限时名额、价格优惠等违规引导。
7. 标签须与主题相关、适合小红书使用，使用 # 开头。
8. 封面文案简短有力，适合手机端大字展示，面向家长，不使用效果承诺。
9. creator_profile 只包含用户确认可公开的资料。只能使用其中明确填写的内容；任何空白字段都不得虚构。
10. 如果用户选择加入个人介绍、服务信息或行动引导，只能使用 creator_profile 中对应的已填写资料。价格、经历、案例、数据、家长反馈和结果必须来自 creator_profile，不能自行补造。
11. 正文必须完整从开头钩子开始，不得以残句或句中片段开头。正文应依次包含：开头钩子、家长痛点、方法或观点、可用的创作者经验/身份、可选服务信息、自然行动引导。
12. 不写空泛句子；优先使用与主题和用户已填写资料有关的具体学习场景。

只输出合法 JSON，不要 Markdown、代码块或额外解释：
{
  "titles": ["标题1", "标题2", "标题3"],
  "body": "完整正文",
  "tags": ["#标签1", "#标签2", "#标签3", "#标签4", "#标签5"],
  "cover_copy": "封面文案"
}
""".strip()

VIRAL_NOTE_ANALYSIS_PROMPT = """
你是一名资深小红书教育赛道运营专家。请拆解用户提供的一篇教育类小红书笔记，分析其传播潜力与可借鉴的写法。

分析要求：
1. 不要做普通摘要，要像运营复盘一样指出内容为什么容易被点击、读完、收藏或互动。
2. 标题分析必须分别说明：家长痛点、目标人群、点击吸引力。
3. 内容结构必须按开头、中段、结尾分别拆解其角色、优点或问题。
4. 爆款原因给出 2 到 4 条具体判断，紧扣原文，不虚构数据、传播量或作者背景。
5. 可复制模板要保留可套用的结构，用【主题】、【家长困扰】等占位符表达，不能照抄原文。
6. 优化建议给出 2 到 4 条可执行建议，帮助教育创作者把内容做得更清晰、更有吸引力且合规。
7. 避免鼓励夸大承诺、绝对化宣传、虚假案例或违规营销。
8. 爆款评分范围为 0 到 100，基于标题、结构、共鸣、信息价值和可读性综合判断。

只输出合法 JSON，不要 Markdown、代码块或额外解释：
{
  "score": 80,
  "title_analysis": {
    "pain_point": "",
    "target_audience": "",
    "click_attraction": ""
  },
  "structure_analysis": {
    "opening": "",
    "middle": "",
    "ending": ""
  },
  "viral_reasons": [""],
  "copyable_template": "",
  "suggestions": [""]
}
""".strip()

PRE_PUBLISH_REPORT_PROMPT = """
你是一名专业的小红书教育赛道运营顾问。请根据用户的标题、正文、风险检测结果、安全评分、安全改写和封面分析，出具一份发布前体检报告。

工作要求：
1. 这不是普通总结。请从内容质量、家长共鸣、点击吸引力、转化表达、合规风险和手机端阅读体验综合判断。
2. 标题分析应分别给出优点、问题和可执行的修改建议。
3. 正文分析应明确说明内容结构、用户痛点和营销风险。
4. 封面分析应说明点击吸引力、信息量和优化建议。没有封面分析数据时，明确标注“未提供封面分析”，不要臆测图片内容。
5. 最终发布建议应给出 2 到 4 条按优先级排序的建议，包含是否适合当前发布，以及发布前应优先调整什么。
6. 对风险项保持严谨：不得鼓励效果承诺、夸大宣传、虚假案例、绝对化表达或违规引导。
7. 综合评分范围为 0 到 100，综合衡量合规安全、表达清晰度、家长共鸣和发布完成度。

只输出合法 JSON，不要 Markdown、代码块或额外解释：
{
  "score": 80,
  "title_analysis": {
    "strengths": [""],
    "problems": [""],
    "suggestions": [""]
  },
  "body_analysis": {
    "structure": "",
    "user_pain": "",
    "marketing_risk": ""
  },
  "cover_analysis": {
    "click_attraction": "",
    "information_density": "",
    "suggestions": [""]
  },
  "final_advice": [""]
}
""".strip()


def load_env() -> bool:
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        if not ENV_PATH.exists():
            return False

        loaded = False
        for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ[key] = value
                loaded = True

        return loaded

    return load_dotenv(ENV_PATH, override=True)


def set_last_error(message: str) -> None:
    global LAST_ERROR
    LAST_ERROR = message
    if message:
        print(f"DeepSeek rewrite failed: {message}")


def get_last_error() -> str:
    return LAST_ERROR


def mask_key(api_key: str | None) -> str:
    if not api_key:
        return ""
    return api_key[:8]


def get_deepseek_api_key() -> str:
    load_env()
    return (os.getenv("DEEPSEEK_API_KEY") or "").strip()


def print_deepseek_diagnostics(api_key: str | None) -> None:
    print(
        "DeepSeek config: "
        f"env_path={ENV_PATH}, "
        f"env_exists={ENV_PATH.exists()}, "
        f"key_loaded={bool(api_key)}, "
        f"key_prefix={mask_key(api_key)}, "
        f"key_length={len(api_key or '')}, "
        f"base_url={DEEPSEEK_BASE_URL}, "
        f"model={DEEPSEEK_MODEL}"
    )


def normalize_risk_items(risk_items: list[Any]) -> list[dict[str, str]]:
    normalized_items: list[dict[str, str]] = []
    for item in risk_items:
        if isinstance(item, dict):
            term = str(item.get("term") or item.get("word") or item.get("风险词") or "")
            category = str(item.get("category") or item.get("分类") or "")
            reason = str(item.get("reason") or item.get("原因") or "")
            suggestion = str(item.get("suggestion") or item.get("建议替换") or "")
        else:
            term = str(getattr(item, "term", ""))
            category = str(getattr(item, "category", ""))
            reason = str(getattr(item, "reason", ""))
            suggestion = str(getattr(item, "suggestion", ""))

        if not term:
            continue

        normalized_items.append(
            {
                "term": term,
                "category": category,
                "reason": reason,
                "suggestion": suggestion,
            }
        )

    return normalized_items


def parse_json_response(content: str) -> dict[str, str] | None:
    cleaned_content = content.strip()
    if not cleaned_content:
        set_last_error("DeepSeek 返回内容为空")
        return None

    if cleaned_content.startswith("```"):
        cleaned_content = cleaned_content.strip("`").strip()
        if cleaned_content.startswith("json"):
            cleaned_content = cleaned_content[4:].strip()

    try:
        parsed = json.loads(cleaned_content)
    except json.JSONDecodeError as error:
        set_last_error(f"DeepSeek 返回内容不是合法 JSON：{error.msg}")
        return None

    if not isinstance(parsed, dict):
        set_last_error("DeepSeek 返回 JSON 不是对象")
        return None

    return {
        "title": str(parsed.get("title", "")),
        "body": str(parsed.get("body", "")),
        "reason": str(parsed.get("reason", "")),
    }


def parse_title_response(content: str) -> list[str] | None:
    cleaned_content = content.strip()
    if cleaned_content.startswith("```"):
        cleaned_content = cleaned_content.strip("`").strip()
        if cleaned_content.startswith("json"):
            cleaned_content = cleaned_content[4:].strip()

    try:
        parsed = json.loads(cleaned_content)
    except json.JSONDecodeError as error:
        set_last_error(f"DeepSeek 标题返回不是合法 JSON：{error.msg}")
        return None

    titles = parsed.get("titles") if isinstance(parsed, dict) else None
    if not isinstance(titles, list):
        set_last_error("DeepSeek 标题返回缺少 titles 列表")
        return None

    cleaned_titles = [str(title).strip() for title in titles if str(title).strip()]
    if len(cleaned_titles) != 5:
        set_last_error("DeepSeek 未返回 5 个标题候选")
        return None

    return cleaned_titles


def parse_note_generation_response(content: str) -> dict[str, Any] | None:
    cleaned_content = content.strip()
    if cleaned_content.startswith("```"):
        cleaned_content = cleaned_content.strip("`").strip()
        if cleaned_content.startswith("json"):
            cleaned_content = cleaned_content[4:].strip()

    try:
        parsed = json.loads(cleaned_content)
    except json.JSONDecodeError as error:
        set_last_error(f"DeepSeek 笔记生成返回不是合法 JSON：{error.msg}")
        return None

    if not isinstance(parsed, dict):
        set_last_error("DeepSeek 笔记生成返回不是对象")
        return None

    def clean_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    titles = clean_list(parsed.get("titles"))
    tags = clean_list(parsed.get("tags"))
    body = str(parsed.get("body", "")).strip()
    cover_copy = str(parsed.get("cover_copy", "")).strip()
    if len(titles) != 3 or len(tags) != 5 or not body or not cover_copy:
        set_last_error("DeepSeek 笔记生成结果不完整，请重试")
        return None

    return {
        "titles": titles,
        "body": body,
        "tags": tags,
        "cover_copy": cover_copy,
    }


def parse_viral_note_analysis_response(content: str) -> dict[str, Any] | None:
    cleaned_content = content.strip()
    if cleaned_content.startswith("```"):
        cleaned_content = cleaned_content.strip("`").strip()
        if cleaned_content.startswith("json"):
            cleaned_content = cleaned_content[4:].strip()

    try:
        parsed = json.loads(cleaned_content)
    except json.JSONDecodeError as error:
        set_last_error(f"DeepSeek 爆款拆解返回不是合法 JSON：{error.msg}")
        return None

    if not isinstance(parsed, dict):
        set_last_error("DeepSeek 爆款拆解返回不是对象")
        return None

    title_analysis = parsed.get("title_analysis")
    structure_analysis = parsed.get("structure_analysis")
    if not isinstance(title_analysis, dict) or not isinstance(structure_analysis, dict):
        set_last_error("DeepSeek 爆款拆解结果缺少分析结构")
        return None

    try:
        score = max(0, min(100, int(parsed.get("score", 0))))
    except (TypeError, ValueError):
        set_last_error("DeepSeek 爆款拆解评分格式错误")
        return None

    def clean_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()][0:4]

    template = str(parsed.get("copyable_template", "")).strip()
    if not template:
        set_last_error("DeepSeek 爆款拆解结果缺少可复制模板")
        return None

    return {
        "score": score,
        "title_analysis": {
            "pain_point": str(title_analysis.get("pain_point", "")).strip(),
            "target_audience": str(title_analysis.get("target_audience", "")).strip(),
            "click_attraction": str(title_analysis.get("click_attraction", "")).strip(),
        },
        "structure_analysis": {
            "opening": str(structure_analysis.get("opening", "")).strip(),
            "middle": str(structure_analysis.get("middle", "")).strip(),
            "ending": str(structure_analysis.get("ending", "")).strip(),
        },
        "viral_reasons": clean_list(parsed.get("viral_reasons")),
        "copyable_template": template,
        "suggestions": clean_list(parsed.get("suggestions")),
    }


def parse_pre_publish_report_response(content: str) -> dict[str, Any] | None:
    cleaned_content = content.strip()
    if cleaned_content.startswith("```"):
        cleaned_content = cleaned_content.strip("`").strip()
        if cleaned_content.startswith("json"):
            cleaned_content = cleaned_content[4:].strip()

    try:
        parsed = json.loads(cleaned_content)
    except json.JSONDecodeError as error:
        set_last_error(f"DeepSeek 体检报告返回不是合法 JSON：{error.msg}")
        return None

    if not isinstance(parsed, dict):
        set_last_error("DeepSeek 体检报告返回不是对象")
        return None

    title_analysis = parsed.get("title_analysis")
    body_analysis = parsed.get("body_analysis")
    cover_analysis = parsed.get("cover_analysis")
    if not all(isinstance(section, dict) for section in (title_analysis, body_analysis, cover_analysis)):
        set_last_error("DeepSeek 体检报告结果缺少分析结构")
        return None

    try:
        score = max(0, min(100, int(parsed.get("score", 0))))
    except (TypeError, ValueError):
        set_last_error("DeepSeek 体检报告评分格式错误")
        return None

    def clean_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()][0:4]

    return {
        "score": score,
        "title_analysis": {
            "strengths": clean_list(title_analysis.get("strengths")),
            "problems": clean_list(title_analysis.get("problems")),
            "suggestions": clean_list(title_analysis.get("suggestions")),
        },
        "body_analysis": {
            "structure": str(body_analysis.get("structure", "")).strip(),
            "user_pain": str(body_analysis.get("user_pain", "")).strip(),
            "marketing_risk": str(body_analysis.get("marketing_risk", "")).strip(),
        },
        "cover_analysis": {
            "click_attraction": str(cover_analysis.get("click_attraction", "")).strip(),
            "information_density": str(cover_analysis.get("information_density", "")).strip(),
            "suggestions": clean_list(cover_analysis.get("suggestions")),
        },
        "final_advice": clean_list(parsed.get("final_advice")),
    }


def parse_cover_analysis_response(content: str) -> dict[str, Any] | None:
    cleaned_content = content.strip()
    if cleaned_content.startswith("```"):
        cleaned_content = cleaned_content.strip("`").strip()
        if cleaned_content.startswith("json"):
            cleaned_content = cleaned_content[4:].strip()

    try:
        parsed = json.loads(cleaned_content)
    except json.JSONDecodeError as error:
        set_last_error(f"DeepSeek 封面分析返回不是合法 JSON：{error.msg}")
        return None

    if not isinstance(parsed, dict):
        set_last_error("DeepSeek 封面分析返回不是对象")
        return None

    dimensions = parsed.get("dimensions")
    if not isinstance(dimensions, dict):
        set_last_error("DeepSeek 封面分析返回缺少 dimensions")
        return None

    try:
        score = max(0, min(100, int(parsed.get("score", 0))))
        attraction = max(1, min(5, int(parsed.get("attraction", 1))))
    except (TypeError, ValueError):
        set_last_error("DeepSeek 封面分析评分格式错误")
        return None

    def clean_items(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()][0:3]

    return {
        "score": score,
        "attraction": attraction,
        "dimensions": {
            "title_attraction": str(dimensions.get("title_attraction", "")),
            "parent_pain": str(dimensions.get("parent_pain", "")),
        "information_density": str(dimensions.get("information_density", "")),
        "marketing_risk": str(dimensions.get("marketing_risk", "")),
        "core_selling_point": str(dimensions.get("core_selling_point", "")),
        "visual_hierarchy": str(dimensions.get("visual_hierarchy", "")),
        "mobile_readability": str(dimensions.get("mobile_readability", "")),
        },
        "issues": clean_items(parsed.get("issues")),
        "suggestions": clean_items(parsed.get("suggestions")),
        "recommended_copy": str(parsed.get("recommended_copy", "")),
    }


def analyze_cover(
    cover_text: str,
    risk_items: list[Any],
) -> dict[str, Any] | None:
    set_last_error("")
    api_key = get_deepseek_api_key()
    print_deepseek_diagnostics(api_key)
    if not api_key:
        set_last_error(f"未读取到 DEEPSEEK_API_KEY，请检查 {ENV_PATH}")
        return None

    try:
        from openai import OpenAI
    except ModuleNotFoundError:
        set_last_error("未安装 openai 依赖，请先安装 requirements.txt")
        return None

    user_payload = {
        "cover_text": cover_text,
        "risk_items": normalize_risk_items(risk_items),
    }

    try:
        client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": COVER_ANALYSIS_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
            temperature=0.4,
        )
        content = response.choices[0].message.content or ""
        return parse_cover_analysis_response(content)
    except Exception as error:
        set_last_error(f"{type(error).__name__}: {error}")
        return None


def generate_title_candidates(
    title: str,
    body: str,
    risk_items: list[Any],
    creator_profile: dict[str, str] | None = None,
) -> list[str] | None:
    set_last_error("")
    api_key = get_deepseek_api_key()
    print_deepseek_diagnostics(api_key)
    if not api_key:
        set_last_error(f"未读取到 DEEPSEEK_API_KEY，请检查 {ENV_PATH}")
        return None

    try:
        from openai import OpenAI
    except ModuleNotFoundError:
        set_last_error("未安装 openai 依赖，请先安装 requirements.txt")
        return None

    user_payload = {
        "title": title or "",
        "body": body or "",
        "risk_items": normalize_risk_items(risk_items),
        "creator_profile": creator_profile or {},
    }

    try:
        client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": TITLE_GENERATION_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
            temperature=0.8,
        )
        content = response.choices[0].message.content or ""
        return parse_title_response(content)
    except Exception as error:
        set_last_error(f"{type(error).__name__}: {error}")
        return None


def generate_xiaohongshu_note(
    topic: str,
    creator_profile: dict[str, str] | None = None,
    generation_options: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    set_last_error("")
    api_key = get_deepseek_api_key()
    print_deepseek_diagnostics(api_key)
    if not api_key:
        set_last_error(f"未读取到 DEEPSEEK_API_KEY，请检查 {ENV_PATH}")
        return None

    try:
        from openai import OpenAI
    except ModuleNotFoundError:
        set_last_error("未安装 openai 依赖，请先安装 requirements.txt")
        return None

    try:
        client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": NOTE_GENERATION_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "topic": topic,
                            "creator_profile": creator_profile or {},
                            "generation_options": generation_options or {},
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.8,
        )
        content = response.choices[0].message.content or ""
        return parse_note_generation_response(content)
    except Exception as error:
        set_last_error(f"{type(error).__name__}: {error}")
        return None


def analyze_viral_note(title: str, body: str) -> dict[str, Any] | None:
    set_last_error("")
    api_key = get_deepseek_api_key()
    print_deepseek_diagnostics(api_key)
    if not api_key:
        set_last_error(f"未读取到 DEEPSEEK_API_KEY，请检查 {ENV_PATH}")
        return None

    try:
        from openai import OpenAI
    except ModuleNotFoundError:
        set_last_error("未安装 openai 依赖，请先安装 requirements.txt")
        return None

    user_payload = {"title": title, "body": body}
    try:
        client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": VIRAL_NOTE_ANALYSIS_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            temperature=0.5,
        )
        content = response.choices[0].message.content or ""
        return parse_viral_note_analysis_response(content)
    except Exception as error:
        set_last_error(f"{type(error).__name__}: {error}")
        return None


def generate_pre_publish_report(
    title: str,
    body: str,
    risk_items: list[Any],
    safety_score: int,
    safe_rewrite: dict[str, str],
    cover_analysis: dict[str, Any] | None,
) -> dict[str, Any] | None:
    set_last_error("")
    api_key = get_deepseek_api_key()
    print_deepseek_diagnostics(api_key)
    if not api_key:
        set_last_error(f"未读取到 DEEPSEEK_API_KEY，请检查 {ENV_PATH}")
        return None

    try:
        from openai import OpenAI
    except ModuleNotFoundError:
        set_last_error("未安装 openai 依赖，请先安装 requirements.txt")
        return None

    user_payload = {
        "title": title,
        "body": body,
        "risk_items": normalize_risk_items(risk_items),
        "safety_score": safety_score,
        "safe_rewrite": safe_rewrite,
        "cover_analysis": cover_analysis,
    }
    try:
        client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": PRE_PUBLISH_REPORT_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            temperature=0.4,
        )
        content = response.choices[0].message.content or ""
        return parse_pre_publish_report_response(content)
    except Exception as error:
        set_last_error(f"{type(error).__name__}: {error}")
        return None


def rewrite_content(
    title: str,
    body: str,
    risk_items: list[Any],
    creator_profile: dict[str, str] | None = None,
) -> dict[str, str] | None:
    set_last_error("")
    api_key = get_deepseek_api_key()
    print_deepseek_diagnostics(api_key)
    if not api_key:
        set_last_error(f"未读取到 DEEPSEEK_API_KEY，请检查 {ENV_PATH}")
        return None

    try:
        from openai import OpenAI
    except ModuleNotFoundError:
        set_last_error("未安装 openai 依赖，请先安装 requirements.txt")
        return None

    user_payload = {
        "title": title or "",
        "body": body or "",
        "risk_items": normalize_risk_items(risk_items),
        "creator_profile": creator_profile or {},
    }

    try:
        client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
            temperature=0.2,
        )
        content = response.choices[0].message.content or ""
        parsed_response = parse_json_response(content)
        if not parsed_response:
            return None
        if not parsed_response["title"] and not parsed_response["body"]:
            set_last_error("DeepSeek 返回 JSON 中 title 和 body 都为空")
            return None
        return parsed_response
    except Exception as error:
        set_last_error(f"{type(error).__name__}: {error}")
        return None
