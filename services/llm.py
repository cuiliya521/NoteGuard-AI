from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from services.creator_profile import build_creator_profile_context


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
2. 只做消除审核风险所必需的最小修改，不重写未命中风险的正常句子。
3. 保持作者原本表达意图，不凭空新增师资、案例、优惠、价格、名额或不存在的服务。
4. 不要逐字替换，不要机械改写，不要把文案改成审核报告。
5. 不要为了规避风险而删除全部营销卖点；优先优化风险表达，保留课程价值。
6. 严格保留原有段落顺序、换行、表情、标签和正常课程卖点，不重新组织整篇文章结构。
7. 这是“格式锁定”任务：标题结构、段落数量、段落顺序和换行位置必须与原文一致。
8. 未命中 risk_items 的文字、emoji、标签、标点、老师介绍和正常课程卖点必须原样保留。
9. 不允许合并、拆分、调换或补写段落；不允许为了更“像小红书”而重写正常内容。

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
保留原标题的句式、语气、标点和核心信息，只修改其中命中 risk_items 的表达。
不要把原标题改成另一种标题类型，不要额外增加情绪、疑问、数据或营销卖点。

正文优化：
正文要自然、像真人写，保持阅读节奏和家长沟通感。
保留科目、阶段、场景、课程形式、方法和服务特点。
仅在命中风险的句子中做最小必要调整；正常句子、原有换行、表情和标签必须原样保留。

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
你是一名资深小红书教育赛道图文内容策划。请根据 source_materials、creator_profile 和 generation_options，生成面向家长、适合直接发布的标题与完整文案。

素材使用：
1. 综合使用当前标题、正文、封面 OCR 文字、用户修正后的封面文字和补充主题，不要求素材字段全部存在。
2. 用户修正后的封面文字优先于原始 OCR；不得臆测图片中未识别的信息。
3. creator_profile 是唯一允许使用的身份、资历、科目、教学形式、时长、价格、案例和行动方式来源。
4. 只有 generation_options 明确允许时，才把老师介绍、课程信息写入正文。
5. source_materials.cover_analysis 和 source_materials.image_analysis 是图片分析结果；只能使用其中有素材依据的结论。

真实性红线：
1. creator_profile 未填写的经历、学员数量、家长反馈、教学成果、价格、案例和数据一律不得生成。
2. 不得虚构提分数据、真实案例、CTR、曝光、留资、转化率或“家长都认可”等无法验证的事实。
3. 案例复盘型仅能使用 source_materials 或 creator_profile 中真实存在的案例素材；没有案例时改为方法复盘，不补造人物和结果。

内容方向：
严格遵循 generation_options.content_direction 和 structure_guidance。不同方向必须使用明显不同的切入方式与段落结构。
可参考家长痛点、老师身份与专业背书、教学理念、具体方法、课程服务、真实素材中的感受、形式时长价格和自然行动引导，但不要每次使用相同顺序。
禁止固定使用“有个家长跟我说”等开头，禁止重复固定句式、固定表情或固定分隔符，不照抄任何示例。
当 generation_options.generation_mode 为“根据图片生成”时：
1. 先使用 source_materials.image_analysis 中的封面主题、目标人群、卖点方向和内容类型确定写作角度。
2. 正文必须按“用户痛点 → 已确认的老师身份背书 → 课程/服务介绍 → 已确认的优势 → 行动引导”展开，不调换顺序。
3. creator_profile 中没有的老师身份或背书必须省略，不得为了补齐结构而虚构。
4. 图片中无法从 OCR 或已确认资料证实的人物、场景、案例和效果不得写入文案。
5. 不得生成成绩保证、短期效果承诺或任何未经用户确认的转化数据。

正文要求：
1. 正文目标字数遵循 generation_options.length_range，且绝对不超过 1000 字。
2. 必须有完整开头、具体用户痛点、核心观点或方法和完整结尾，不得从残句开始或突然中断。
3. 写作自然、有经验分享感和转化力，但不空泛、不堆砌卖点、不过度营销。
4. 可以灵活调整场景、观点、方法和服务信息的顺序，避免连续使用相同句式。
5. 生成一条独立、简短、自然的 action；是否加入最终发布版由页面控制。

标题要求：
生成恰好 5 个不同类型标题，依次为痛点型、好奇型、干货型、老师经验型、家长共鸣型。
标题保留真实科目、年级、学习场景和家长问题，但不得出现保证提分、30天提高50分、一定有效、百分百、必然逆袭或虚构数据。

