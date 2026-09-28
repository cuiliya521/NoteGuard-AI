"""LLM adapters for the optional semantic review and candidate draft."""
from __future__ import annotations

import json

from services import llm
from services.rule_checker import Finding
from services.workflow_v2 import Draft, SemanticIssue, SemanticReview


REVIEW_PROMPT = """你是教育内容运营的发布前语义审核助手。只根据输入内容判断可能的夸大效果、虚构事实、上下文误导或不当引导；不把正常的教育表达判作风险。规则命中由另一模块负责。不要推断未提供的事实，也不要输出思维链。只输出 JSON：{\"issues\":[{\"location\":\"标题或正文\",\"excerpt\":\"原文中的短片段\",\"reason\":\"具体风险理由\",\"severity\":\"high或medium或low\"}]}。无明显问题返回空数组。"""
DRAFT_PROMPT = """你是教育内容编辑。根据原文、规则命中及语义问题，只对必要的风险表达作最小修改，保持段落与真实卖点，不虚构事实、结果、师资或用户反馈。建议稿供用户审阅，不是自动发布。只输出 JSON：{\"title\":\"建议标题\",\"body\":\"建议正文\",\"reason\":\"具体改动与理由\"}。保留没有风险的原句。"""


def _complete(system: str, payload: dict) -> dict:
    api_key = llm.get_deepseek_api_key()
    if not api_key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY")
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=llm.DEEPSEEK_BASE_URL, timeout=25, max_retries=0)
    response = client.chat.completions.create(
        model=llm.DEEPSEEK_MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        response_format={"type": "json_object"}, temperature=0.2,
    )
    parsed = json.loads(response.choices[0].message.content or "")
    if not isinstance(parsed, dict):
        raise ValueError("模型结果不是 JSON 对象")
    return parsed


def review_semantics(title: str, body: str) -> SemanticReview:
    try:
        result = _complete(REVIEW_PROMPT, {"title": title, "body": body})
        raw = result.get("issues")
        if not isinstance(raw, list):
            raise ValueError("语义问题列表缺失")
        issues = []
        for item in raw[:10]:
            if not isinstance(item, dict):
                raise ValueError("语义问题格式错误")
            location = str(item.get("location", "")).strip()
            excerpt = str(item.get("excerpt", "")).strip()
            reason = str(item.get("reason", "")).strip()
            source = title if location == "标题" else body if location == "正文" else ""
            if not excerpt or excerpt not in source or not reason:
                raise ValueError("语义问题无法在原文定位")
            severity = str(item.get("severity", "medium"))
            issues.append(SemanticIssue(location, excerpt, reason,
                                        severity if severity in {"high", "medium", "low"} else "medium"))
        return SemanticReview(tuple(issues), available=True)
    except Exception as exc:
        return SemanticReview(error=f"{type(exc).__name__}: {exc}")


def make_draft(title: str, body: str, findings: tuple[Finding, ...],
               issues: tuple[SemanticIssue, ...]) -> Draft | None:
    payload = {"title": title, "body": body,
               "rule_findings": [{"location": f.position, "excerpt": f.term,
                                  "reason": f.reason, "suggestion": f.suggestion} for f in findings],
               "semantic_issues": [vars(i) for i in issues]}
    try:
        result = _complete(DRAFT_PROMPT, payload)
        candidate_title, candidate_body = result.get("title"), result.get("body")
        if not isinstance(candidate_title, str) or not isinstance(candidate_body, str):
            raise ValueError("建议稿字段缺失")
        return Draft(candidate_title, candidate_body, str(result.get("reason", "请人工核对修改。")), "LLM")
    except Exception as exc:
        if not findings:
            return None
        from services.rewriter import rewrite_with_local_rules
        fallback = rewrite_with_local_rules(title, body, list(findings))
        return Draft(fallback.title, fallback.body,
                     "AI 建议不可用；以下仅根据命中规则生成本地替代，请人工检查语义与事实。",
                     "本地规则", error=f"{type(exc).__name__}: {exc}")
