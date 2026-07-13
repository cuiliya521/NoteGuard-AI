import unittest

from services.link_importer import LinkImportError, PublicPageParser, import_public_page, validate_public_url


class LinkImporterTests(unittest.TestCase):
    def test_invalid_and_local_links_return_friendly_errors(self) -> None:
        with self.assertRaisesRegex(LinkImportError, "仅支持公开"):
            import_public_page("not-a-url")
        with self.assertRaisesRegex(LinkImportError, "不支持"):
            validate_public_url("http://127.0.0.1/internal")

    def test_parser_reads_public_metadata_without_executing_scripts(self) -> None:
        parser = PublicPageParser()
        parser.feed(
            '<html><head><title>页面标题</title><meta property="og:description" content="页面描述"></head>'
            '<body><script>window.secret = "ignored"</script><p>公开正文</p></body></html>'
        )

        self.assertIn("页面标题", parser.title_parts)
        self.assertEqual(parser.meta["og:description"], "页面描述")
        self.assertIn("公开正文", parser.text_parts)
        self.assertFalse(any("window.secret" in item for item in parser.text_parts))