合规要求：
1. 同时参考 risk_items 和 source_materials.rule_constraints，避开当前启用规则中的风险表达。
2. 不使用绝对化承诺、保证结果、虚假案例、违规引导和夸大宣传。
3. “孩子”“数学”等普通教育词可自然使用，不要把普通词自行升级成严重风险。
4. 标签与主题相关，使用 # 开头，生成恰好 5 个。

只输出合法 JSON，不要 Markdown、代码块或额外解释：
{
  "titles": ["标题1", "标题2", "标题3", "标题4", "标题5"],
  "body": "完整正文",
  "action": "简短行动引导",
  "tags": ["#标签1", "#标签2", "#标签3", "#标签4", "#标签5"]
}
""".strip()

NOTE_IMAGE_ANALYSIS_PROMPT = """
你是小红书教育赛道内容策划。请在生成完整笔记之前，先分析用户已确认的图片素材。

你会收到 image_context、creator_profile、risk_items 和 rule_constraints。
能力边界：
1. 当前模型不直接接收图片像素，只能根据 OCR 文字、用户修正文字、图片尺寸比例和已有封面分析作出判断。
2. visual_elements 只能列出已确认的文字元素、信息层级方向或尺寸比例特征；不得虚构人物、背景、颜色、表情和版式细节。
3. target_audience、selling_direction 和 content_type 必须有输入文字依据。
4. creator_profile 只能帮助理解用户已保存的真实定位，不得补造经历、案例、人数、成绩和效果数据。
5. 参考 risk_items 标记可能需要在生成阶段规避的方向，不得引入成绩保证或短期效果承诺。
6. rule_constraints 是当前 rules.json 中启用的审核规则，分析卖点方向时必须主动避开其中的风险表达。

