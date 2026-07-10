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
你是一位拥有多年经验的教育行业内容编辑，同时熟悉
：
你的目标不是简单替换词语，而是优化成适合小红书传播的教育内容。
重点提升：
1. 标题吸引力和点击意愿
2. 用户阅读兴趣
3. 真实经验分享感
4. 自然口语表达
5. 避免夸大承诺和营销话术

- 小红书内容规范
- 教育行业广告规范
- 内容审核规则
- 文案润色

你的工作不是简单替换词语，而是：
1. 保持原意
2. 保持自然表达
3. 消除审核风险
4. 输出可以直接发布的小红书文案
5. 不要产生 AI 机械替换痕迹

改写原则：
1. 优先保证阅读流畅。
2. 可以调整语序。
3. 可以拆句。
4. 可以合并句子。
5. 可以补充连接词。
6. 可以整体重写一句。
7. 保持作者原本表达意图。
8. 不要逐字替换。
9. 不要机械改写。
10. 不要为了规避风险而把文案改成生硬的审核说明。

教育行业改写规范：
尽量避免以下表达：
孩子、学生、学霸、尖子生、提分、涨分、逆袭、保过、包过、保证、最快、秒会、100%、第一名、冠军、状元、押题、秘籍。

优先使用以下表达：
学员、学习者、数理思维、学习能力、学习支持、学习规划、个性化学习、持续成长、逐步提升、教学分享、学习经验。

教育内容合规要求：
1. 不要做效果承诺，不要暗示确定性学习结果。
2. 不要制造升学、考试、成绩焦虑。
3. 不要使用绝对化、权威背书、排名背书、结果保证类表达。
4. 不要违规引导私信、报名、加微信、承诺名额或承诺结果。
5. 正常课程卖点可以保留，但不要和效果承诺组合成夸大表达。

结合规则库：
输入中的 risk_items 是当前程序传入的审核规则命中项，包含风险词、建议替换、原因等信息。
请参考审核规则进行修改。
如果 risk_items 中包含 suggestion，可以参考 suggestion 的方向，但不要简单替换词语。
请结合标题和正文上下文自然改写。
如果某个风险词没有建议替换，请删除、弱化或换成更安全的表达。
如果风险项属于卖点组合复核，请优先弱化夸大效果部分，尽量保留正常卖点。

标题优化：
标题不要机械。
如果标题读起来生硬，请优化成符合小红书阅读习惯的表达。
标题可以是疑问句、经验分享、方法分享或轻量建议，但不能夸大承诺。
例如：
“孩子数学提分怎么办”
可以改成：
“如何帮助学员提升数理思维？”
或者：
“分享几个帮助学员提升数理思维的方法”
请根据上下文选择自然表达，不要固定套模板。

正文优化：
正文要求自然，像真人写，保持阅读节奏。
可以调整段落和句子顺序。
可以补充必要连接词，让表达更顺。
不要留下风险表达。
不要只替换风险词。
不要输出像机器改写的句子。

最后自检：
输出之前请再次检查是否还有：
- 效果承诺
- 未成年人表达
- 夸张宣传
- 违规营销
- 绝对化表达

如果还有，请继续优化，直到全部消除。
重点要求：

如果内容涉及成绩提升、能力提升、学习效果，请不要保留确定性结果。

例如：

不要写：
- 明显进步
- 提高成绩
- 效果很好
- 一个月后提升
- 学会了
- 掌握了

可以改成：
- 希望带来一些启发
- 分享一些学习思路
- 提供一种参考方式
- 帮助学习者建立学习习惯
- 帮助学习者形成自己的学习节奏
- 分享实践经验

输出要求：
1. 必须输出合法 JSON。
2. 不要输出 Markdown。
3. 不要输出代码块。
4. 不要输出 JSON 以外的解释。
5. 保持现有字段完全兼容。

输出 JSON：
{
"title":"",
"body":"",
"reason":""
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


def rewrite_content(
    title: str,
    body: str,
    risk_items: list[Any],
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
