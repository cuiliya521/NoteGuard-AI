from __future__ import annotations

import json
import logging
import os
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from services.creator_profile import build_creator_profile_context


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
IMAGE_ANALYSIS_TIMEOUT_SECONDS = 20.0
IMAGE_ANALYSIS_MAX_ATTEMPTS = 3
LAST_ERROR = ""
LOGGER = logging.getLogger(__name__)


def _image_request_metadata(payload: dict[str, Any]) -> tuple[str, int]:
    context = payload.get("image_context") if isinstance(payload.get("image_context"), dict) else payload
    width = int(context.get("image_width") or 0) if isinstance(context, dict) else 0
    height = int(context.get("image_height") or 0) if isinstance(context, dict) else 0
    image_size = f"{width}x{height}" if width and height else "unknown"
    byte_size = int(context.get("image_bytes_size") or 0) if isinstance(context, dict) else 0
    return image_size, byte_size


def _request_image_analysis(
    OpenAI: Any,
    api_key: str,
    system_prompt: str,
    payload: dict[str, Any],
    temperature: float,
) -> str:
    """Analyze OCR text and basic image metadata with a text-only model.

    The payload intentionally contains no image URL or image bytes. A future
    visual provider remains isolated in ``services.vision_text``.
    """
    image_size, byte_size = _image_request_metadata(payload)
    last_error: Exception | None = None
    for attempt in range(1, IMAGE_ANALYSIS_MAX_ATTEMPTS + 1):
        started_at = time.perf_counter()
        try:
            client = OpenAI(
                api_key=api_key,
                base_url=DEEPSEEK_BASE_URL,
                timeout=IMAGE_ANALYSIS_TIMEOUT_SECONDS,
                max_retries=0,
            )
            response = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                temperature=temperature,
            )
            elapsed = time.perf_counter() - started_at
            LOGGER.info(
                "Image text-context analysis succeeded model=%s image=%s bytes=%s attempt=%s elapsed=%.3fs",
                DEEPSEEK_MODEL,
                image_size,
                byte_size,
                attempt,
                elapsed,
            )
            return response.choices[0].message.content or ""
        except Exception as error:
            last_error = error
            elapsed = time.perf_counter() - started_at
            LOGGER.warning(
                "Image text-context analysis failed model=%s image=%s bytes=%s attempt=%s elapsed=%.3fs error=%s",
                DEEPSEEK_MODEL,
                image_size,
                byte_size,
                attempt,
                elapsed,
                type(error).__name__,
            )
            if attempt < IMAGE_ANALYSIS_MAX_ATTEMPTS:
                time.sleep(0.25 * attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Image text-context analysis failed")

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
1. 目标用户：优先写出内容中已有的年级、年龄段或学习阶段。
2. 搜索关键词：使用家长真实会搜索的学科和问题，如“初二数学”“数学成绩上不去”“考试不会做题”。
3. 具体痛点：抓住成绩停滞、错题反复、听懂不会做、学习习惯等真实关注点。
4. 结果价值：明确点开后能获得的方法、关键点、步骤或判断依据，但不承诺确定效果。
5. 可读性：自然、具体，像真实小红书教育老师或家长分享，不像教育论文或后台报告。

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
8. 每个候选都必须重新设计，任何候选都不得与用户的原标题相同；必须综合目标用户、搜索关键词、用户痛点和点击理由，而不是只替换风险词。
9. 禁止使用“学习状态改善”“学习者”“数理思维基础薄弱”“内容表达优化”等论文式或审核式表达。
10. 标题只能使用 title、body 和 creator_profile 中已经明确出现的事实，不得凭空增加年级、分数、年龄、学习问题、案例或结果。
11. 如果原文没有明确某个痛点，不得把它写成确定事实；确需提供探索方向时，必须明确写成“推测用户痛点”，不能伪装成用户已经提供的信息。
12. 保留原文中的真实学科与搜索关键词，不要为了书面化而替换成家长不会搜索的词。

示例方向：
不要：数学30天提高50分
可以：数学成绩一直上不去，可能忽略了这个关键问题

不要：专收差生
可以：帮助数学基础薄弱孩子找到学习方法

只输出合法 JSON，不要 Markdown、代码块或额外解释：
{"titles": ["标题1", "标题2", "标题3", "标题4", "标题5"]}
""".strip()

COVER_ANALYSIS_PROMPT = """
你是一名小红书教育赛道封面内容策划。请根据封面 OCR 识别文字、用户补充的图片描述和当前 risk_items，分析这张封面是否适合家长用户在手机端快速阅读，并给出合规、可执行的优化建议。图片描述仅作为用户确认的补充上下文，不得据此扩展或虚构未提供的视觉事实。

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

这不是原文扩写或逐句润色任务。请先理解图片、案例截图、课程海报、课堂照片或文字素材的核心信息，再重新策划一篇完整发布稿。素材只作为事实来源，不需要沿用原文顺序和句式。

整体口吻必须像一位真实教育老师在分享观察和方法：克制、具体、有现场感。禁止营销号语气、夸张承诺、绝对结果和课程推销开头。优先从家长真实困惑切入，使用素材中已有的具体学习场景，再给出老师观察和可执行方法。没有 creator_profile 依据时，不得虚构老师经历或第一人称案例。

素材使用：
1. 综合使用当前标题、正文、封面 OCR 文字、用户修正后的封面文字和补充主题，不要求素材字段全部存在。
2. 用户修正后的封面文字优先于原始 OCR；不得臆测图片中未识别的信息。
3. creator_profile 是唯一允许使用的身份、资历、科目、教学形式、时长、价格、案例和行动方式来源。
4. 只有 generation_options 明确允许时，才把老师介绍、课程信息写入正文。
5. source_materials.cover_analysis 和 source_materials.image_analysis 是图片分析结果；只能使用其中有素材依据的结论。
6. source_materials.viral_examples 是用户保存的历史跑量案例，只能参考其开头方式、内容结构、家长痛点表达、情绪触发、老师 IP 展示、方法拆解、服务介绍、自然转化和排版节奏。
7. source_materials.viral_example_analysis 是生成前对多个案例共同写法的拆解。优先学习共同规律，不要贴近某一篇案例。
8. 不得复制 viral_examples 的标题、原句、段落或案例事实，不得把历史案例中的人物、数据和经历写成当前创作者的事实。

真实性红线：
1. creator_profile 未填写的经历、学员数量、家长反馈、教学成果、价格、案例和数据一律不得生成。
2. 不得虚构提分数据、真实案例、CTR、曝光、留资、转化率或“家长都认可”等无法验证的事实。
3. 案例复盘型仅能使用 source_materials 或 creator_profile 中真实存在的案例素材；没有案例时改为方法复盘，不补造人物和结果。

内容方向：
严格遵循 generation_options.content_direction 和 structure_guidance。不同方向必须使用明显不同的切入方式与段落结构。
可参考家长痛点、老师身份与专业背书、教学理念、具体方法、课程服务、真实素材中的感受、形式时长价格和自然行动引导，但不要每次使用相同顺序。
禁止固定使用“有个家长跟我说”等开头，禁止重复固定句式、固定表情或固定分隔符，不照抄任何示例。
当 generation_options.generation_mode 为“根据图片生成”时：
1. 先使用 source_materials.image_analysis 中的封面主题、目标人群、卖点方向和 content_type 确定写作角度，不得直接把 OCR 文字扩写成正文。
2. 必须遵循 generation_options.structure_guidance 中与教学经验、学生成果案例、课程服务或学习方法分享对应的结构。
3. creator_profile 中没有的老师身份或背书必须省略，不得为了补齐结构而虚构。
4. 图片中无法从 OCR 或已确认资料证实的人物、场景、案例和效果不得写入文案。
5. 不得生成成绩保证、短期效果承诺或任何未经用户确认的转化数据。
6. 如有 viral_examples，提炼多个案例的共同写法后重新创作，不得贴近或复刻某一篇原文。
7. 开头直接用第二人称或常见家长场景建立代入，例如“你家娃是不是也这样”；禁止“随着时代发展”等论文式开头。
8. 重新定义问题时，不贬低学习者；优先表达为缺少合适的方法、训练或学习节奏。
9. 老师背书可用“我是XX老师👩‍🏫”和 ✅ 列表，但每一项都必须能在 creator_profile 中逐字找到事实依据。
10. 方法必须使用 1️⃣、2️⃣、3️⃣ 拆解到“如何做”，不能只写“培养能力”等空泛结论。
11. 服务价值按已确认资料说明学前诊断、学中互动反馈纠正、学后复盘跟进；资料没有的环节必须省略。
12. 行动引导使用了解学习情况、诊断问题或咨询学习规划等自然表达，不作结果承诺。

正文要求：
1. 正文目标字数遵循 generation_options.min_chars 与 max_chars；图片模式为 800—1000 字，且绝对不超过 1000 字。
2. 必须有完整开头、具体用户痛点、核心观点或方法和完整结尾，不得从残句开始或突然中断。
3. 写作自然、有经验分享感和转化力，但不空泛、不堆砌卖点、不过度营销。
4. 可以灵活调整场景、观点、方法和服务信息的顺序，避免连续使用相同句式。
5. 生成一条独立、简短、自然的 action；是否加入最终发布版由页面控制。
6. 生成一条独立的 comment_question，用于评论区互动。问题必须与素材主题直接相关，不得补造用户经历或效果。
7. 图片模式使用小红书投放素材的阅读节奏：短句、每 2—4 句话换行、任何单段不得超过 100 字，避免公众号式长段落。
8. 图片模式使用适量 emoji，并让符号各有分工：开头可用 👇😭😣，痛点可用 ❌⚠️，老师背书可用 👩‍🏫✅，方法必须用 1️⃣2️⃣3️⃣，优势可用 ⭐📌，转化可用 👉。不要堆满每一句。

标题要求：
根据 generation_options.expected_title_count 生成恰好对应数量的标题。图片模式生成 3 个不同角度标题，文字模式保持 5 个；优先覆盖痛点型、好奇型、干货型、老师经验型、家长共鸣型。
标题保留真实科目、年级、学习场景和家长问题，但不得出现保证提分、30天提高50分、一定有效、百分百、必然逆袭或虚构数据。

合规要求：
1. 同时参考 risk_items 和 source_materials.rule_constraints，避开当前启用规则中的风险表达。
2. 不使用绝对化承诺、保证结果、虚假案例、违规引导和夸大宣传。
3. “孩子”“数学”等普通教育词可自然使用，不要把普通词自行升级成严重风险。
4. 标签与主题相关，使用 # 开头，生成恰好 5 个。

只输出合法 JSON，不要 Markdown、代码块或额外解释：
{
  "titles": ["标题1", "标题2", "标题3"],
  "body": "完整正文",
  "action": "简短行动引导",
  "comment_question": "与素材主题相关的评论区问题",
  "tags": ["#标签1", "#标签2", "#标签3", "#标签4", "#标签5"]
}
""".strip()

CONTENT_LAB_DRAFT_PROMPT = """
你是教育行业真实账号的小红书内容编辑。请基于用户已经确认的真实素材、业务定位、参考案例、方法模型和内容策划方案，写出一篇可以直接人工复核并发布的小红书笔记。

写作前请在内部完成结构提炼，但不要输出分析过程：
1. 标题结构：参考案例如何同时交代目标用户、具体问题和阅读价值。
2. 开头方式：参考案例如何用真实场景、家长困惑或具体问题让用户继续阅读。
3. 用户痛点表达：参考案例如何把抽象焦虑写成用户熟悉的教育场景。
4. 信任建立方式：参考案例如何用已确认的经验、过程、方法或素材建立可信度。
5. 转化路径：参考案例如何从提供价值自然过渡到评论、咨询或下一步行动。

只复用上述结构和节奏。禁止复制参考案例原句、人物经历、身份、成绩、价格、反馈和具体数据。

要求：
1. 只能使用输入中已有的事实，不得虚构成绩、案例、身份、反馈、价格、人数或效果。
2. 学习参考案例和方法模型的结构，不得复制案例原句、人物经历和具体数据。
3. 必须生成5个角度明显不同的标题，兼顾目标用户、具体问题和内容价值，不承诺爆款或确定效果。
4. 封面文案包含主标题、副标题和简短视觉建议；视觉建议只描述信息层级，不臆测上传图片中未确认的画面内容。
5. 默认平台为小红书，内容类型为教育培训/课程咨询，目标是获取真实咨询线索。正文控制在800-1500字，并按自然阅读顺序覆盖：情绪开头、家长与学生痛点、具体场景、老师背书、方法论证明、服务介绍、福利与行动引导。不得输出结构名称或分析说明。
6. 老师背书优先使用输入中已确认的姓名、教学经验、擅长领域和服务学生类型；缺少的信息不得编造，也不要在正文里用占位符冒充事实。
7. 方法论证明应体现“过去问题 → 发现原因 → 解决方法 → 执行过程”，可使用学情诊断、错题分析、针对训练、阶段反馈等步骤，但只能采用与输入素材相符的内容。
8. 服务介绍应说明已确认的服务形式、服务对象、服务内容和解决的问题。免费试听、学情诊断、学习规划等福利，仅当输入素材或业务档案明确存在时才可以写入；否则不得擅自承诺。
9. 发布时间建议使用一般运营建议，并明确需要结合账号历史数据调整，不得声称掌握平台推荐规律。
10. 标签生成5个，以#开头；爆款结构复用点仅总结本次实际使用的方法；生成一条自然的评论区引导问题。
11. 语言要像真实小红书教育博主以第一人称发布：短段落、有具体场景、有自然口语感，先给用户价值，再自然提及产品或服务；可适度使用 ✅、👉、⭐ 等符号帮助直接复制发布，但不要堆砌；避免论文腔、营销号语气、夸张承诺和绝对化表达。
12. full_text 中禁止出现“本文分析”“根据案例”“参考案例”“爆款模型显示”“爆款模型”“方法模型”“建议用户”“内容策划”“结构分析”等幕后分析语言。
13. 不要在 full_text 中使用“开头钩子：”“用户痛点：”“信任建立：”“转化路径：”等报告式小标题。用户最终只能感受到一篇自然成稿。

只输出合法 JSON，不要 Markdown、代码块或额外解释：
{
  "titles": ["", "", "", "", ""],
  "cover_copy": {
    "main_title": "",
    "subtitle": "",
    "visual_suggestion": ""
  },
  "body": {
    "opening_hook": "",
    "user_pain": "",
    "real_experience": "",
    "solution": "",
    "product_intro": "",
    "action_guide": "",
    "full_text": ""
  },
  "publishing": {
    "tags": ["", "", "", "", ""],
    "comment_question": "",
    "timing_advice": "",
    "reused_points": [""]
  }
}
""".strip()

CONTENT_LAB_REPORT_PHRASES = (
    "本文分析",
    "根据案例",
    "参考案例",
    "爆款模型显示",
    "爆款模型",
    "方法模型",
    "建议用户",
    "内容策划",
    "结构分析",
    "开头钩子：",
    "用户痛点：",
    "信任建立：",
    "转化路径：",
)

NOTE_IMAGE_ANALYSIS_PROMPT = """
你是小红书教育赛道内容策划。请在生成完整笔记之前，分析图片经过 OCR 后得到的文字与基础文件信息。

你会收到 image_context、creator_profile、risk_items 和 rule_constraints。
能力边界：
1. 当前 DeepSeek 是文本模型，不接收图片像素。只能使用 OCR 文字、用户修正文字、标题、图片尺寸、宽高比、格式和已有业务资料。
2. 如果未来视觉接口明确提供了已验证的 content_type、visual_scene、education_value 和 evidence，可以将其作为补充证据；当前没有这些字段时不得自行补造。
3. 不要机械复述或拼接 OCR。根据已有文字判断教育内容价值，再说明适合生成什么类型的笔记。
4. content_type 只能是：教学经验、学生成果案例、课程服务、学习方法分享。
5. visual_elements 只能列出 OCR 或用户输入中已确认的文字元素；不得虚构人物身份、成绩变化、背景、颜色、表情和版式细节。teacher_cues 也只能来自 OCR、用户修正文字或 creator_profile。
6. target_audience、selling_direction 和 content_type 必须有输入文字依据。
7. creator_profile 只能帮助理解用户已保存的真实定位，不得补造经历、案例、人数、成绩和效果数据。
8. 参考 risk_items 和 rule_constraints 避开成绩保证、短期效果承诺及其他未经确认表达。

只输出合法 JSON：
{
  "cover_theme": "",
  "visual_elements": [""],
  "target_audience": "",
  "selling_direction": "",
  "content_type": "",
  "teacher_cues": "",
  "analysis_basis": ""
}
""".strip()

VIRAL_EXAMPLE_ANALYSIS_PROMPT = """
你是一名资深小红书教育投放内容策划。生成新文案前，请拆解用户保存的多个历史跑量案例的共同写法。

分析范围：
1. 识别案例类型、家长场景开头、痛点表达、情绪触发、老师 IP 背书、方法拆解、服务介绍、转化方式和手机端排版节奏。
2. 优先提炼多个案例共有的结构规律，并说明哪些写法适合当前图片主题和目标人群。
3. 输入案例中的 category、structure、opening_style、pain_points、selling_points、conversion_style 是用户保存的参考标签，可用于辅助判断。
4. 只能学习结构和表达策略，不得复制标题、原句、段落、人物、经历、案例或数据。
5. 不得把历史案例中的事实当成 creator_profile 的事实，不得建议成绩保证、短期逆袭或绝对效果。

只输出合法 JSON：
{
  "category": "",
  "opening_style": "",
  "structure": [""],
  "pain_expression": "",
  "emotional_trigger": "",
  "teacher_ip_style": "",
  "method_style": "",
  "service_style": "",
  "conversion_style": "",
  "layout_style": "",
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
1. 封面文字结构：说明主标题、辅助说明、数字或行动信息如何组成文案。
2. 信息层级：说明用户按什么顺序接收信息，哪些是一级、二级、三级信息。
3. 排版方式：结合尺寸、宽高比和用户描述，对标题位置、信息密度与元素关系给出有边界的推断或建议。
4. 第一眼信息：只基于 OCR 与已提供描述，指出用户最先接收到的具体信息。
5. 点击吸引因素：列出文案中形成点击动机的具体痛点、数字、结果价值或悬念。
6. 信任建立方式：指出案例、过程、老师经验或服务细节如何建立信任；没有时明确写“未体现”。
7. 用户痛点表达：指出封面如何描述目标用户的具体困扰；没有时明确写“未体现”。
8. 转化元素：只列出文字中真实存在的咨询、领取、试听、价格、时长或行动引导；没有时返回空数组。
9. 可复用模板：沉淀一个结构模板，只复用写法，不照搬案例、数据或承诺。
10. 风险点：结合 risk_items 判断夸大承诺或风险表达，并列出不建议照搬的内容。
11. 不能虚构 CTR、曝光、转化率、爆款概率或未提供的画面细节。

只输出合法 JSON，不要 Markdown、代码块或额外解释：
{
  "cover_text_structure": "",
  "information_hierarchy": "",
  "layout_method": "",
  "first_glance": "",
  "click_factors": [""],
  "trust_building": "",
  "user_pain_expression": "",
  "conversion_elements": [""],
  "reusable_template": "",
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


def get_deepseek_api_key() -> str:
    load_env()
    return (os.getenv("DEEPSEEK_API_KEY") or "").strip()


def print_deepseek_diagnostics(api_key: str | None) -> None:
    provider_status = "configured" if api_key else "missing_key"
    print(
        f"key_loaded={bool(api_key)} "
        f"provider_status={provider_status}"
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


def parse_note_generation_response(
    content: str,
    expected_title_count: int = 5,
) -> dict[str, Any] | None:
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
    comment_question = str(parsed.get("comment_question", "")).strip()
    expected_title_count = max(1, min(int(expected_title_count), 5))
    if len(titles) != expected_title_count or len(tags) != 5 or not body or not action:
        set_last_error("DeepSeek 笔记生成结果不完整，请重试")
        return None

    return {
        "titles": titles,
        "body": body,
        "action": action,
        "comment_question": comment_question,
        "tags": tags,
    }


def parse_content_lab_draft_response(content: str) -> dict[str, Any] | None:
    cleaned_content = content.strip()
    if cleaned_content.startswith("```"):
        cleaned_content = cleaned_content.strip("`").strip()
        if cleaned_content.startswith("json"):
            cleaned_content = cleaned_content[4:].strip()
    try:
        parsed = json.loads(cleaned_content)
    except json.JSONDecodeError as error:
        set_last_error(f"DeepSeek 内容实验室返回不是合法 JSON：{error.msg}")
        return None
    if not isinstance(parsed, dict):
        set_last_error("DeepSeek 内容实验室返回不是对象")
        return None

    def clean_text(value: Any, limit: int = 6000) -> str:
        return str(value or "").strip()[:limit]

    def clean_list(value: Any, limit: int) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for item in value:
            text = clean_text(item, 500)
            if text and text not in result:
                result.append(text)
        return result[:limit]

    cover = parsed.get("cover_copy") if isinstance(parsed.get("cover_copy"), dict) else {}
    body = parsed.get("body") if isinstance(parsed.get("body"), dict) else {}
    publishing = parsed.get("publishing") if isinstance(parsed.get("publishing"), dict) else {}
    result = {
        "titles": clean_list(parsed.get("titles"), 5),
        "cover_copy": {
            "main_title": clean_text(cover.get("main_title"), 100),
            "subtitle": clean_text(cover.get("subtitle"), 160),
            "visual_suggestion": clean_text(cover.get("visual_suggestion"), 500),
        },
        "body": {
            "opening_hook": clean_text(body.get("opening_hook"), 1000),
            "user_pain": clean_text(body.get("user_pain"), 1500),
            "real_experience": clean_text(body.get("real_experience"), 2000),
            "solution": clean_text(body.get("solution"), 3000),
            "product_intro": clean_text(body.get("product_intro"), 1500),
            "action_guide": clean_text(body.get("action_guide"), 1000),
            "full_text": clean_text(body.get("full_text"), 6000),
        },
        "publishing": {
            "tags": clean_list(publishing.get("tags"), 5),
            "comment_question": clean_text(publishing.get("comment_question"), 300),
            "timing_advice": clean_text(publishing.get("timing_advice"), 500),
            "reused_points": clean_list(publishing.get("reused_points"), 6),
        },
    }
    required = (
        len(result["titles"]) == 5,
        bool(result["cover_copy"]["main_title"]),
        800 <= len(result["body"]["full_text"]) <= 1500,
        len(result["publishing"]["tags"]) == 5,
    )
    if not all(required):
        set_last_error(
            "DeepSeek 内容实验室生成结果不完整："
            f"titles={len(result['titles'])}, "
            f"cover={bool(result['cover_copy']['main_title'])}, "
            f"body_chars={len(result['body']['full_text'])}, "
            f"tags={len(result['publishing']['tags'])}"
        )
        return None
    return result


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
        "teacher_cues": str(parsed.get("teacher_cues", "")).strip(),
        "analysis_basis": str(parsed.get("analysis_basis", "")).strip(),
    }
    if not all(result[key] for key in ("cover_theme", "target_audience", "selling_direction", "content_type")):
        set_last_error("DeepSeek 图片素材分析结果不完整")
        return None
    return result


def parse_viral_example_analysis_response(content: str) -> dict[str, Any] | None:
    cleaned_content = content.strip()
    if cleaned_content.startswith("```"):
        cleaned_content = cleaned_content.strip("`").strip()
        if cleaned_content.startswith("json"):
            cleaned_content = cleaned_content[4:].strip()
    try:
        parsed = json.loads(cleaned_content)
    except json.JSONDecodeError as error:
        set_last_error(f"DeepSeek 案例拆解不是合法 JSON：{error.msg}")
        return None
    if not isinstance(parsed, dict):
        set_last_error("DeepSeek 案例拆解结果不是对象")
        return None

    structure = parsed.get("structure", [])
    if not isinstance(structure, list):
        structure = [str(structure).strip()] if str(structure).strip() else []
    result = {
        "category": str(parsed.get("category", "")).strip(),
        "opening_style": str(parsed.get("opening_style", "")).strip(),
        "structure": [str(item).strip() for item in structure if str(item).strip()],
        "pain_expression": str(parsed.get("pain_expression", "")).strip(),
        "emotional_trigger": str(parsed.get("emotional_trigger", "")).strip(),
        "teacher_ip_style": str(parsed.get("teacher_ip_style", "")).strip(),
        "method_style": str(parsed.get("method_style", "")).strip(),
        "service_style": str(parsed.get("service_style", "")).strip(),
        "conversion_style": str(parsed.get("conversion_style", "")).strip(),
        "layout_style": str(parsed.get("layout_style", "")).strip(),
        "analysis_basis": str(parsed.get("analysis_basis", "")).strip(),
    }
    if not result["opening_style"] or not result["structure"] or not result["conversion_style"]:
        set_last_error("DeepSeek 案例拆解结果不完整")
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


def copies_viral_example(
    generated: dict[str, Any],
    examples: list[dict[str, str]],
) -> bool:
    generated_titles = {
        re.sub(r"\s+", "", str(title))
        for title in generated.get("titles", [])
        if str(title).strip()
    }
    generated_body = re.sub(r"\s+", "", str(generated.get("body", "")))
    for example in examples:
        example_title = re.sub(r"\s+", "", str(example.get("title", "")))
        if example_title and example_title in generated_titles:
            return True

        content = str(example.get("content", ""))
        fragments = [content, *content.splitlines()]
        for fragment in fragments:
            normalized = re.sub(r"\s+", "", fragment)
            if len(normalized) >= 24 and normalized in generated_body:
                return True
    return False


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
        "cover_text_structure": str(parsed.get("cover_text_structure", "")).strip(),
        "information_hierarchy": str(parsed.get("information_hierarchy", "")).strip(),
        "layout_method": str(parsed.get("layout_method", "")).strip(),
        "first_glance": str(parsed.get("first_glance", "")).strip(),
        "click_factors": clean_list(parsed.get("click_factors")),
        "trust_building": str(parsed.get("trust_building", "")).strip(),
        "user_pain_expression": str(parsed.get("user_pain_expression", "")).strip(),
        "conversion_elements": clean_list(parsed.get("conversion_elements")),
        "reusable_template": str(parsed.get("reusable_template", "")).strip(),
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
    if not result["cover_text_structure"]:
        result["cover_text_structure"] = "；".join(
            value
            for value in result["copy_structure"].values()
            if value
        ) or "现有封面文字不足，暂无法拆解文案结构。"
    if not result["information_hierarchy"]:
        result["information_hierarchy"] = result["layout_structure"]["text_hierarchy"] or "现有信息不足"
    if not result["layout_method"]:
        result["layout_method"] = "；".join(
            value
            for value in (
                result["layout_structure"]["headline_position"],
                result["layout_structure"]["information_density"],
                result["layout_structure"]["element_relationship"],
            )
            if value
        ) or "现有信息不足"
    if not result["first_glance"]:
        result["first_glance"] = result["layout_structure"]["visual_focus"] or "现有信息不足"
    if not result["click_factors"]:
        result["click_factors"] = list(result["attraction_points"])
    if not result["trust_building"]:
        result["trust_building"] = result["copy_structure"]["credibility"] or "封面文字中未体现明确的信任依据。"
    if not result["user_pain_expression"]:
        result["user_pain_expression"] = result["copy_structure"]["pain_point"] or "封面文字中未体现明确的用户痛点。"
    if not result["conversion_elements"] and result["copy_structure"]["service_information"]:
        result["conversion_elements"] = [result["copy_structure"]["service_information"]]
    if not result["reusable_template"]:
        target = result["copy_structure"]["target_audience"] or "目标人群"
        pain = result["copy_structure"]["pain_point"] or "具体问题"
        result["reusable_template"] = f"{target} + {pain} + 可验证的方法或价值"
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
    image_description: str = "",
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
        "image_description": image_description.strip(),
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

    def request_titles(client: Any, retry: bool = False) -> list[str] | None:
        payload = dict(user_payload)
        if retry:
            payload["regeneration_requirement"] = (
                "上一轮候选与原标题过于相似或包含未经确认的信息。请重新生成5个不同的发布测试标题，"
                "只能使用输入中已有的用户阶段、搜索关键词、具体痛点和价值事实；不得补造分数、年级或孩子问题。"
            )
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": TITLE_GENERATION_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ],
            temperature=0.8,
        )
        content = response.choices[0].message.content or ""
        return parse_title_response(content)

    try:
        client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        candidates = request_titles(client)
        normalized_original = re.sub(r"[\s，。！？、；：,.!?;:]", "", title or "")
        banned_title_phrases = ("学习状态改善", "学习者", "数理思维基础薄弱", "内容表达优化")
        factual_source = json.dumps(user_payload, ensure_ascii=False)

        def introduced_fact(candidate: str) -> bool:
            fact_patterns = (
                r"(?:小|初|高)[一二三123]",
                r"\d+\s*(?:岁|分|天|年|个月|小时|课时|元|r|个)",
            )
            for pattern in fact_patterns:
                for fact in re.findall(pattern, candidate):
                    if fact not in factual_source:
                        return True
            inferred_pains = ("听懂却不会做题", "错题反复", "考试不会做", "偏科", "粗心")
            return any(pain in candidate and pain not in factual_source for pain in inferred_pains) and "推测用户痛点" not in candidate

        def unsuitable(candidate: str) -> bool:
            normalized_candidate = re.sub(r"[\s，。！？、；：,.!?;:]", "", candidate)
            if any(phrase in candidate for phrase in banned_title_phrases):
                return True
            if introduced_fact(candidate):
                return True
            if not normalized_original:
                return False
            return SequenceMatcher(None, normalized_original, normalized_candidate).ratio() >= 0.78

        if candidates and any(unsuitable(candidate) for candidate in candidates):
            candidates = request_titles(client, retry=True)
        if candidates:
            candidates = [candidate for candidate in candidates if not unsuitable(candidate)]
        if not candidates:
            set_last_error("标题生成未产生与原标题不同的方案，请重试")
            return None
        return candidates
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
        expected_title_count = int(
            (generation_options or {}).get("expected_title_count", 5)
        )
        parsed = parse_note_generation_response(
            content,
            expected_title_count=expected_title_count,
        )
        examples = (source_materials or {}).get("viral_examples", [])
        if parsed and isinstance(examples, list) and copies_viral_example(parsed, examples):
            set_last_error("生成结果与历史案例存在直接重复，请重新生成。")
            return None
        return parsed
    except Exception as error:
        set_last_error(f"{type(error).__name__}: {error}")
        return None


def generate_content_lab_draft(
    plan: dict[str, Any],
    material_context: dict[str, Any],
    business_profile: dict[str, Any],
    method_model: dict[str, Any],
) -> dict[str, Any] | None:
    """Generate publish-ready copy from the confirmed content-lab context."""
    set_last_error("")
    api_key = get_deepseek_api_key()
    print_deepseek_diagnostics(api_key)
    if not api_key:
        set_last_error("AI 服务配置不可用")
        return None
    try:
        from openai import OpenAI
    except ModuleNotFoundError:
        set_last_error("AI 服务依赖不可用")
        return None

    payload = {
        "material": material_context if isinstance(material_context, dict) else {},
        "business_profile": business_profile if isinstance(business_profile, dict) else {},
        "method_model": method_model if isinstance(method_model, dict) else {},
        "content_plan": plan if isinstance(plan, dict) else {},
    }
    try:
        client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)

        def request_draft(extra_instruction: str = "") -> dict[str, Any] | None:
            user_content = json.dumps(payload, ensure_ascii=False)
            if extra_instruction:
                user_content += f"\n{extra_instruction}"
            response = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": CONTENT_LAB_DRAFT_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.75,
            )
            content = response.choices[0].message.content or ""
            return parse_content_lab_draft_response(content)

        draft = request_draft()
        if not draft:
            validation_error = get_last_error()
            draft = request_draft(
                "上一版没有通过发布稿校验。请重新输出完整合法JSON，并严格保证："
                "titles恰好5个，cover_copy.main_title非空，publishing.tags恰好5个；"
                "body.full_text必须为800至1500个中文字符，建议写900至1200字，"
                "内容完整覆盖痛点共鸣、老师背书、方法证明、服务介绍和福利行动，"
                "不得重复句子凑字数。"
                f"上一版校验信息：{validation_error}"
            )
        if not draft:
            validation_error = get_last_error()
            draft = request_draft(
                "这是最后一次修正。请重新生成完整JSON，正文不要摘要化。"
                "body.full_text请按约1100至1300个中文字符撰写，"
                "用具体家长场景、已确认的老师信息、方法执行过程、服务内容和"
                "自然行动引导充分展开；严禁虚构数据、经历或效果。"
                f"上一版校验信息：{validation_error}"
            )
        if draft and any(
            phrase in str(draft.get("body", {}).get("full_text") or "")
            for phrase in CONTENT_LAB_REPORT_PHRASES
        ):
            draft = request_draft(
                "上一版正文带有AI分析报告语气。请保留真实事实和参考结构，"
                "彻底重写为真实小红书博主可直接发布的正文；不要解释改写过程。"
            )
        if draft and any(
            phrase in str(draft.get("body", {}).get("full_text") or "")
            for phrase in CONTENT_LAB_REPORT_PHRASES
        ):
            set_last_error("生成结果仍包含分析报告语言，请重试")
            return None
        return draft
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
        content = _request_image_analysis(
            OpenAI,
            api_key,
            NOTE_IMAGE_ANALYSIS_PROMPT,
            payload,
            0.3,
        )
        return parse_note_image_analysis_response(content)
    except Exception as error:
        set_last_error(f"{type(error).__name__}: {error}")
        return None


def analyze_viral_examples_for_generation(
    examples: list[dict[str, str]],
    image_analysis: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    set_last_error("")
    if not examples:
        return {}
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
        "viral_examples": examples,
        "current_image_analysis": image_analysis or {},
    }
    try:
        client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": VIRAL_EXAMPLE_ANALYSIS_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.3,
        )
        content = response.choices[0].message.content or ""
        return parse_viral_example_analysis_response(content)
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
        content = _request_image_analysis(
            OpenAI,
            api_key,
            VIRAL_IMAGE_ANALYSIS_PROMPT,
            image_context,
            0.4,
        )
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
