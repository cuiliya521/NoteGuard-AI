"""Native UI integration. Provider responses here are explicit mocks, not online evidence."""
import hashlib
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from services.notes_forest_paper_ui import workflow_stage


SOURCE = {"cover_theme": "错题复盘", "target_audience": "初二学生家长",
          "selling_direction": "错题方法", "teacher_cues": "素材中的老师"}
ANALYSIS = {"user_pain_expression": "同类题反复出错", "conversion_elements": ["咨询"],
            "copy_structure": {"target_audience": "初二学生家长", "pain_point": "同类题反复出错"}}
DRAFT = {"titles": [f"测试标题{i}" for i in range(5)],
         "cover_copy": {"main_title": "测试封面", "visual_suggestion": "使用真实场景"},
         "body": {"full_text": "自动化测试正文，仅用于测试。"},
         "publishing": {"tags": ["#测试"], "comment_question": "测试问题"}}


def notes(monkeypatch, flag="1"):
    monkeypatch.setenv("NOTEGUARD_FOREST_PAPER_NOTES", flag)
    app = AppTest.from_file("app.py").run(timeout=30)
    app.session_state["forest_navigate_to"] = "招生笔记助手"
    app.run(timeout=30)
    assert not app.exception
    return app


def button(app, label):
    return next(b for b in app.button if b.label == label)


def test_flag_off_restores_legacy_notes(monkeypatch):
    app = notes(monkeypatch, "0")
    assert any("step-indicator" in x.value for x in app.markdown)
    assert not any("ngn-heading" in x.value for x in app.markdown)
    assert not any((b.key or "").startswith("ngnotes-nav") for b in app.button)


def test_empty_material_and_empty_link_do_not_call_ai(monkeypatch):
    with patch("services.llm.analyze_note_image_source") as source:
        app = notes(monkeypatch)
        button(app, "读取内容").click().run(timeout=30)
        assert any("请先粘贴" in i.value for i in app.info)
        assert not any(b.label == "开始拆解同行内容" for b in app.button)
        source.assert_not_called()


def test_native_breakdown_generation_edit_audit_and_return(monkeypatch):
    with (patch("services.llm.analyze_note_image_source", return_value=SOURCE) as source,
          patch("services.llm.analyze_viral_image", return_value=ANALYSIS),
          patch("services.llm.generate_content_lab_draft", return_value=DRAFT) as generate):
        app = notes(monkeypatch)
        app.text_input(key="content_lab_material_title").set_value("输入素材标题")
        app.text_area(key="content_lab_material_body").set_value("输入素材正文").run(timeout=30)
        source.assert_not_called()
        button(app, "开始拆解同行内容").click().run(timeout=30)
        assert not app.exception
        assert any('class="ngn-insights"' in x.value and "初二学生家长" in x.value for x in app.markdown)
        app.text_input(key="content_lab_confirm_product_name").set_value("人工确认的业务").run(timeout=30)
        button(app, "🔥 生成我的招生笔记").click().run(timeout=30)
        assert not app.exception
        assert generate.call_args.args[2]["product_name"] == "人工确认的业务"
        assert workflow_stage(app.session_state.filtered_state) == 4
        app.text_area(key="content_lab_draft_full_text").set_value("人工编辑的最终正文").run(timeout=30)
        app.radio(key="content_lab_draft_selected_title").set_value("测试标题2").run(timeout=30)
        button(app, "一键审核").click().run(timeout=30)
        assert not app.exception
        assert app.session_state["workspace_page"] == "内容审核中心"
        assert app.session_state["draft_body"] == "人工编辑的最终正文"
        assert app.session_state["draft_title"] == "测试标题2"
        app.radio(key="workspace_page").set_value("招生笔记助手").run(timeout=30)
        assert app.text_area(key="content_lab_draft_full_text").value == "人工编辑的最终正文"
        button(app, "内容审核").click().run(timeout=30)
        assert app.session_state["workspace_page"] == "协作审核 V2"
        assert not any("ngn-heading" in x.value for x in app.markdown)
        assert not app.exception


def test_changed_material_does_not_show_old_analysis_as_current(monkeypatch):
    with (patch("services.llm.analyze_note_image_source", return_value=SOURCE),
          patch("services.llm.analyze_viral_image", return_value=ANALYSIS)):
        app = notes(monkeypatch)
        app.text_area(key="content_lab_material_body").set_value("第一份素材").run(timeout=30)
        button(app, "开始拆解同行内容").click().run(timeout=30)
        assert workflow_stage(app.session_state.filtered_state) == 3
        app.text_area(key="content_lab_material_body").set_value("另一份素材").run(timeout=30)
        assert workflow_stage(app.session_state.filtered_state) == 2
        assert not any('class="ngn-insights"' in x.value for x in app.markdown)
        assert not any(b.label == "🔥 生成我的招生笔记" for b in app.button)


