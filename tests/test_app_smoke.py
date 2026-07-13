import unittest

from streamlit.testing.v1 import AppTest


class AppSmokeTests(unittest.TestCase):
    def test_navigation_and_draft_persist_between_pages(self) -> None:
        app = AppTest.from_file("app.py")
        app.run(timeout=30)
        app.button(key="load_experience_case_button").click()
        app.run(timeout=30)

        title = app.text_input(key="title_input").value
        body = app.text_area(key="body_input").value
        app.radio[0].set_value("封面诊断")
        app.run(timeout=30)
        self.assertEqual(len(app.exception), 0)

        app.radio[0].set_value("创作工作台")
        app.run(timeout=30)
        self.assertEqual(app.text_input(key="title_input").value, title)
        self.assertEqual(app.text_area(key="body_input").value, body)
        self.assertEqual(len(app.exception), 0)
