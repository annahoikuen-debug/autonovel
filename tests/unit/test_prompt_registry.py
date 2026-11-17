from unittest.mock import MagicMock

from src.services.prompt_registry import PromptRegistry


def test_prompt_registry_render_and_metrics():
    """PromptRegistry でのテンプレートレンダリングとメトリクス追跡の検証。"""
    mock_pm = MagicMock()
    mock_template = MagicMock()
    mock_template.render.return_value = "Hello World: Taro"
    mock_pm.get_template.return_value = mock_template

    registry = PromptRegistry(mock_pm)

    # 取得実行
    rendered = registry.get("greeting_template", name="Taro")
    assert rendered == "Hello World: Taro"
    mock_template.render.assert_called_once_with(name="Taro")

    # メトリクス確認
    all_metrics = registry.get_metrics()
    assert "greeting_template" in all_metrics
    assert all_metrics["greeting_template"]["hits"] == 1
    assert all_metrics["greeting_template"]["total_time_ms"] >= 0


def test_prompt_registry_reset_metrics():
    """メトリクスのリセット機能の検証。"""
    mock_pm = MagicMock()
    mock_pm.get_template.return_value.render.return_value = "output"

    registry = PromptRegistry(mock_pm)
    registry.get("temp1")
    assert registry.get_metrics()["temp1"]["hits"] == 1

    registry.reset_metrics("temp1")
    assert "temp1" not in registry.get_metrics()


def test_prompt_registry_disabled_still_renders():
    """disable() 後もレンダリングは実行され、空文字列を返さないこと。"""
    mock_pm = MagicMock()
    mock_template = MagicMock()
    mock_template.render.return_value = "rendered output"
    mock_pm.get_template.return_value = mock_template

    registry = PromptRegistry(mock_pm)
    registry.disable()
    assert not registry.is_enabled()

    rendered = registry.get("greeting_template", name="Taro")
    assert rendered == "rendered output"
    mock_template.render.assert_called_once_with(name="Taro")


def test_prompt_registry_invalidate_reflects_update():
    """invalidate() 後にテンプレート更新が反映されること。"""
    mock_pm = MagicMock()
    v1 = MagicMock()
    v1.render.return_value = "version 1"
    v2 = MagicMock()
    v2.render.return_value = "version 2"
    mock_pm.get_template.side_effect = [v1, v2]

    registry = PromptRegistry(mock_pm)

    # 初回取得は v1
    assert registry.get("tpl") == "version 1"
    assert mock_pm.get_template.call_count == 1

    # キャッシュにより再取得でも v1 のまま
    assert registry.get("tpl") == "version 1"
    assert mock_pm.get_template.call_count == 1

    # invalidate 後は最新 (v2) が取得される
    registry.invalidate("tpl")
    assert registry.get("tpl") == "version 2"
    assert mock_pm.get_template.call_count == 2
