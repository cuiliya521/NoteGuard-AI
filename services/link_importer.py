from __future__ import annotations

import ipaddress
import json
import re
import socket
import ssl
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


MAX_RESPONSE_BYTES = 1_000_000
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_REDIRECTS = 5
REQUEST_TIMEOUT_SECONDS = 8

TRACKING_QUERY_KEYS = {
    "share_from_user_hidden",
    "share_id",
    "source",
    "timestamp",
}
DYNAMIC_MARKERS = (
    "__next_data__",
    "webpack",
    "window.__initial_state__",
    "id=\"app\"",
    "id=\"root\"",
)
LOGIN_MARKERS = ("登录后查看", "请先登录", "扫码登录", "login required", "sign in")
LIMIT_MARKERS = ("验证码", "访问频繁", "安全验证", "captcha", "too many requests")


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
        self.image_urls: list[str] = []
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
        if tag in {"img", "source"}:
            image_url = attributes.get("src") or attributes.get("data-src")
            if not image_url and attributes.get("srcset"):
                image_url = attributes["srcset"].split(",", 1)[0].strip().split(" ", 1)[0]
            if image_url:
                self.image_urls.append(image_url)
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
            return
        if not any(tag in {"script", "style", "noscript", "head"} for tag in self._tag_stack):
            self.text_parts.append(cleaned)


def clean_tracking_parameters(url: str) -> str:
    parsed = urlparse(url.strip())
    cleaned_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_KEYS
    ]
    return urlunparse(parsed._replace(query=urlencode(cleaned_query), fragment=""))


def validate_public_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise LinkImportError("链接格式不正确，请检查后重试。")

    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise LinkImportError("不支持本地或内网地址。")

    try:
        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(
                hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        }
    except socket.gaierror as error:
        raise LinkImportError("无法解析该链接的公开地址，请检查链接是否有效。") from error

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise LinkImportError("不支持本地、内网或保留地址。")
    return clean_tracking_parameters(parsed.geturl())


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


def _friendly_request_error(error: Exception) -> LinkImportError:
    if isinstance(error, HTTPError):
        if error.code == 404:
            return LinkImportError("页面不存在或链接已失效。")
        if error.code in {401, 403}:
            return LinkImportError("该页面可能需要登录，暂时无法自动读取。")
        if error.code == 429:
            return LinkImportError("页面触发访问频控或验证码，请稍后重试并使用手动输入。")
        return LinkImportError(f"页面返回 HTTP {error.code}，暂时无法读取。")
    if isinstance(error, (TimeoutError, socket.timeout)):
        return LinkImportError("访问超时，请稍后重试或使用手动输入。")
    if isinstance(error, ssl.SSLError):
        return LinkImportError("SSL 连接失败，请检查链接或稍后重试。")
    if isinstance(error, URLError):
        reason = error.reason
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return LinkImportError("访问超时，请稍后重试或使用手动输入。")
        if isinstance(reason, ssl.SSLError):
            return LinkImportError("SSL 连接失败，请检查链接或稍后重试。")
    return LinkImportError("网络连接异常，请稍后重试或使用手动输入。")


def _read_with_redirects(
    url: str,
    accepted_types: set[str],
    max_bytes: int,
    opener: Any | None = None,
) -> tuple[bytes, str, str, int]:
    current_url = validate_public_url(url)
    request_opener = opener or build_opener(NoRedirectHandler())

    for redirect_count in range(MAX_REDIRECTS + 1):
        request = Request(
            current_url,
            headers={
                "User-Agent": "AI-Reviewer-LinkImporter/1.1",
                "Accept": "text/html,application/xhtml+xml,image/*",
            },
        )
        try:
            response = request_opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS)
        except HTTPError as error:
            if 300 <= error.code < 400:
                location = error.headers.get("Location", "")
                if not location:
                    raise LinkImportError("页面发生跳转，但未提供有效目标地址。") from error
                if redirect_count >= MAX_REDIRECTS:
                    raise LinkImportError("页面跳转次数过多，请改用手动输入。") from error
                current_url = validate_public_url(urljoin(current_url, location))
                continue
            raise _friendly_request_error(error) from error
        except (URLError, TimeoutError, socket.timeout, ssl.SSLError, OSError) as error:
            raise _friendly_request_error(error) from error

        with response:
            content_type = response.headers.get_content_type().lower()
            if content_type not in accepted_types:
                raise LinkImportError("该链接返回的内容类型暂不支持读取。")
            content = response.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise LinkImportError("页面或图片内容过大，暂不支持自动读取。")
        return content, current_url, content_type, redirect_count

    raise LinkImportError("页面跳转次数过多，请改用手动输入。")


def _absolute_public_images(parser: PublicPageParser, final_url: str) -> list[str]:
    candidates = [
        parser.meta.get("og:image", ""),
        parser.meta.get("twitter:image", ""),
        *parser.image_urls,
    ]
    images: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        absolute = clean_tracking_parameters(urljoin(final_url, candidate))
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            continue
        if absolute not in images:
            images.append(absolute)
    return images[:10]


def parse_public_page(
    raw_html: bytes | str,
    original_url: str,
    final_url: str,
    redirect_count: int = 0,
) -> dict[str, Any]:
    html = raw_html.decode("utf-8", errors="replace") if isinstance(raw_html, bytes) else raw_html
    lowered_html = html.lower()
    if any(marker in lowered_html for marker in LOGIN_MARKERS):
        raise LinkImportError("该页面可能需要登录，暂时无法自动读取。")
    if any(marker in lowered_html for marker in LIMIT_MARKERS):
        raise LinkImportError("页面返回验证码或访问限制，请切换手动输入。")

    parser = PublicPageParser()
    parser.feed(html)
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
    body = _first_json_ld_value(parser.json_ld_parts, ("articleBody",)) or _clean_text(parser.text_parts)
    if body == title:
        body = ""

    is_dynamic = any(marker in lowered_html for marker in DYNAMIC_MARKERS)
    if not body:
        if title:
            status = "dynamic" if is_dynamic else "partial"
            status_message = (
                "页面使用动态加载，未能提取正文，请切换手动输入。"
                if is_dynamic
                else "当前只读取到标题，正文请手动补充。"
            )
        elif is_dynamic:
            raise LinkImportError("页面使用动态加载，未能提取正文，请切换手动输入。")
        else:
            raise LinkImportError("页面正文为空，请切换手动输入。")
    else:
        status = "success"
        status_message = "已读取公开标题和正文，请确认后导入。"

    images = _absolute_public_images(parser, final_url)
    return {
        "original_url": original_url,
        "source_url": final_url,
        "final_url": final_url,
        "redirect_count": redirect_count,
        "title": title,
        "body": body or description,
        "description": description,
        "image_url": images[0] if images else "",
        "image_urls": images,
        "status": status,
        "status_message": status_message,
    }


def import_public_page(url: str, opener: Any | None = None) -> dict[str, Any]:
    original_url = url.strip()
    public_url = validate_public_url(original_url)
    raw_html, final_url, _, redirect_count = _read_with_redirects(
        public_url,
        {"text/html", "application/xhtml+xml"},
        MAX_RESPONSE_BYTES,
        opener=opener,
    )
    return parse_public_page(
        raw_html,
        original_url=original_url,
        final_url=final_url,
        redirect_count=redirect_count,
    )


def download_public_image(url: str, opener: Any | None = None) -> bytes:
    image_bytes, _, _, _ = _read_with_redirects(
        url,
        {"image/png", "image/jpeg", "image/webp"},
        MAX_IMAGE_BYTES,
        opener=opener,
    )
    return image_bytes
