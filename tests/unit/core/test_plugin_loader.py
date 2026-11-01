"""src/core/plugin_loader.py の単体テスト。"""

from __future__ import annotations

from src.core.plugin_loader import PluginLoader


def test_plugin_loader_class_exists():
    """PluginLoader クラスが存在すること。"""
    assert PluginLoader is not None


def test_load_all_plugins_is_callable():
    """load_all_plugins が呼び出し可能であること。"""
    assert callable(PluginLoader.load_all_plugins)


def test_load_all_plugins_no_crash_without_plugins_dir():
    """plugins ディレクトリが存在しない場合でも例外にならないこと。

    load_all_plugins は __file__ から相対パスで plugins ディレクトリを
    参照するため、存在しない場合は警告ログのみで早期リターンする。
    このテストでは例外が発生しないことのみを確認する。
    """
    loader = PluginLoader()
    # 例外が発生しないことを確認（plugins/ が無い場合は警告のみでリターン）
    loader.load_all_plugins()
