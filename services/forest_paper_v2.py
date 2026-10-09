"""UI transaction adapter. Detection and drafting stay in the existing V2 modules."""
from __future__ import annotations

from dataclasses import asdict, replace
from difflib import SequenceMatcher
from threading import RLock
import secrets
import time

from services.workflow_v2 import Draft, start_workflow, decide_workflow
from services.workflow_ai_v2 import review_semantics, make_draft


def document(value):
    if not isinstance(value, dict):
        raise ValueError("稿件格式错误。")
    title, body = value.get("title"), value.get("body")
    if not isinstance(title, str) or not isinstance(body, str):
        raise ValueError("标题与正文必须为文本。")
    if not body.strip():
        raise ValueError("正文不能为空。")
    if len(title) > 200 or len(body) > 5000:
        raise ValueError("标题最多 200 字，正文最多 5000 字。")
    return title, body


def differences(original, final):
    result = []
    for field in ("title", "body"):
        before, after = original[field], final[field]
        for kind, a, b, c, d in SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
            if kind != "equal":
                result.append({"field": field, "removed": before[a:b], "added": after[c:d]})
    return result


def review_payload(findings, semantic):
    rules = [dict(asdict(f), source="rule", field="title" if f.position == "标题" else "body",
                  excerpt=f.term, positioning="detector-offset") for f in findings]
    semantics = [dict(asdict(i), source="semantic", field="title" if i.location == "标题" else "body",
                      positioning="exact-quote") for i in (semantic.issues if semantic else ())]
    available = bool(semantic and semantic.available)
    return {"rules": rules, "semantic": semantics,
            "semantic_available": available,
            "status": "completed" if available else "partial_failure",
            "message": ("仍有疑似风险" if rules or semantics else "未发现明显风险") if available else
                       "语义审核未完成；仅有规则结果，允许重试。",
            "scope_note": "未发现明显风险不等于保证内容绝对合规，发布前仍需人工判断。"}


class Workspace:
    def __init__(self, rules, reviewer=None, drafter=None):
        self.rules = tuple(rules)
        self.reviewer = reviewer or review_semantics
        self.drafter = drafter or make_draft
        self.token = secrets.token_urlsafe(32)
        self.version = 0
        self.state = None
        self.final = None
        self.final_review = None
        self.final_status = "not_adopted"
        self.final_revision = 0
        self.error = ""
        self.seen = set()
        self.lock = RLock()
        self.touched = time.monotonic()

    def handle(self, event):
        with self.lock:
            self.touched = time.monotonic()
            if not isinstance(event, dict):
                raise ValueError("操作格式错误。")
            eid, version = event.get("id"), event.get("version")
            if not isinstance(eid, str) or not 1 <= len(eid) <= 100:
                raise ValueError("操作标识无效。")
            if eid in self.seen:
                return self.snapshot()
            if not isinstance(version, int) or isinstance(version, bool) or version != self.version:
                raise ValueError("稿件版本已变化，已忽略旧操作；请重试。")
            action = event.get("action")
            # Opening, typing in, and cancelling the dialog do not mutate saved state.
            if action == "cancel_edit":
                return self.snapshot()
            if action == "audit":
                title, body = document(event.get("document"))
                state = start_workflow(title, body, list(self.rules), self.reviewer, self.drafter)
                self.state = state
                self.final = self.final_review = None
                self.final_status = "not_adopted"
                self.final_revision = 0
            elif action == "reject":
                if not self.state or self.state.path != "needs_decision":
                    raise ValueError("当前没有待确认建议。")
                self.state = decide_workflow(self.state, "reject", self.reviewer)
                # Rejection does not turn the original into an adopted candidate.
                self.final = self.final_review = None
                self.final_status = "not_adopted"
            elif action in ("accept", "edit_accept", "save_final", "recheck"):
                if not self.state:
                    raise ValueError("请先审核原文。")
                if action in ("accept", "edit_accept"):
                    if self.state.path != "needs_decision" or not self.state.suggestion:
                        raise ValueError("当前没有待确认建议。")
                    draft = self.state.suggestion
                    title, body = document({"title": draft.title, "body": draft.body}
                                           if action == "accept" else event.get("document"))
                    self._save_final(title, body)
                elif action == "save_final":
                    if not self.final:
                        raise ValueError("当前没有最终采用稿。")
                    self._save_final(*document(event.get("document")))
                if action != "save_final":
                    if not self.final:
                        raise ValueError("当前没有最终采用稿。")
                    self.final_status = "running"
                    self.final_review = None
                    exact = Draft(self.final["title"], self.final["body"], "人工确认稿", "人工确认")
                    accepted = decide_workflow(replace(self.state, path="needs_decision", suggestion=exact),
                                               "accept", self.reviewer, confirmed_draft=exact)
                    self.final_review = review_payload(accepted.final_findings, accepted.final_semantic)
                    self.final_review["revision"] = self.final_revision
                    self.final_status = "completed" if accepted.final_semantic.available else "failed"
                    self.state = replace(accepted, suggestion=self.state.suggestion)
            else:
                raise ValueError("未知操作。")
            self.version += 1
            self.seen.add(eid)
            if len(self.seen) > 1000:
                self.seen = {eid}
            self.error = ""
            return self.snapshot()

    def _save_final(self, title, body):
        if self.state.original_title.strip() and not title.strip():
            raise ValueError("确认版标题不能为空。")
        candidate = {"title": title, "body": body}
        if candidate != self.final:
            self.final = candidate
            self.final_revision += 1
            self.final_review = None
            self.final_status = "pending"

    def snapshot(self):
        with self.lock:
            original = {"title": self.state.original_title, "body": self.state.original_body} if self.state else None
            draft = asdict(self.state.suggestion) if self.state and self.state.suggestion else None
            if draft:
                draft["error"] = "模型建议不可用，已回退为本地规则稿。" if draft["error"] else ""
            return {"version": self.version, "original": original, "draft": draft,
                    "original_review": review_payload(self.state.original_findings, self.state.semantic)
                        if self.state else None,
                    "path": self.state.path if self.state else "input", "final": self.final,
                    "final_revision": self.final_revision, "final_status": self.final_status,
                    "final_review": self.final_review, "error": self.error,
                    "draft_diff": differences(original, draft) if original and draft else [],
                    "diff": differences(original, self.final) if original and self.final else [],
                    "provenance": "real_v2"}


class WorkspaceRegistry:
    """Bounded, private, process-local refresh recovery; no persisted API credentials."""
    def __init__(self, ttl=3600, capacity=128):
        self.ttl, self.capacity = ttl, capacity
        self.items = {}
        self.lock = RLock()

    def acquire(self, token, rules):
        with self.lock:
            now = time.monotonic()
            self.items = {k: v for k, v in self.items.items() if now - v.touched < self.ttl}
            if isinstance(token, str) and token in self.items:
                self.items[token].touched = now
                return self.items[token], True
            if len(self.items) >= self.capacity:
                oldest = min(self.items, key=lambda k: self.items[k].touched)
                del self.items[oldest]
            work = Workspace(rules)
            self.items[work.token] = work
            return work, False


REGISTRY = WorkspaceRegistry()
