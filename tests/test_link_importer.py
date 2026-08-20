import socket
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from services.link_importer import (
    LinkImportError,
    PublicPageParser,
    clean_tracking_parameters,
    import_public_page,
    parse_public_page,
    validate_public_url,
)


class FakeHeaders:
    def __init__(self, content_type: str = "text/html") -> None:
        self.content_type = content_type

    def get_content_type(self) -> str:
        return self.content_type


class FakeResponse:
    def __init__(self, content: bytes, content_type: str = "text/html") -> None:
        self.content = content
        self.headers = FakeHeaders(content_type)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, _size: int) -> bytes:
        return self.content


class SequenceOpener:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses

    def open(self, _request, timeout: int):
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class LinkImporterTests(unittest.TestCase):
    def test_invalid_and_local_links_return_friendly_errors(self) -> None:
        with self.assertRaisesRegex(LinkImportError, "格式不正确"):
            import_public_page("not-a-url")
        with self.assertRaisesRegex(LinkImportError, "不支持"):
            validate_public_url("http://127.0.0.1/internal")

    def test_parser_reads_public_metadata_images_without_executing_scripts(self) -> None:
        parser = PublicPageParser()
        parser.feed(
            '<html><head><title>页面标题</title><meta property="og:description" content="页面描述">'
            '<meta property="og:image" content="https://example.com/cover.jpg"></head>'
            '<body><script>window.secret = "ignored"</script><p>公开正文</p>'
            '<img src="/second.png"></body></html>'
        )

        self.assertIn("页面标题", parser.title_parts)
        self.assertEqual(parser.meta["og:description"], "页面描述")
        self.assertIn("公开正文", parser.text_parts)
        self.assertIn("/second.png", parser.image_urls)
        self.assertFalse(any("window.secret" in item for item in parser.text_parts))

    def test_meta_cover_precedes_page_images_and_body_images_stay_separate(self) -> None:
        result = parse_public_page(
            '<html><head><meta property="og:title" content="数学案例">'
            '<meta property="og:image" content="/cover.jpg"></head>'
            '<body><p>公开正文</p><img src="/body-1.jpg"><img src="/body-2.jpg"></body></html>',
            "https://www.xiaohongshu.com/explore/123",
            "https://www.xiaohongshu.com/explore/123",
        )

        self.assertEqual(result["cover_image_url"], "https://www.xiaohongshu.com/cover.jpg")
        self.assertEqual(result["cover_image_source"], "分享图")
        self.assertEqual(
            result["content_image_urls"],
            [
                "https://www.xiaohongshu.com/body-1.jpg",
                "https://www.xiaohongshu.com/body-2.jpg",
            ],
        )
        self.assertEqual(result["image_url"], result["cover_image_url"])
        self.assertEqual(result["image_urls"][0], result["cover_image_url"])

    def test_first_displayed_image_is_cover_when_metadata_is_missing(self) -> None:
        result = parse_public_page(
            '<html><head><title>数学案例</title></head><body><p>公开正文</p>'
            '<img src="/first.jpg"><img src="/second.jpg"></body></html>',
            "https://example.com/note",
            "https://example.com/note",
        )

        self.assertEqual(result["cover_image_url"], "https://example.com/first.jpg")
        self.assertEqual(result["cover_image_source"], "页面首张展示图片")
        self.assertEqual(result["content_image_urls"], ["https://example.com/second.jpg"])

    def test_structured_image_is_used_before_page_images(self) -> None:
        result = parse_public_page(
            '<html><head><title>数学案例</title>'
            '<meta property="og:image" content="/shared-preview.jpg">'
            '<script type="application/ld+json">{"image":"/structured-cover.jpg"}</script>'
            '</head><body><p>公开正文</p><img src="/body.jpg"></body></html>',
            "https://example.com/note",
            "https://example.com/note",
        )

        self.assertEqual(result["cover_image_url"], "https://example.com/structured-cover.jpg")
        self.assertEqual(result["cover_image_source"], "结构化数据")
        self.assertEqual(result["content_image_urls"], ["https://example.com/body.jpg"])

    def test_xiaohongshu_note_image_list_overrides_incorrect_meta_image(self) -> None:
        html = (
            '<html><head><meta property="og:title" content="数学案例">'
            '<meta property="og:image" content="https://cdn.example.com/wrong-second.jpg"></head>'
            '<body><p>公开正文</p><script>'
            'window.__INITIAL_STATE__={"note":{"noteDetailMap":{"note123":{"note":'
            '{"noteId":"note123","imageList":['
            '{"urlDefault":"https:\\/\\/cdn.example.com\\/real-cover.jpg"},'
            '{"urlDefault":"https:\\/\\/cdn.example.com\\/body-2.jpg"}'
            ']}}}}};'
            '</script></body></html>'
        )
        result = parse_public_page(
            html,
            "https://www.xiaohongshu.com/explore/note123",
            "https://www.xiaohongshu.com/explore/note123",
        )

        self.assertEqual(result["cover_image_url"], "https://cdn.example.com/real-cover.jpg")
        self.assertEqual(result["cover_image_source"], "笔记首图")
        self.assertEqual(result["content_image_urls"], ["https://cdn.example.com/body-2.jpg"])

    def test_xiaohongshu_page_img_is_not_promoted_to_cover(self) -> None:
        result = parse_public_page(
            '<html><head><title>数学案例</title></head>'
            '<body><p>公开正文</p><img src="https://cdn.example.com/promo.jpg"></body></html>',
            "https://www.xiaohongshu.com/explore/note-without-state",
            "https://www.xiaohongshu.com/explore/note-without-state",
        )

        self.assertEqual(result["cover_image_url"], "")
        self.assertEqual(result["cover_image_source"], "未提取到")
        self.assertEqual(result["content_image_urls"], ["https://cdn.example.com/promo.jpg"])

    def test_xiaohongshu_unavailable_page_is_not_imported_as_a_note(self) -> None:
        with self.assertRaisesRegex(LinkImportError, "笔记已失效"):
            parse_public_page(
                '<html><head><title>小红书 - 你访问的页面不见了</title>'
                '<meta property="og:image" content="https://picasso-static.xiaohongshu.com/fe-platform/error.png">'
                '</head><body>你访问的页面不见了</body></html>',
                "https://www.xiaohongshu.com/explore/missing",
                "https://www.xiaohongshu.com/explore/missing",
            )

    def test_login_page_returns_login_specific_message(self) -> None:
        with self.assertRaisesRegex(LinkImportError, "需要登录"):
            parse_public_page(
                "<html><body>请先登录后查看</body></html>",
                "https://example.com/share",
                "https://example.com/note",
            )

    def test_dynamic_page_without_body_returns_manual_input_status(self) -> None:
        result = parse_public_page(
            '<html><head><title>公开标题</title></head><body><div id="root"></div></body></html>',
            "https://example.com/share",
            "https://example.com/note",
        )

        self.assertEqual(result["status"], "dynamic")
        self.assertIn("动态加载", result["status_message"])

    def test_redirect_records_final_url(self) -> None:
        redirect = HTTPError(
            "https://example.com/share",
            302,
            "redirect",
            {"Location": "https://example.com/note?utm_source=test"},
            None,
        )
        opener = SequenceOpener(
            [redirect, FakeResponse(b"<html><title>Title</title><body>Body text</body></html>")]
        )
        with patch(
            "services.link_importer.validate_public_url",
            side_effect=lambda value: clean_tracking_parameters(value),
        ):
            result = import_public_page("https://example.com/share", opener=opener)

        self.assertEqual(result["final_url"], "https://example.com/note")
        self.assertEqual(result["redirect_count"], 1)

    def test_title_only_is_partial_not_exception(self) -> None:
        result = parse_public_page(
            "<html><head><title>只提取到标题</title></head><body></body></html>",
            "https://example.com/note",
            "https://example.com/note",
        )

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["title"], "只提取到标题")
        self.assertIn("正文请手动补充", result["status_message"])

    def test_timeout_returns_timeout_specific_message(self) -> None:
        opener = SequenceOpener([socket.timeout("slow")])
        with patch("services.link_importer.validate_public_url", side_effect=lambda value: value):
            with self.assertRaisesRegex(LinkImportError, "访问超时"):
                import_public_page("https://example.com/note", opener=opener)

    def test_tracking_parameters_are_removed_but_required_query_is_kept(self) -> None:
        cleaned = clean_tracking_parameters(
            "https://www.xiaohongshu.com/explore/123?xsec_token=keep&utm_source=remove#fragment"
        )

        self.assertEqual(
            cleaned,
            "https://www.xiaohongshu.com/explore/123?xsec_token=keep",
        )


if __name__ == "__main__":
    unittest.main()
