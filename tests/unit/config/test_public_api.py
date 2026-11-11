"""config パッケージのパブリック API 契約テスト。

shim 削除等のリファクタ時に config パッケージから消えてはならない
名前を __all__ と照らし合わせて検証する。
"""

import importlib

from config import __all__ as config_all

MODULE = importlib.import_module("config")


def test_config_public_api_names_exist():
    """__all__ に列挙された全ての名前が config パッケージから解決できること。"""
    for name in config_all:
        assert hasattr(MODULE, name), f"config.{name} が見つからない"


def test_config_public_api_names_are_not_none():
    """__all__ に列挙された全ての名前が None で束縛されていないこと。"""
    for name in config_all:
        obj = getattr(MODULE, name)
        assert obj is not None, f"config.{name} が None に束縛されている"


def test_config_keeps_critical_compat_names():
    """shim 削除後も後方互換コードから参照される名前が残っていること。"""
    critical = (
        "constants",
        "project_context",
        "FORBIDDEN_SUMMARY_PATTERNS",
        "FORBIDDEN_WORD_REPLACEMENTS",
    )
    for name in critical:
        assert name in config_all, f"{name} が __all__ から外れている"
        assert hasattr(MODULE, name), f"config.{name} が見つからない"