def test_failure_is_explicit_and_retryable(monkeypatch):
    with (patch("services.llm.analyze_note_image_source", return_value=None),
          patch("services.llm.analyze_viral_image", return_value=None),
          patch("services.llm.get_last_error", return_value="自动化模拟的服务失败")):
        app = notes(monkeypatch)
        app.text_area(key="content_lab_material_body").set_value("测试失败素材").run(timeout=30)
        button(app, "开始拆解同行内容").click().run(timeout=30)
        assert workflow_stage(app.session_state.filtered_state) == 2
        assert any("未完整完成" in x.value for x in app.warning)
        assert any(b.label == "开始拆解同行内容" for b in app.button)
        assert not app.exception


def test_generation_failure_keeps_material_and_business(monkeypatch):
    with (patch("services.llm.analyze_note_image_source", return_value=SOURCE),
          patch("services.llm.analyze_viral_image", return_value=ANALYSIS),
          patch("services.llm.generate_content_lab_draft", return_value=None),
          patch("services.llm.get_last_error", return_value="自动化模拟的生成失败")):
        app = notes(monkeypatch)
        app.text_area(key="content_lab_material_body").set_value("保留的素材").run(timeout=30)
        button(app, "开始拆解同行内容").click().run(timeout=30)
        button(app, "🔥 生成我的招生笔记").click().run(timeout=30)
        assert any("生成暂时不可用" in x.value for x in app.info)
        assert app.text_area(key="content_lab_material_body").value == "保留的素材"
        assert "content_lab_generated_draft" not in app.session_state
        assert not app.exception


def test_link_import_populates_existing_material_state(monkeypatch):
    with patch("services.link_importer.import_public_page", return_value={
        "title": "导入的测试标题", "body": "导入的测试正文", "image_urls": []
    }) as importer:
        app = notes(monkeypatch)
        app.text_input(key="content_growth_link_url").set_value("https://www.xiaohongshu.com/explore/test").run(timeout=30)
        button(app, "读取内容").click().run(timeout=30)
        assert importer.call_count == 1
        assert app.text_input(key="content_lab_material_title").value == "导入的测试标题"
        assert app.text_area(key="content_lab_material_body").value == "导入的测试正文"
        assert not app.exception


def test_upload_keeps_shared_ocr_and_image_metadata(monkeypatch):
    from io import BytesIO
    from PIL import Image
    from services.image_ocr import OcrExtractionResult
    image = BytesIO()
    Image.new("RGB", (120, 160), "white").save(image, format="PNG")
    result = OcrExtractionResult(lines=["测试素材"], error="", average_confidence=95,
                                 engine="自动化模拟 OCR", cover_text="测试素材")
    with patch("services.image_ocr.extract_cover_text_details", return_value=result):
        app = notes(monkeypatch)
        app.file_uploader(key="content_lab_material_upload").set_value(("test.png", image.getvalue(), "image/png")).run(timeout=30)
        assert app.session_state["content_lab_material_image_source"] == "upload"
        assert app.session_state["content_lab_cover_text"] == "测试素材"
        assert app.session_state["content_lab_material_image_width"] == 120
        assert not app.exception


def test_stage_requires_current_analysis_and_never_marks_failure_done():
    state = {"content_lab_material_body": "正文"}
    assert workflow_stage(state) == 2
    state.update(content_lab_material_analysis_key=hashlib.sha256("\n\n正文\n".encode()).hexdigest(),
                 content_lab_material_suggestion={})
    assert workflow_stage(state) == 3
    state["content_lab_generated_draft"] = DRAFT
    assert workflow_stage(state) == 4
    state["content_lab_material_error"] = "失败"
    assert workflow_stage(state) == 2


def test_demo_identity_stays_visible_and_history_does_not_inherit_notes_css(monkeypatch):
    app = notes(monkeypatch)
    app.session_state["demo_mode"] = True
    app.run(timeout=30)
    assert any("Demo 模式" in x.value for x in app.info)
    assert any("虚构演示账号" in x.value for x in app.info)
    button(app, "历史与资产").click().run(timeout=30)
    assert app.session_state["workspace_page"] == "历史与资产"
    assert not any("ngn-heading" in x.value for x in app.markdown)
    assert not app.exception
