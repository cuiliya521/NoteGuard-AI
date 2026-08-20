from io import BytesIO
import unittest
from unittest.mock import patch

from PIL import Image
from streamlit.testing.v1 import AppTest

from services.image_ocr import OcrExtractionResult


class AppSmokeTests(unittest.TestCase):
    def test_audit_center_keeps_image_review_without_generation_ui(self) -> None:
        image = BytesIO()
        Image.new("RGB", (80, 80), "white").save(image, format="PNG")
        app = AppTest.from_file("app.py")
        app.run(timeout=30)

        app.file_uploader[0].set_value(("cover.png", image.getvalue(), "image/png"))
        app.run(timeout=30)

        self.assertFalse(any(radio.key == "note_generation_mode" for radio in app.radio))
        self.assertNotIn("3. 生成发布稿", [expander.label for expander in app.expander])
        self.assertFalse(any(button.label == "生成完整发布稿" for button in app.button))
        self.assertTrue(
            any("图片文字识别失败，请检查OCR环境" in error.value for error in app.error)
        )
        self.assertEqual(len(app.exception), 0)

    def test_uploaded_cover_ocr_enters_rule_review_and_comparison(self) -> None:
        image = BytesIO()
        Image.new("RGB", (120, 120), "white").save(image, format="PNG")
        extraction = OcrExtractionResult(
            lines=["保证提分", "初二数学"],
            error="",
            average_confidence=96,
            engine="PaddleOCR:contrast",
            cover_text="保证提分\n初二数学",
        )
        app = AppTest.from_file("app.py")
        app.run(timeout=30)

        with patch("services.image_ocr.extract_cover_text_details", return_value=extraction):
            app.file_uploader[0].set_value(("cover.png", image.getvalue(), "image/png"))
            app.run(timeout=30)

        self.assertEqual(app.session_state["cover_text"], "保证提分\n初二数学")
        self.assertEqual(app.session_state["cover_ocr_status"], "success")
        app.button(key="start_review_button").click()
        app.run(timeout=30)
        self.assertTrue(any(button.label == "查看：保证提分" for button in app.button))
        self.assertTrue(any(expander.label == "查看已识别的封面文字" for expander in app.expander))
        self.assertEqual(len(app.exception), 0)

    def test_navigation_exposes_content_growth_assistant(self) -> None:
        app = AppTest.from_file("app.py")
        app.run(timeout=30)

        navigation_options = app.radio(key="workspace_page").options
        self.assertEqual(len(navigation_options), 4)
        for page in ("内容审核中心", "招生笔记助手", "历史与资产", "审核规则中心"):
            self.assertTrue(any(page in option for option in navigation_options))
        app.radio(key="workspace_page").set_value("招生笔记助手")
        app.run(timeout=30)
        self.assertTrue(
            any(text_input.label == "小红书公开链接" for text_input in app.text_input)
        )
        self.assertEqual(
            sum(
                expander.label == "🔬 高级玩法（运营人员使用）"
                for expander in app.expander
            ),
            1,
        )
        visible_markdown = "\n".join(item.value for item in app.markdown)
        for step in (
            "找参考爆款",
            "AI告诉我为什么它能招生",
            "生成我的招生笔记",
            "一键审核",
        ):
            self.assertIn(step, visible_markdown)
        self.assertFalse(any(text_input.label == "本次推广主题" for text_input in app.text_input))
        self.assertFalse(any(button.label == "生成完整发布稿" for button in app.button))
        self.assertEqual(len(app.exception), 0)

    def test_content_lab_material_analysis_prefills_confirmation_card(self) -> None:
        source_result = {
            "cover_theme": "初二数学规划",
            "visual_elements": ["标题文字"],
            "target_audience": "初二学生家长",
            "selling_direction": "真实错题复盘",
            "content_type": "学习方法分享",
            "teacher_cues": "林老师数学",
            "analysis_basis": "标题与OCR文字",
        }
        image_result = {
            "user_pain_expression": "听懂但考试不会做",
            "conversion_elements": ["评论区领取错题清单"],
            "copy_structure": {
                "target_audience": "初二学生家长",
                "pain_point": "听懂但考试不会做",
                "credibility": "林老师数学",
                "service_information": "初二数学规划",
            },
        }
        generated_draft = {
            "titles": ["标题1", "标题2", "标题3", "标题4", "标题5"],
            "cover_copy": {
                "main_title": "初二数学错题怎么复盘",
                "subtitle": "期中考试后的调整方法",
                "visual_suggestion": "主标题优先",
            },
            "body": {
                "opening_hook": "先看错题原因。",
                "user_pain": "同类题反复出错。",
                "real_experience": "基于已确认素材说明。",
                "solution": "按题型整理。",
                "product_intro": "提供学习规划支持。",
                "action_guide": "从最近一张试卷开始。",
                "full_text": "完整正文" * 210,
            },
            "publishing": {
                "tags": ["#数学", "#初二", "#错题", "#学习方法", "#家长"],
                "timing_advice": "结合账号历史数据测试。",
                "reused_points": ["问题 → 方法 → 行动"],
            },
        }
        with (
            patch("services.llm.analyze_note_image_source", return_value=source_result),
            patch("services.llm.analyze_viral_image", return_value=image_result),
            patch("services.llm.generate_content_lab_draft", return_value=generated_draft),
        ):
            app = AppTest.from_file("app.py")
            app.run(timeout=30)
            app.radio(key="workspace_page").set_value("招生笔记助手")
            app.run(timeout=30)
            app.text_input(key="content_lab_material_title").set_value("初二数学错题复盘")
            app.run(timeout=30)
            next(
                button for button in app.button
                if button.label == "🔥 生成我的招生笔记"
            ).click()
            app.run(timeout=30)

        self.assertTrue(app.session_state["content_lab_confirm_product_name"])
        self.assertTrue(app.text_input(key="content_lab_confirm_target_user").value)
        self.assertEqual(len(app.session_state["content_lab_generated_draft"]["titles"]), 5)
        self.assertTrue(
            any(text_area.label == "完整小红书正文" for text_area in app.text_area)
        )
        self.assertTrue(any("🔥 我的招生笔记" in item.value for item in app.markdown))
        self.assertTrue(
            any(radio.label == "选择一个标题作为最终标题" for radio in app.radio)
        )
        self.assertEqual(
            sum(
                expander.label == "🔬 高级玩法（运营人员使用）"
                for expander in app.expander
            ),
            1,
        )
        self.assertTrue(any("为什么它能招生" in item.value for item in app.markdown))
        self.assertTrue(any("家长痛点：" in item.value for item in app.markdown))
        self.assertTrue(any("成交钩子：" in item.value for item in app.markdown))
        self.assertTrue(any("内容结构：" in item.value for item in app.markdown))
        self.assertTrue(any("我的课程如何借：" in item.value for item in app.markdown))
        self.assertTrue(any("我的招生笔记" in item.value for item in app.markdown))
        self.assertTrue(any(button.label == "一键审核" for button in app.button))
        visible_text = "\n".join(item.value for item in app.markdown)
        self.assertNotIn("APIConnectionError", visible_text)
        self.assertNotIn("图片视觉分析失败", visible_text)
        self.assertEqual(len(app.exception), 0)

    def test_content_lab_upload_uses_shared_ocr_and_shows_paste_guidance(self) -> None:
        image = BytesIO()
        Image.new("RGB", (120, 160), "white").save(image, format="PNG")
        extraction = OcrExtractionResult(
            lines=["初二数学错题复盘", "期中考试后怎么调整"],
            error="",
            average_confidence=95,
            engine="PaddleOCR:contrast",
            cover_text="初二数学错题复盘\n期中考试后怎么调整",
        )
        with patch("services.image_ocr.extract_cover_text_details", return_value=extraction):
            app = AppTest.from_file("app.py")
            app.run(timeout=30)
            app.radio(key="workspace_page").set_value("招生笔记助手")
            app.run(timeout=30)
            app.file_uploader(key="content_lab_material_upload").set_value(
                ("material.png", image.getvalue(), "image/png")
            )
            app.run(timeout=30)

        self.assertEqual(
            app.session_state["content_lab_cover_text"],
            "初二数学错题复盘\n期中考试后怎么调整",
        )
        self.assertEqual(
            app.session_state["content_lab_image_ocr_result"]["engine"],
            "PaddleOCR:contrast",
        )
        self.assertEqual(
            app.session_state["content_lab_ocr_text"],
            "初二数学错题复盘\n期中考试后怎么调整",
        )
        self.assertEqual(
            app.session_state["content_lab_image_ocr_result"]["cover_text"],
            "初二数学错题复盘\n期中考试后怎么调整",
        )
        self.assertTrue(
            any(
                "支持拖拽上传" in caption.value
                for caption in app.caption
            )
        )
        self.assertEqual(app.session_state["content_lab_material_image_source"], "upload")
        visible_messages = " ".join(
            str(item.value)
            for collection in (app.warning, app.info, app.caption, app.markdown)
            for item in collection
        )
        self.assertNotIn("APIConnectionError", visible_messages)
        self.assertNotIn("OCR文字", visible_messages)
        self.assertEqual(len(app.exception), 0)

    def test_navigation_and_draft_persist_between_pages(self) -> None:
        app = AppTest.from_file("app.py")
        app.run(timeout=30)
        app.button(key="load_experience_case_button").click()
        app.run(timeout=30)

        metric_labels = [metric.label for metric in app.metric]
        self.assertIn("审核结论", metric_labels)
        self.assertIn("风险等级", metric_labels)
        self.assertIn("命中规则数量", metric_labels)
        self.assertNotIn("内容质量参考", metric_labels)
        self.assertFalse(any(expander.label == "详细风险与问题位置" for expander in app.expander))
        self.assertTrue(any(expander.label == "问题定位与左右对比" for expander in app.expander))

        title = app.text_input(key="title_input").value
        body = app.text_area(key="body_input").value
        finding_buttons = [
            button for button in app.button if str(button.key).startswith("audit_finding_")
        ]
        self.assertTrue(finding_buttons)
        finding_buttons[0].click()
        app.run(timeout=30)
        self.assertIn("selected_audit_finding", app.session_state)
        self.assertEqual(len(app.exception), 0)

        self.assertFalse(any(button.label == "标记已处理" for button in app.button))
        unchanged_title = app.text_input(key="title_input").value
        unchanged_body = app.text_area(key="body_input").value
        self.assertEqual((unchanged_title, unchanged_body), (title, body))

        app.radio(key="workspace_page").set_value("历史与资产")
        app.run(timeout=30)
        self.assertEqual(len(app.exception), 0)

        app.radio(key="workspace_page").set_value("内容审核中心")
        app.run(timeout=30)
        self.assertEqual(app.text_input(key="title_input").value, unchanged_title)
        self.assertEqual(app.text_area(key="body_input").value, unchanged_body)
        self.assertEqual(len(app.exception), 0)
