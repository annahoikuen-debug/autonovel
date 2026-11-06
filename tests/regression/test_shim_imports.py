"""Step 3: 全ての shim モジュールの import が動作することを確認する。

後方互換のため残している shim モジュールが、期待するシンボルを
正しく再エクスポートしていることを機械的に検証する。

各ステップで新しい shim を追加したら、KNOWN_SHIMS に登録すること。
"""

from __future__ import annotations

import importlib

import pytest

#: 各ステップで追加する shim の一覧 (module_path, expected_symbols)
#: 「モジュールパス」と「そのモジュールが公開すべきシンボル名」のペア。
KNOWN_SHIMS = [
    # 案Aで移動した生成物系（shim ではなく .gitkeep のみだが、念のため）
    # 既存の shim（案B 以前から存在するもの）
    ("config.erotic_vocabulary", ["METAPHOR_BANK", "get_vocabulary_for_tier"]),
    ("config.container", ["Container", "get_container"]),
    ("src.api.health", ["router"]),
    ("src.services.llm.circuit_breaker", ["CircuitBreaker", "LLMCircuitBreaker"]),
    ("src.backend.config", ["settings", "Settings", "ROOT_DIR"]),
    # Step 8 で追加予定
    # ("src.core.llm_clients", ["BaseLLMClient", "GeminiApiClient", "OpenAIApiClient"]),
    # Step 9 で追加予定
    # ("src.core.llm.adapters", ["GeminiUnifiedClient"]),
    # Step 10 で追加予定
    # ("src.services.llm", ["BaseLLMAdapter", "get_llm_adapter"]),
    # Step 11 で追加予定
    # ("src.core.llm", ["IUnifiedLLMClient", "LLMCircuitBreaker"]),
    # Step 15 で追加予定
    # ("src.api.dashboard", ["router"]),
    # ("src.api.conflicts", ["router"]),
    # ("src.api.agent_memory", ["router"]),
    # Step 16 で追加予定
    # ("src.backend.api.admin_phase2", ["router", "enrichment_router", "rag_router"]),
]


@pytest.mark.parametrize("module_path,symbols", KNOWN_SHIMS)
def test_shim_importable(module_path, symbols):
    """shim モジュールが import 可能で、期待するシンボルを公開する。"""
    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        pytest.fail(f"{module_path} の import に失敗: {exc}")
    for symbol in symbols:
        assert hasattr(mod, symbol), \
            f"{module_path} に {symbol} が公開されていない"


def test_shim_list_not_empty():
    """KNOWN_SHIMS が空でないこと（登録忘れ防止）。"""
    assert len(KNOWN_SHIMS) > 0
