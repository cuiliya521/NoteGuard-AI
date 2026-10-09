"""Reuse V2 rule/semantic/draft functions, adding transport metadata only."""
from __future__ import annotations
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from services import llm
from services.rule_checker import check_text, load_rules, load_rule_records
from services.workflow_ai_v2 import review_semantics, make_draft

ROOT = Path(__file__).resolve().parents[2]
BASE_COMMIT = "4d3e737004db14c64cc6586480e66f1f9f7552d8"

class InputError(ValueError):
    pass

def environment_key():
    # V2 normally also loads .env; this isolated process accepts server env only.
    return (os.environ.get("DEEPSEEK_API_KEY") or "").strip()

llm.get_deepseek_api_key = environment_key

def document(payload):
    title, body = payload.get("title"), payload.get("body")
    if not isinstance(title, str) or not isinstance(body, str):
        raise InputError("标题和正文必须是字符串。")
    if not body.strip():
        raise InputError("正文不能为空。")
    if len(title) > 200 or len(body) > 5000:
        raise InputError("标题最多 200 字，正文最多 5000 字。")
    revision = payload.get("revision")
    request_id = payload.get("request_id")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise InputError("稿件版本无效。")
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
        raise InputError("请求标识无效。")
    return title, body, revision, request_id

def fingerprint(title, body):
    return hashlib.sha256(json.dumps([title, body], ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()

def semantic_error(error):
    # Never expose provider exceptions, request bodies, credentials or URLs.
    if not environment_key():
        return {"code": "missing_key", "message": "服务端尚未配置审核 API 密钥，允许配置后重试。"}
    if "timeout" in error.lower() or "timed out" in error.lower():
        return {"code": "timeout", "message": "语义审核超时，请重试。"}
    return {"code": "provider_failure", "message": "语义审核失败或返回结果无效，请重试。"}

class V2Engine:
    def __init__(self, rule_path=None):
        rule_path = rule_path or ROOT / "data" / "rules.json"
        # Existing loader silently falls back to [] on corruption; fail closed first.
        if not rule_path.is_file():
            raise RuntimeError("V2 规则库缺失。")
        load_rule_records(rule_path)
        self.rules = load_rules(rule_path)
        if not self.rules:
            raise RuntimeError("V2 有效规则库为空。")

    def audit(self, payload):
        title, body, revision, request_id = document(payload)
        findings = tuple(check_text(title, body, self.rules))
        review = review_semantics(title, body)
        rule_items = [dict(asdict(f), source="rule", field="title" if f.position == "标题" else "body",
                           positioning="detector-offset") for f in findings]
        semantic_items = []
        for issue in review.issues:
            text = title if issue.location == "标题" else body
            positions, start = [], 0
            while (index := text.find(issue.excerpt, start)) != -1:
                positions.append({"start": index, "end": index + len(issue.excerpt)})
                start = index + max(1, len(issue.excerpt))
            semantic_items.append(dict(asdict(issue), source="semantic",
                field="title" if issue.location == "标题" else "body",
                positioning="exact-quote", occurrences=positions))
        completed = review.available
        result = {"status": "completed" if completed else "partial_failure",
            "request_id": request_id, "revision": revision,
            "document": {"title": title, "body": body}, "content_hash": fingerprint(title, body),
            "rules": {"status": "completed", "count": len(rule_items), "items": rule_items},
            "semantic": {"status": "completed" if completed else "failed",
                         "count": len(semantic_items) if completed else None,
                         "items": semantic_items if completed else [],
                         "error": None if completed else semantic_error(review.error)},
            "conclusion": ("仍有疑似风险" if rule_items or semantic_items else "未发现明显风险") if completed else None,
            "scope_note": "未发现明显风险不等于保证内容绝对合规，发布前仍需人工判断。",
            "provenance": {"mode": "real_v2", "base_commit": BASE_COMMIT,
                           "rule_module": "services.rule_checker.check_text",
                           "semantic_module": "services.workflow_ai_v2.review_semantics"}}
        return result, (title, body, findings, review)

    def suggest(self, audited):
        title, body, findings, review = audited
        if not environment_key():
            return {"status": "failed", "source": "LLM", "draft": None,
                    "error": semantic_error("missing key")}
        if not review.available:
            return {"status": "failed", "source": "LLM", "draft": None,
                    "error": {"code": "incomplete_audit", "message": "语义审核尚未成功，请先重试原文检测。"}}
        if not findings and not review.issues:
            return {"status": "no_change", "source": "LLM", "draft": None,
                    "message": "本轮未发现明显风险，保留原文；未生成修改建议。"}
        draft = make_draft(title, body, findings, review.issues)
        if draft is None or draft.source != "LLM" or draft.error:
            return {"status": "failed", "source": "LLM", "draft": None,
                    "error": {"code": "llm_failure", "message": "LLM 建议生成失败，请重试；未将本地规则回退稿当作 AI 结果。"}}
        return {"status": "completed", "source": "LLM", "draft": asdict(draft),
                "message": "真实 LLM 建议，经 V2 最小删除约束处理；建议稿尚未复检。"}
