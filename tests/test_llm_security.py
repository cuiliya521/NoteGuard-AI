from contextlib import redirect_stdout
from io import StringIO
import unittest

from services.llm import print_deepseek_diagnostics


class LlmSecurityTests(unittest.TestCase):
    def test_diagnostics_never_log_api_key_characters(self) -> None:
        api_key = "sk-test-secret-ABC123456789"
        output = StringIO()

        with redirect_stdout(output):
            print_deepseek_diagnostics(api_key)

        diagnostic = output.getvalue()
        self.assertEqual(
            diagnostic,
            "key_loaded=True provider_status=configured\n",
        )
        self.assertNotIn(api_key, diagnostic)
        for fragment in ("sk-test", "secret", "ABC123", "key_prefix", "key_length"):
            self.assertNotIn(fragment, diagnostic)

    def test_diagnostics_only_report_missing_key_status(self) -> None:
        output = StringIO()

        with redirect_stdout(output):
            print_deepseek_diagnostics("")

        self.assertEqual(
            output.getvalue(),
            "key_loaded=False provider_status=missing_key\n",
        )


if __name__ == "__main__":
    unittest.main()
