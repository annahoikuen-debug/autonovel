"""Step 14: LLM 4箇所の統合が完了し、全 import 経路が動作することを確認する。

LLM 関連モジュールが分散していた4箇所（src/llm/, src/core/llm/,
src/core/llm_clients/, src/services/llm/）を src/llm/ に統合し、
旧パスの shim も含めて全経路が正しく動作することを検証する。
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: 全ての LLM 関連 import 経路 (module_path, expected_symbols)
LLM_IMPORT_PATHS = [
    # 新パス（統合後）
    ("src.llm", ["LLMCircuitBreaker", "ResilientLLMGateway", "LLMProvider"]),
    ("src.llm.clients", ["BaseLLMClient", "GeminiApiClient", "OpenAIApiClient"]),
    ("src.llm.unified", ["IUnifiedLLMClient", "LLMRequest", "LLMResponse"]),
    ("src.llm.unified.adapters", ["GeminiUnifiedClient", "OpenAIUnifiedClient"]),
    ("src.llm.adapters", ["BaseLLMAdapter", "get_llm_adapter"]),
    # 旧パス（shim、維持必須）
    ("src.core.llm", ["IUnifiedLLMClient", "LLMCircuitBreaker", "BaseLLMClient"]),
    ("src.core.llm_clients", ["BaseLLMClient", "GeminiApiClient"]),
    ("src.core.llm.adapters", ["GeminiUnifiedClient"]),
    ("src.services.llm", ["BaseLLMAdapter", "get_llm_adapter"]),
    ("src.services.llm.circuit_breaker", ["CircuitBreaker", "LLMCircuitBreaker"]),
    ("src.llm.service", ["LLMService"]),
    ("src.core.llm_gateway", ["LLMProviderFactory"]),
]


@pytest.mark.parametrize("module_path,symbols", LLM_IMPORT_PATHS)
def test_all_llm_import_paths(module_path, symbols):
    """全ての LLM import 経路が動作する。"""
    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        pytest.fail(f"{module_path} の import に失敗: {exc}")
    for symbol in symbols:
        assert hasattr(mod, symbol), \
            f"{module_path} に {symbol} が公開されていない"


def test_no_orphan_llm_files():
    """移動元に不要な実体ファイルが残っていない。
    src/services/llm/ のサブモジュール shim は意図的に維持しているため、
    チェック対象から除外する（shim_registry.json に登録済み）。
    """
    orphan_checks = [
        (ROOT / "src" / "core" / "llm_clients",
         ["base.py", "gemini.py", "openai.py"]),
        (ROOT / "src" / "core" / "llm" / "adapters",
         ["claude_unified_client.py", "gemini_unified_client.py",
          "mock_unified_client.py", "ollama_unified_client.py",
          "openai_unified_client.py"]),
    ]
    for dir_path, removed_files in orphan_checks:
        for fname in removed_files:
            assert not (dir_path / fname).exists(), \
                f"{dir_path / fname} が残っている（削除すべき）"


def test_ruff_clean_llm():
    """src/llm/, src/core/llm/, src/services/llm/ が ruff check を通る。"""
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "src/llm", "src/core/llm", "src/services/llm"],
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
    )
    assert result.returncode == 0, \
        f"ruff check 失敗:\n{result.stdout}\n{result.stderr}"
