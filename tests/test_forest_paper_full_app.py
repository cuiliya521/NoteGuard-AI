"""Complete app routing integration; no online AI assertions or key access."""
from streamlit.testing.v1 import AppTest
from unittest.mock import patch


def test_full_app_flag_default_navigation_and_return(monkeypatch):
    monkeypatch.setenv('NOTEGUARD_FOREST_PAPER', '1')
    app = AppTest.from_file('app.py').run(timeout=30)
    assert not app.exception
    assert app.session_state['workspace_page'] == '协作审核 V2'
    work = app.session_state['forest_workspace']
    for page in ('招生笔记助手', '历史与资产', '审核规则中心'):
        app.session_state['forest_navigate_to'] = page
        app.run(timeout=30)
        assert not app.exception
        assert app.session_state['workspace_page'] == page
        app.radio(key='workspace_page').set_value('协作审核 V2').run(timeout=30)
        assert not app.exception
        assert app.session_state['forest_workspace'] is work
        assert any('noteguard_forest_paper_v2' in str(e.proto) for e in app.get('component_instance'))


def test_component_navigation_reaches_original_complete_app(monkeypatch):
    monkeypatch.setenv('NOTEGUARD_FOREST_PAPER', '1')
    from services import forest_paper_ui_v2 as ui
    original = ui.component
    app = AppTest.from_file('app.py').run(timeout=30)
    for index, (slug, page) in enumerate((('notes','招生笔记助手'),('history','历史与资产'),('rules','审核规则中心'))):
        delivered = False
        def navigate(**kwargs):
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'id': f'route-{index}', 'action':'navigate', 'page':slug}
            return original(**kwargs)
        with patch.object(ui, 'component', side_effect=navigate):
            app.run(timeout=30)
        assert not app.exception
        assert app.session_state['workspace_page'] == page
        app.radio(key='workspace_page').set_value('协作审核 V2').run(timeout=30)
        assert not app.exception


def test_flag_disabled_keeps_existing_default(monkeypatch):
    monkeypatch.delenv('NOTEGUARD_FOREST_PAPER', raising=False)
    app = AppTest.from_file('app.py').run(timeout=30)
    assert not app.exception
    assert app.session_state['workspace_page'] == '内容审核中心'
