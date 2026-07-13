from __future__ import annotations

import ipaddress
import json
import re
import socket
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


MAX_RESPONSE_BYTES = 1_000_000
REQUEST_TIMEOUT_SECONDS = 8


class LinkImportError(ValueError):
    pass


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class PublicPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.json_ld_parts: list[str] = []
        self._tag_stack: list[str] = []
        self._capture_json_ld = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attributes = {key.lower(): value or "" for key, value in attrs}
        if tag not in {"meta", "link", "img", "br", "input", "source"}:
            self._tag_stack.append(tag)
        if tag == "meta":
            name = (attributes.get("property") or attributes.get("name") or "").lower()
            content = attributes.get("content", "").strip()
            if name and content:
                self.meta[name] = content
        if tag == "script" and attributes.get("type", "").lower() == "application/ld+json":
            self._capture_json_ld = True

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "script":
            self._capture_json_ld = False
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(unescape(data).split())
        if not cleaned:
            return
        if self._capture_json_ld:
            self.json_ld_parts.append(cleaned)
            return
        if "title" in self._tag_stack:
            self.title_parts.append(cleaned)
        if not any(tag in {"script", "style", "noscript"} for tag in self._tag_stack):
            self.text_parts.append(cleaned)


def validate_public_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise LinkImportError("仅支持公开的 http 或 https 链接。")

    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise LinkImportError("不支持本地或内网地址。")

    try:
        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as error:
        raise LinkImportError("无法解析该链接的公开地址。") from error

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise LinkImportError("不支持本地、内网或保留地址。")
    return parsed.geturl()


def _first_json_ld_value(parts: list[str], keys: tuple[str, ...]) -> str:
    for part in parts:
        try:
            value = json.loads(part)
        except json.JSONDecodeError:
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            if not isinstance(item, dict):
                continue
            for key in keys:
                candidate = item.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
    return ""


def _clean_text(parts: list[str], limit: int = 6000) -> str:
    joined = "\n".join(parts)
    joined = re.sub(r"\n{2,}", "\n", joined)
    return joined[:limit].strip()


def import_public_page(url: str) -> dict[str, str]:
    public_url = validate_public_url(url)
    request = Request(
        public_url,
        headers={
            "User-Agent": "AI-Reviewer-LinkImporter/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    opener = build_opener(NoRedirectHandler())

    try:
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise LinkImportError("该链接不是可读取的公开网页。")
            raw_html = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        if 300 <= error.code < 400:
            raise LinkImportError("该链接需要跳转，暂不自动跟随跳转。") from error
        raise LinkImportError("该链接暂时无法读取，可能需要登录或页面限制访问。") from error
    except (URLError, TimeoutError, OSError) as error:
        raise LinkImportError("该链接暂时无法读取，可能需要登录或页面限制访问。") from error

    if len(raw_html) > MAX_RESPONSE_BYTES:
        raise LinkImportError("页面内容过大，暂不支持自动读取。")

    parser = PublicPageParser()
    parser.feed(raw_html.decode("utf-8", errors="replace"))
    title = (
        parser.meta.get("og:title")
        or _first_json_ld_value(parser.json_ld_parts, ("headline", "name"))
        or _clean_text(parser.title_parts, limit=200)
    )
    description = (
        parser.meta.get("og:description")
        or parser.meta.get("description")
        or _first_json_ld_value(parser.json_ld_parts, ("description",))
    )
    body = _first_json_ld_value(parser.json_ld_parts, ("articleBody", "description")) or _clean_text(parser.text_parts)
    if not title and not body and not description:
        raise LinkImportError("未读取到可用于拆解的公开标题或正文。")

    return {
        "source_url": public_url,
        "title": title,
        "body": body or description,
        "description": description,
        "image_url": parser.meta.get("og:image", ""),
    }
