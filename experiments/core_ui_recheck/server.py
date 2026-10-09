"""Loopback-only, same-origin test server. No production configuration changes."""
from __future__ import annotations
import argparse
import json
import secrets
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from .adapter import V2Engine, InputError, environment_key

WEB = Path(__file__).with_name("web")
MAX_BYTES = 40000

class TestServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, engine):
        super().__init__(address, Handler)
        self.engine = engine
        self.sessions = {}
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(2)

class Handler(BaseHTTPRequestHandler):
    server_version = "NoteGuardTest/1"
    def log_message(self, *args):
        # Deliberately do not log bodies, provider errors, cookies or secrets.
        pass

    def session(self, create=False):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except Exception:
            pass
        sid = cookies.get("ng_test_session")
        sid = sid.value if sid else ""
        with self.server.lock:
            now = time.monotonic()
            expired = [key for key, value in self.server.sessions.items() if now - value["created"] > 3600]
            for key in expired:
                self.server.sessions.pop(key, None)
            data = self.server.sessions.get(sid)
            if data is None and create:
                if len(self.server.sessions) >= 100:
                    return "", None
                sid = secrets.token_urlsafe(32)
                data = {"csrf": secrets.token_urlsafe(32), "created": now, "audits": {}}
                self.server.sessions[sid] = data
        return sid, data

    def send_json(self, code, payload, cookie=None):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.headers_common()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if cookie:
            self.send_header("Set-Cookie", "ng_test_session=" + cookie + "; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600")
        self.end_headers()
        self.wfile.write(data)

    def headers_common(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")

    def allowed_host(self):
        host = self.headers.get("Host", "")
        port = self.server.server_address[1]
        return host in {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}

    def do_GET(self):
        if not self.allowed_host():
            return self.send_json(403, {"error": "仅允许本机测试来源。"})
        path = urlsplit(self.path).path
        if path == "/api/health":
            sid, session = self.session(True)
            if not session:
                return self.send_json(503, {"error": "测试会话已满。"})
            return self.send_json(200, {"mode": "isolated_v2_test", "csrf": session["csrf"],
                "provider_configured": bool(environment_key()), "rules_ready": True}, sid)
        allowed = {"/": "index.html", "/index.html": "index.html", "/workflow.js": "workflow.js", "/master.html": "master.html"}
        file = WEB / allowed.get(path, "__not_found__")
        if not file.is_file():
            return self.send_json(404, {"error": "未找到资源。"})
        data = file.read_bytes()
        self.send_response(200)
        self.headers_common()
        self.send_header("Content-Type", "text/javascript; charset=utf-8" if file.suffix == ".js" else "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        sid, session = self.session()
        origin = self.headers.get("Origin")
        if (not self.allowed_host() or not session or
            not secrets.compare_digest(self.headers.get("X-NoteGuard-CSRF", ""), session["csrf"]) or
            (origin and origin != "http://" + self.headers.get("Host", ""))):
            return self.send_json(403, {"error": "测试会话或来源无效，请刷新页面重试。"})
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self.send_json(415, {"error": "仅接受 JSON。"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_BYTES:
                return self.send_json(413, {"error": "请求大小无效。"})
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise InputError("请求必须为 JSON 对象。")
        except (ValueError, UnicodeDecodeError):
            return self.send_json(400, {"error": "请求格式无效。"})
        if not self.server.slots.acquire(blocking=False):
            return self.send_json(429, {"error": "审核繁忙，请稍后重试。"})
        try:
            path = urlsplit(self.path).path
            if path in {"/api/audit", "/api/recheck"}:
                result, internal = self.server.engine.audit(payload)
                if path == "/api/audit":
                    audit_id = secrets.token_urlsafe(24)
                    with self.server.lock:
                        if len(session["audits"]) >= 20:
                            session["audits"].pop(next(iter(session["audits"])))
                        session["audits"][audit_id] = (result, internal)
                    result["audit_id"] = audit_id
                result["purpose"] = "original" if path == "/api/audit" else "final"
                return self.send_json(200, result)
            if path == "/api/suggest":
                with self.server.lock:
                    audit = session["audits"].get(payload.get("audit_id", ""))
                if not audit or payload.get("content_hash") != audit[0]["content_hash"]:
                    return self.send_json(409, {"error": "原文检测已失效，请重新检测后生成建议。"})
                result = self.server.engine.suggest(audit[1])
                result.update(audit_id=payload["audit_id"], content_hash=audit[0]["content_hash"],
                              request_id=payload.get("request_id"))
                return self.send_json(200, result)
            return self.send_json(404, {"error": "未找到接口。"})
        except InputError as exc:
            return self.send_json(400, {"error": str(exc)})
        except Exception:
            return self.send_json(502, {"error": "审核服务失败，请重试；未生成检测结论。"})
        finally:
            self.server.slots.release()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8877)
    args = parser.parse_args()
    server = TestServer(("127.0.0.1", args.port), V2Engine())
    print(f"独立本机测试环境：http://127.0.0.1:{args.port}/；provider_configured={bool(environment_key())}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
