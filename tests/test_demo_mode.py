from unittest import TestCase
from unittest.mock import Mock

from services.demo_mode import (
    DEMO_COVER_ANALYSIS,
    DEMO_PRE_PUBLISH_REPORT,
    DEMO_TITLES,
    DEMO_VIRAL_ANALYSIS,
    DEMO_VIRAL_IMAGE_ANALYSIS,
    build_demo_note,
    resolve_demo_or_live,
)


class DemoModeTests(TestCase):
    def test_demo_mode_never_calls_live_provider(self) -> None:
        live_call = Mock(return_value={"source": "live"})

        result = resolve_demo_or_live(True, DEMO_VIRAL_ANALYSIS, live_call)

        live_call.assert_not_called()
        self.assertEqual(result["score"], 86)

    def test_normal_mode_keeps_live_flow(self) -> None:
        live_call = Mock(return_value={"source": "live"})

        result = resolve_demo_or_live(False, DEMO_VIRAL_ANALYSIS, live_call)

        live_call.assert_called_once_with()
        self.assertEqual(result, {"source": "live"})

    def test_demo_payloads_cover_public_product_results(self) -> None:
        self.assertEqual(len(DEMO_TITLES), 5)
        self.assertIn("title_analysis", DEMO_VIRAL_ANALYSIS)
        self.assertIn("suggestions", DEMO_VIRAL_ANALYSIS)
        self.assertIn("layout_structure", DEMO_VIRAL_IMAGE_ANALYSIS)
        self.assertIn("dimensions", DEMO_COVER_ANALYSIS)
        self.assertIn("final_advice", DEMO_PRE_PUBLISH_REPORT)
        self.assertEqual(len(build_demo_note(3)["titles"]), 3)

    def test_demo_results_are_copied_per_request(self) -> None:
        first = resolve_demo_or_live(True, DEMO_VIRAL_ANALYSIS, Mock())
        first["score"] = 0
        second = resolve_demo_or_live(True, DEMO_VIRAL_ANALYSIS, Mock())
        self.assertEqual(second["score"], 86)
