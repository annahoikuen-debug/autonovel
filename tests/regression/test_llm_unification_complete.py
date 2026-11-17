"""Step 14: LLM 統合が完了し、全新 import 経路が動作することを確認する。

LLM 関連モジュールは src/llm/ に統合済み。旧パス（src.core.llm / src.core.llm_clients /
src.core.llm.adapters / src.services.llm / src.core.llm_gateway 等）の shim は PLAN_Q3 で
全削除し、shim registry は 0 件に到達済み。本テストは新パスのみを検証する。
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: 新パス（統合後）の import 経路 (module_path, expected_symbols)
LLM_IMPORT_PATHS = [
    ("src.llm", ["LLMCircuitBreaker", "ResilientLLMGateway", "LLMProvider"]),
    ("src.llm.clients", ["BaseLLMClient"]),
    ("src.llm.unified", ["IUnifiedLLMClient", "LLMRequest", "LLMResponse"]),
    ("src.llm.unified.adapters", ["GeminiUnifiedClient", "OpenAIUnifiedClient"]),
    ("src.llm.adapters", ["BaseLLMAdapter", "get_llm_adapter"]),
    ("src.llm.service", ["LLMService"]),
]


@pytest.mark.parametrize("module_path,symbols", LLM_IMPORT_PATHS)
def test_all_llm_import_paths(module_path, symbols):
    """全ての新 LLM import 経路が動作し、期待シンボルを公開する。"""
    mod = importlib.import_module(module_path)  # ImportError はテスト失敗
    for symbol in symbols:
        assert hasattr(mod, symbol), f"{module_path} に {symbol} が公開されていない"


def test_old_llm_shim_paths_removed():
    """旧パス shim は削除済み：clean checkout でモジュール不在（ModuleNotFoundError）であることを確認。"""
    old_paths = [
        "src.core.llm",
        "src.core.llm_clients",
        "src.core.llm.adapters",
        "src.services.llm",
    ]
    for module_path in old_paths:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module_path)


def test_old_llm_circuit_breaker_removed():
    """src.services.llm.circuit_breaker shim は削除済み（ModuleNotFoundError）。"""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("src.services.llm.circuit_breaker")


def test_llm_gateway_compat_alias():
    """src.core.llm_gateway は互換エイリアス（LLMGateway 関数）のみ残存。"""
    mod = importlib.import_module("src.core.llm_gateway")
    assert callable(getattr(mod, "LLMGateway", None)), "LLMGateway が callable ではない"
    assert not hasattr(mod, "LLMProviderFactory"), "LLMProviderFactory は削除済み"


def test_no_orphan_llm_files():
    """移動元に不要な実体ファイルが残っていない。"""
    orphan_checks = [
        (ROOT / "src" / "core" / "llm_clients", ["base.py", "gemini.py", "openai.py"]),
        (
            ROOT / "src" / "core" / "llm" / "adapters",
            [
                "claude_unified_client.py",
                "gemini_unified_client.py",
                "mock_unified_client.py",
                "ollama_unified_client.py",
                "openai_unified_client.py",
            ],
        ),
    ]
    for dir_path, removed_files in orphan_checks:
        for fname in removed_files:
            assert not (dir_path / fname).exists(), f"{dir_path / fname} が残っている（削除すべき）"


def test_ruff_clean_llm():
    """src/llm/ が ruff check を通る。"""
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "src/llm"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    )
    assert result.returncode == 0, f"ruff check 失敗:\n{result.stdout}\n{result.stderr}"