只输出合法 JSON：
{
  "cover_theme": "",
  "visual_elements": [""],
  "target_audience": "",
  "selling_direction": "",
  "content_type": "",
  "analysis_basis": ""
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

VIRAL_IMAGE_ANALYSIS_PROMPT = """
你是一名小红书教育赛道内容策划，请对爆款拆解中的主图进行“基于文字与基础元数据的图片拆解”。

能力边界：
1. 当前没有多模态视觉模型。你只能使用 OCR 文字、图片尺寸、宽高比、格式、用户补充描述和 risk_items。
2. 不得声称真实识别了人物表情、字体大小、颜色对比、具体版式细节或图片中未提供的对象。
3. 涉及主标题位置、文字层级、视觉焦点和人物/文字/背景关系时，必须明确使用“可能”“建议”“从现有文字推断”等措辞。
4. 不得生成或推测 CTR、曝光、留资、转化率、爆款概率和平台推荐机制。

分析要求：
1. 吸引点：基于 OCR 文案判断第一眼可能吸引家长的内容。
2. 版式结构：结合尺寸和宽高比，对主标题位置、文字层级、信息密度、视觉焦点、人物/文字/背景关系给出推断或建议。
3. 文案结构：分析目标人群、家长痛点、老师或课程背书，以及价格、时长、1V1 等服务信息是否在已提供文字中出现。
4. 风险点：结合 risk_items 判断夸大承诺或风险表达。
5. 分别列出可复用元素和不建议照搬的内容。
6. 只能评价点击潜力、可能的吸引点和可复用方向，不能虚构表现数据。

只输出合法 JSON，不要 Markdown、代码块或额外解释：
{
  "attraction_points": [""],
  "layout_structure": {
    "headline_position": "",
    "text_hierarchy": "",
    "information_density": "",
    "visual_focus": "",
    "element_relationship": ""
  },
  "copy_structure": {
    "target_audience": "",
    "pain_point": "",
    "credibility": "",
    "service_information": ""
  },
  "risk_points": [""],
  "reusable_elements": [""],
  "avoid_copying": [""]
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
    action = str(parsed.get("action", "")).strip()
    if len(titles) != 5 or len(tags) != 5 or not body or not action:
        set_last_error("DeepSeek 笔记生成结果不完整，请重试")
        return None

    return {
        "titles": titles,
        "body": body,
        "action": action,
        "tags": tags,
    }


def parse_note_image_analysis_response(content: str) -> dict[str, Any] | None:
    cleaned_content = content.strip()
    if cleaned_content.startswith("```"):
        cleaned_content = cleaned_content.strip("`").strip()
        if cleaned_content.startswith("json"):
            cleaned_content = cleaned_content[4:].strip()
    try:
        parsed = json.loads(cleaned_content)
    except json.JSONDecodeError as error:
        set_last_error(f"DeepSeek 图片素材分析不是合法 JSON：{error.msg}")
        return None
    if not isinstance(parsed, dict):
        set_last_error("DeepSeek 图片素材分析结果不是对象")
        return None

    visual_elements = parsed.get("visual_elements", [])
    if not isinstance(visual_elements, list):
        visual_elements = []
    result = {
        "cover_theme": str(parsed.get("cover_theme", "")).strip(),
        "visual_elements": [str(item).strip() for item in visual_elements if str(item).strip()],
        "target_audience": str(parsed.get("target_audience", "")).strip(),
        "selling_direction": str(parsed.get("selling_direction", "")).strip(),
        "content_type": str(parsed.get("content_type", "")).strip(),
        "analysis_basis": str(parsed.get("analysis_basis", "")).strip(),
    }
    if not all(result[key] for key in ("cover_theme", "target_audience", "selling_direction", "content_type")):
        set_last_error("DeepSeek 图片素材分析结果不完整")
        return None
    return result


def build_note_generation_payload(
    topic: str,
    creator_profile: dict[str, str] | None,
    generation_options: dict[str, Any] | None,
    source_materials: dict[str, Any] | None,
    risk_items: list[Any] | None,
) -> dict[str, Any]:
    return {
        "topic": (topic or "").strip(),
        "source_materials": source_materials or {},
        "creator_profile": build_creator_profile_context(creator_profile),
        "generation_options": generation_options or {},
        "risk_items": normalize_risk_items(risk_items or []),
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


def parse_viral_image_analysis_response(content: str) -> dict[str, Any] | None:
    cleaned_content = content.strip()
    if cleaned_content.startswith("```"):
        cleaned_content = cleaned_content.strip("`").strip()
        if cleaned_content.startswith("json"):
            cleaned_content = cleaned_content[4:].strip()

    try:
        parsed = json.loads(cleaned_content)
    except json.JSONDecodeError as error:
        set_last_error(f"DeepSeek 图片拆解返回不是合法 JSON：{error.msg}")
        return None

    if not isinstance(parsed, dict):
        set_last_error("DeepSeek 图片拆解返回不是对象")
        return None
    layout = parsed.get("layout_structure")
    copy_structure = parsed.get("copy_structure")
    if not isinstance(layout, dict) or not isinstance(copy_structure, dict):
        set_last_error("DeepSeek 图片拆解结果缺少分析结构")
        return None

    def clean_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()][:5]

    result = {
        "attraction_points": clean_list(parsed.get("attraction_points")),
        "layout_structure": {
            key: str(layout.get(key, "")).strip()
            for key in (
                "headline_position",
                "text_hierarchy",
                "information_density",
                "visual_focus",
                "element_relationship",
            )
        },
        "copy_structure": {
            key: str(copy_structure.get(key, "")).strip()
            for key in (
                "target_audience",
                "pain_point",
                "credibility",
                "service_information",
            )
        },
        "risk_points": clean_list(parsed.get("risk_points")),
        "reusable_elements": clean_list(parsed.get("reusable_elements")),
        "avoid_copying": clean_list(parsed.get("avoid_copying")),
    }
    forbidden_metrics = ("ctr", "曝光", "留资", "转化率", "爆款概率")
    serialized = json.dumps(result, ensure_ascii=False).lower()
    if any(term in serialized for term in forbidden_metrics):
        set_last_error("图片拆解包含无法验证的表现数据，已拒绝展示")
        return None
    return result


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
    source_materials: dict[str, Any] | None = None,
    risk_items: list[Any] | None = None,
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
                        build_note_generation_payload(
                            topic,
                            creator_profile,
                            generation_options,
                            source_materials,
                            risk_items,
                        ),
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


def analyze_note_image_source(
    image_context: dict[str, Any],
    creator_profile: dict[str, str] | None = None,
    risk_items: list[Any] | None = None,
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

    payload = {
        "image_context": image_context,
        "creator_profile": build_creator_profile_context(creator_profile),
        "risk_items": normalize_risk_items(risk_items or []),
        "rule_constraints": image_context.get("rule_constraints", []),
    }
    try:
        client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": NOTE_IMAGE_ANALYSIS_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.3,
        )
        content = response.choices[0].message.content or ""
        return parse_note_image_analysis_response(content)
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


def analyze_viral_image(image_context: dict[str, Any]) -> dict[str, Any] | None:
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
                {"role": "system", "content": VIRAL_IMAGE_ANALYSIS_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(image_context, ensure_ascii=False),
                },
            ],
            temperature=0.4,
        )
        content = response.choices[0].message.content or ""
        return parse_viral_image_analysis_response(content)
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
