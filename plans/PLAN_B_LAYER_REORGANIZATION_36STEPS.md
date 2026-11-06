# PLAN_B: レイヤー再編実装計画書 (36 Steps)

> **目的**: `src/` 配下に散在する重複モジュール（LLM 4箇所 / API 4箇所 / config 4箇所 / スキーマ 6箇所）を統合し、`services/` の巨大化を抑制する。
>
> **原則**:
> - 各ステップは単一のファイル移動 + シム作成 + テスト追加で完結する
> - 既存のテストが全緑を維持することを常に確認する
> - 旧パスには shim（再エクスポート）を残し、新規コードだけ新パスを使う
> - 各ステップの完了条件は「関連テストが全て通ること」
>
> **前提**: 案A（ルート整理）完了済み。`var/` 集約、`.bat` 隔離、docs 整理済み。

---

## 全体マップ

```
Phase 1: LLM 統合          (Steps  7-14)
Phase 2: API 統合          (Steps 15-20)
Phase 3: config 統合       (Steps 21-27)
Phase 4: スキーマ統合       (Steps 28-32)
Phase 5: services 分割     (Steps 33-36)
```

---

## Phase 0: 基盤準備 (Steps 1-6)

### Step 1: import 依存グラフのスナップショット生成

**目的**: 移動前に「どのファイルがどのモジュールを import しているか」の完全な記録を作成する。以後の各ステップでこの記録と照合し、import が壊れていないことを機械的に確認する。

**手順**:
1. `scripts/` に `generate_import_graph.py` を作成
2. `src/`, `config/`, `tests/` 以下の全 `.py` を走査し、`from src.xxx import yyy` / `import src.xxx` パターンを抽出
3. `var/import_graph.json` に出力（JSON形式: `{source_file: [imported_modules]}`）
4. `git add scripts/generate_import_graph.py`

**完了条件**:
```bash
python scripts/generate_import_graph.py
# var/import_graph.json が生成される
```

**リグレッションテスト**:
```python
# tests/regression/test_import_graph_baseline.py
"""Step 1: import 依存グラフのベースラインが維持されることを確認する。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def test_import_graph_baseline_exists():
    """ベースラインファイルが存在する"""
    assert (ROOT / "var" / "import_graph.json").exists()

def test_no_new_import_cycles():
    """循環 import が増加していない"""
    graph = json.loads((ROOT / "var" / "import_graph.json").read_text())
    # 循環検出: A→B→A のペアを検出
    cycles = []
    for a, targets in graph.items():
        for b in targets:
            if b in graph and a in graph[b]:
                cycles.append(f"{a} <-> {b}")
    # 既知の循環は許可リストで管理
    KNOWN_CYCLES = set()  # 既知循環をここに追加
    new_cycles = set(cycles) - KNOWN_CYCLES
    assert not new_cycles, f"新しい循環 import: {new_cycles}"
```

---

### Step 2: シムテンプレートの確立

**目的**: 以後の全ステップで使う「旧パス → 新パス」の shim パターンを確定する。既存の `src/backend/config.py` と `config/erotic_*.py` のパターンをフォーマル化する。

**手順**:
1. `docs/` に `SHIM_PATTERN.md` を作成
2. 既存の2つの成功パターンをテンプレートとして記載:

**テンプレートA: ファイル単位の shim（1ファイル → 1ファイル）**
```python
# 旧パス (例: src/services/llm/circuit_breaker.py)
"""後方互換 shim: 実体は src.llm.circuit_breaker に移設済み。"""
from src.llm.circuit_breaker import *  # noqa: F401, F403
from src.llm.circuit_breaker import CircuitState, LLMCircuitBreaker, ProviderHealthState  # noqa: F401

__all__ = ["CircuitState", "LLMCircuitBreaker", "ProviderHealthState"]
```

**テンプレートB: パッケージ単位の shim（ディレクトリ全体を移設）**
```python
# 旧パスの __init__.py (例: src/services/llm/__init__.py)
"""後方互換 shim: 実体は src/llm/adapters/ に移設済み。"""
from src.llm.adapters.base import BaseLLMAdapter  # noqa: F401
from src.llm.adapters.factory import get_llm_adapter  # noqa: F401
from src.llm.adapters.gemini import GeminiAdapter  # noqa: F401
from src.llm.adapters.mock import MockLLMAdapter  # noqa: F401
from src.llm.adapters.openai import OpenAIAdapter  # noqa: F401

__all__ = [
    "BaseLLMAdapter", "GeminiAdapter", "MockLLMAdapter",
    "OpenAIAdapter", "get_llm_adapter",
]
```

**完了条件**:
- `docs/SHIM_PATTERN.md` が作成される
- テンプレートが2つの既存成功例を含む

**リグレッションテスト**:
```python
# tests/regression/test_shim_pattern_compliance.py
"""Step 2: 新規 shim がテンプレートに従っていることを確認する。"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def test_shim_has_deprecation_docstring():
    """全ての shim ファイルに 'shim' または '後方互換' の docstring がある"""
    # 既知の shim ファイル一覧（各ステップで追加）
    KNOWN_SHIMS = [
        "src/backend/config.py",
        "config/container.py",
        "config/erotic_vocabulary.py",
        "src/api/health.py",
        "src/services/llm/circuit_breaker.py",
    ]
    for rel_path in KNOWN_SHIMS:
        path = ROOT / rel_path
        if path.exists():
            content = path.read_text(encoding="utf-8")
            assert "shim" in content.lower() or "後方互換" in content, \
                f"{rel_path} に shim である旨の docstring がない"
```

---

### Step 3: リグレッションテスト基盤の作成

**目的**: 以後の全ステップで「移動後も旧 import が動作すること」を機械的に確認する共通テストスイートを作る。

**手順**:
1. `tests/regression/test_shim_imports.py` を作成
2. 既知の shim パス一覧をマージし、全 shim の import が動作することを確認
3. `tests/regression/test_no_orphan_shims.py` を拡張（既に存在する `test_H1_no_orphan_shims.py` に追記）

**テスト内容**:
```python
# tests/regression/test_shim_imports.py
"""全ての shim モジュールの import が動作することを確認する。"""
import importlib
import pytest

#: 各ステップで追加する shim の一覧 (module_path, expected_symbols)
KNOWN_SHIMS = [
    ("config.erotic_vocabulary", ["METAPHOR_BANK", "get_vocabulary_for_tier"]),
    ("config.container", ["Container", "get_container"]),
    ("src.api.health", ["router"]),
    ("src.services.llm.circuit_breaker", ["CircuitBreaker", "LLMCircuitBreaker"]),
    ("src.backend.config", ["settings", "Settings", "ROOT_DIR"]),
    # 以下は各 Phase で追加される
]

@pytest.mark.parametrize("module_path,symbols", KNOWN_SHIMS)
def test_shim_importable(module_path, symbols):
    """shim モジュールが import 可能で、期待するシンボルを公開する"""
    mod = importlib.import_module(module_path)
    for symbol in symbols:
        assert hasattr(mod, symbol), \
            f"{module_path} に {symbol} が公開されていない"
```

**完了条件**:
```bash
python -m pytest tests/regression/test_shim_imports.py -v
# 全 shim の import が成功する
```

---

### Step 4: lint ratchet ベースラインの更新手順確立

**目的**: 移動に伴い `config/ci_lint_baseline.json` の値が変わる。その更新手順を文書化し、意図的な更新を機械的に追跡可能にする。

**手順**:
1. `docs/LINT_BASELINE_UPDATE.md` を作成
2. 更新手順を記載:
   ```bash
   # 1. 現状を確認
   ruff check src config tests --statistics | head -20
   # 2. 移動後、新しいベースラインを計算
   ruff check src config tests 2>&1 | tail -5
   # 3. config/ci_lint_baseline.json を更新（値は「悪化させない」上限）
   python scripts/ci_lint_ratchet.py --update-baseline
   # 4. テストで確認
   python -m pytest tests/regression/test_lint_budget.py -v
   ```
3. `config/ci_lint_baseline.json` の現在値を記録: `ruff=100, mypy=1122, format=759`

**完了条件**:
- `docs/LINT_BASELINE_UPDATE.md` が作成される

**リグレッションテスト**:
```python
# tests/regression/test_lint_baseline_integrity.py
"""Step 4: lint ベースラインが存在し、ratchet テストが通ることを確認する。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def test_baseline_file_exists():
    assert (ROOT / "config" / "ci_lint_baseline.json").exists()

def test_baseline_values_are_int():
    data = json.loads((ROOT / "config" / "ci_lint_baseline.json").read_text())
    for key in ["ruff", "mypy", "format"]:
        assert key in data, f"ベースラインに {key} がない"
        assert isinstance(data[key], int), f"{key} が整数でない"
```

---

### Step 5: CIガードラインの追加（新規 shim の検知）

**目的**: 新しい shim が作られたら、それが意図的であることを CI で確認する仕組みを作る。

**手順**:
1. `tests/regression/test_new_shims_registered.py` を作成
2. `config/shim_registry.json` を作成（既知の shim 一覧）
3. 新しい shim が `shim_registry.json` に登録されていなければテストが失敗する

**テスト内容**:
```python
# tests/regression/test_new_shims_registered.py
"""Step 5: 新しい shim が shim_registry.json に登録されていることを確認する。"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def test_all_shims_registered():
    """全ての shim ファイルが shim_registry.json に登録されている"""
    registry = json.loads((ROOT / "config" / "shim_registry.json").read_text())
    registered = set(registry.get("shims", []))

    # src/ と config/ 以下の全 .py を走査
    shim_patterns = [
        ROOT / "src",
        ROOT / "config",
    ]
    discovered = set()
    for base in shim_patterns:
        for py_file in base.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            if "後方互換 shim" in content or "Compatibility shim" in content:
                rel = str(py_file.relative_to(ROOT))
                discovered.add(rel)

    unregistered = discovered - registered
    assert not unregistered, \
        f"未登録の shim: {unregistered}\n" \
        f"config/shim_registry.json に追加してください"
```

**完了条件**:
- `config/shim_registry.json` が作成される
- 既知の shim が全て登録される

---

### Step 6: 移動マッピング表の作成

**目的**: 全36ステップで「どこからどこへ移動するか」の一覧表を先に作成し、迷子を防止する。

**手順**:
1. `docs/MOVEMENT_MAPPING.md` を作成
2. 以下を記載:

| Step | 移動元 | 移動先 | シム残し場所 |
|------|--------|--------|-------------|
| 8 | `src/core/llm_clients/` | `src/llm/clients/` | `src/core/llm_clients/` |
| 9 | `src/core/llm/adapters/` | `src/llm/adapters/` | `src/core/llm/adapters/` |
| 10 | `src/services/llm/*.py` | `src/llm/adapters/` | `src/services/llm/` |
| 11 | `src/llm/circuit_breaker.py` | (統合、移動なし) | — |
| 15 | `src/api/{dashboard,conflicts,agent_memory}.py` | `src/backend/routers/` | `src/api/` |
| 16 | `src/backend/api/admin_phase2.py` | `src/backend/routers/` | `src/backend/api/` |
| 21 | `config/container.py` | `src/core/container/` | `config/container.py` |
| 22 | `config/settings.py` | `src/infrastructure/config/` | `config/settings.py` |
| 25 | `config/` の残り Python | `src/config/` | `config/` |
| 28 | `src/schemas/easy_mode.py` | `src/domain/schemas/` | `src/schemas/` |
| 29 | `src/types/inlineRevision.ts` | `frontend/src/types/` | — (TSX なので不要) |
| 33-36 | `src/services/` のサブパッケージ | `src/engine/`, `src/publishing/`, `src/integrations/` | `src/services/` |

**完了条件**:
- `docs/MOVEMENT_MAPPING.md` が作成される
- 全36ステップの対象が記載される

---

## Phase 1: LLM 統合 (Steps 7-14)

### 現状の問題

LLM クライアントが4箇所に分散:

| 場所 | 内容 | 行数 | 依存ファイル数 |
|------|------|------|--------------|
| `src/llm/` | resilient_gateway, circuit_breaker, model_router, base | 1,161 | 13 |
| `src/core/llm/` | unified_interface, factory, types, adapters | 4,453 | 22 |
| `src/core/llm_clients/` | base, gemini, openai (低レベル) | 696 | 3 |
| `src/services/llm/` | adapters, factory, failover, retry, tracked_adapter | 1,431 | 35 |

**既存の成功例**:
- `src/services/llm/circuit_breaker.py` は既に `src/llm/circuit_breaker.py` への shim
- `src/core/llm/__init__.py` は `src/llm/` からの re-export を PEP 562 で遅延実行

---

### Step 7: LLM 統合のターゲット構成を確定

**目的**: 4箇所をどこに統合するかを決定し、依存グラフを分析する。

**決定**: **`src/llm/` を統合先に指定**（既に resilient_gateway, circuit_breaker, model_router がここにあり、`src/core/llm/__init__.py` がここを re-export している）

**移動計画**:

```
src/llm/  ← 統合先
├── __init__.py        (新規作成: 公開API一覧)
├── base.py            (維持)
├── circuit_breaker.py (維持、統合の中心)
├── fallback_policy.py (維持)
├── model_router.py    (維持)
├── resilient_gateway.py (維持)
├── gemini_provider.py (維持)
├── openai_provider.py (維持)
├── clients/           ← src/core/llm_clients/ を移設
│   ├── __init__.py
│   ├── base.py
│   ├── gemini.py
│   └── openai.py
├── unified/           ← src/core/llm/ を移設
│   ├── __init__.py
│   ├── interface.py   (旧 unified_interface.py)
│   ├── factory.py
│   ├── types.py
│   └── adapters/
│       ├── claude.py
│       ├── gemini.py
│       ├── mock.py
│       ├── ollama.py
│       └── openai.py
└── adapters/          ← src/services/llm/ を移設
    ├── __init__.py
    ├── base.py
    ├── factory.py
    ├── gemini.py
    ├── mock.py
    ├── openai.py
    ├── ollama.py
    ├── claude.py
    ├── vllm.py
    ├── tracked.py
    ├── failover.py
    ├── retry.py
    ├── prompts.py
    └── prompt_cache.py
```

**手順**:
1. `docs/LLM_UNIFICATION_PLAN.md` を作成
2. 上記のツリーと移動マッピングを記載
3. 各移動元の import 依存ファイル数を記録

**完了条件**:
- `docs/LLM_UNIFICATION_PLAN.md` が作成される

---

### Step 8: `src/core/llm_clients/` → `src/llm/clients/` への移設

**目的**: 低レベルクライアントを統合先に移動する。

**手順**:
1. `mkdir -p src/llm/clients`
2. `git mv src/core/llm_clients/base.py src/llm/clients/base.py`
3. `git mv src/core/llm_clients/gemini.py src/llm/clients/gemini.py`
4. `git mv src/core/llm_clients/openai.py src/llm/clients/openai.py`
5. `src/llm/clients/__init__.py` を作成（公開シンボルを re-export）
6. `src/core/llm_clients/__init__.py` を shim に置き換え:
   ```python
   """後方互換 shim: 実体は src/llm/clients/ に移設済み。"""
   from src.llm.clients.base import BaseLLMClient  # noqa: F401
   from src.llm.clients.gemini import GeminiApiClient  # noqa: F401
   from src.llm.clients.openai import OpenAIApiClient  # noqa: F401
   
   __all__ = ["BaseLLMClient", "GeminiApiClient", "OpenAIApiClient"]
   ```
7. `src/core/llm_clients/base.py`, `gemini.py`, `openai.py` を削除（shim のみ残す）
8. `config/shim_registry.json` に `src/core/llm_clients/__init__.py` を追加

**完了条件**:
```bash
python -m pytest tests/unit/llm_clients/ -v
# 全テストが通る
python -c "from src.core.llm_clients import BaseLLMClient; print('OK')"
# OK が出る
```

**リグレッションテスト追加**:
```python
# tests/regression/test_llm_clients_shim.py
"""Step 8: src.core.llm_clients の shim が動作することを確認する。"""
import importlib

def test_core_llm_clients_shim():
    mod = importlib.import_module("src.core.llm_clients")
    assert hasattr(mod, "BaseLLMClient")
    assert hasattr(mod, "GeminiApiClient")
    assert hasattr(mod, "OpenAIApiClient")

def test_new_path_importable():
    from src.llm.clients import BaseLLMClient, GeminiApiClient, OpenAIApiClient
    assert BaseLLMClient is not None
```

---

### Step 9: `src/core/llm/adapters/` → `src/llm/unified/adapters/` への移設

**目的**: 統合アダプタを統合先に移動する。

**手順**:
1. `mkdir -p src/llm/unified/adapters`
2. `git mv src/core/llm/adapters/claude_unified_client.py src/llm/unified/adapters/claude.py`
3. `git mv src/core/llm/adapters/gemini_unified_client.py src/llm/unified/adapters/gemini.py`
4. `git mv src/core/llm/adapters/mock_unified_client.py src/llm/unified/adapters/mock.py`
5. `git mv src/core/llm/adapters/ollama_unified_client.py src/llm/unified/adapters/ollama.py`
6. `git mv src/core/llm/adapters/openai_unified_client.py src/llm/unified/adapters/openai.py`
7. `src/llm/unified/adapters/__init__.py` を作成
8. `src/core/llm/adapters/__init__.py` を shim に置き換え:
   ```python
   """後方互換 shim: 実体は src/llm/unified/adapters/ に移設済み。"""
   from src.llm.unified.adapters.claude import ClaudeUnifiedClient  # noqa: F401
   from src.llm.unified.adapters.gemini import GeminiUnifiedClient  # noqa: F401
   from src.llm.unified.adapters.mock import UnifiedMockLLMClient  # noqa: F401
   from src.llm.unified.adapters.ollama import OllamaUnifiedClient  # noqa: F401
   from src.llm.unified.adapters.openai import OpenAIUnifiedClient  # noqa: F401
   
   __all__ = [
       "ClaudeUnifiedClient", "GeminiUnifiedClient",
       "UnifiedMockLLMClient", "OllamaUnifiedClient", "OpenAIUnifiedClient",
   ]
   ```
9. `src/core/llm/adapters/` の元ファイルを削除
10. `src/core/llm/__init__.py` の `_LAZY_EXPORTS` のパスを更新:
    ```python
    # 旧: "GeminiUnifiedClient": ("src.core.llm.adapters.gemini_unified_client", "GeminiUnifiedClient")
    # 新:
    "GeminiUnifiedClient": ("src.llm.unified.adapters.gemini", "GeminiUnifiedClient"),
    ```
11. `config/shim_registry.json` に `src/core/llm/adapters/__init__.py` を追加

**完了条件**:
```bash
python -m pytest tests/unit/test_unified_llm_interface.py tests/unit/test_llm_factory.py -v
# 全テストが通る
python -c "from src.core.llm.adapters import GeminiUnifiedClient; print('OK')"
```

**リグレッションテスト追加**:
```python
# tests/regression/test_llm_unified_adapters_shim.py
"""Step 9: src.core.llm.adapters の shim が動作することを確認する。"""
import importlib

def test_core_llm_adapters_shim():
    mod = importlib.import_module("src.core.llm.adapters")
    for symbol in ["ClaudeUnifiedClient", "GeminiUnifiedClient",
                   "UnifiedMockLLMClient", "OllamaUnifiedClient",
                   "OpenAIUnifiedClient"]:
        assert hasattr(mod, symbol), f"{symbol} が公開されていない"

def test_new_path_importable():
    from src.llm.unified.adapters import GeminiUnifiedClient, OpenAIUnifiedClient
    assert GeminiUnifiedClient is not None
```

---

### Step 10: `src/services/llm/` → `src/llm/adapters/` への移設

**目的**: サービス層のアダプタを統合先に移動する。

**手順**:
1. `mkdir -p src/llm/adapters`
2. 以下を `git mv` で移動:
   ```
   src/services/llm/base.py           → src/llm/adapters/base.py
   src/services/llm/factory.py        → src/llm/adapters/factory.py
   src/services/llm/gemini_adapter.py → src/llm/adapters/gemini.py
   src/services/llm/mock_adapter.py   → src/llm/adapters/mock.py
   src/services/llm/openai_adapter.py → src/llm/adapters/openai.py
   src/services/llm/ollama_adapter.py → src/llm/adapters/ollama.py
   src/services/llm/claude_adapter.py → src/llm/adapters/claude.py
   src/services/llm/vllm_adapter.py   → src/llm/adapters/vllm.py
   src/services/llm/tracked_adapter.py → src/llm/adapters/tracked.py
   src/services/llm/provider_failover.py → src/llm/adapters/failover.py
   src/services/llm/retry.py          → src/llm/adapters/retry.py
   src/services/llm/prompts.py        → src/llm/adapters/prompts.py
   src/services/llm/prompt_cache_builder.py → src/llm/adapters/prompt_cache.py
   ```
3. `src/llm/adapters/__init__.py` を作成（公開シンボルを re-export）
4. `src/services/llm/__init__.py` を shim に置き換え:
   ```python
   """後方互換 shim: 実体は src/llm/adapters/ に移設済み。"""
   from src.llm.adapters.base import BaseLLMAdapter  # noqa: F401
   from src.llm.adapters.factory import get_llm_adapter  # noqa: F401
   from src.llm.adapters.gemini import GeminiAdapter  # noqa: F401
   from src.llm.adapters.mock import MockLLMAdapter  # noqa: F401
   from src.llm.adapters.openai import OpenAIAdapter  # noqa: F401
   
   __all__ = [
       "BaseLLMAdapter", "GeminiAdapter", "MockLLMAdapter",
       "OpenAIAdapter", "get_llm_adapter",
   ]
   ```
5. `src/services/llm/` の元ファイルを削除（`circuit_breaker.py` は既に shim なので維持）
6. `config/shim_registry.json` に `src/services/llm/__init__.py` を追加

**完了条件**:
```bash
python -m pytest tests/unit/services/llm/ tests/unit/test_llm_factory.py -v
# 全テストが通る
python -c "from src.services.llm import get_llm_adapter; print('OK')"
```

**リグレッションテスト追加**:
```python
# tests/regression/test_llm_services_adapters_shim.py
"""Step 10: src.services.llm の shim が動作することを確認する。"""
import importlib

def test_services_llm_shim():
    mod = importlib.import_module("src.services.llm")
    for symbol in ["BaseLLMAdapter", "GeminiAdapter", "MockLLMAdapter",
                   "OpenAIAdapter", "get_llm_adapter"]:
        assert hasattr(mod, symbol), f"{symbol} が公開されていない"

def test_new_path_importable():
    from src.llm.adapters import get_llm_adapter, GeminiAdapter
    assert get_llm_adapter is not None
```

---

### Step 11: `src/core/llm/unified_interface.py` → `src/llm/unified/interface.py` への移設

**目的**: 統合インターフェースを統合先に移動する。

**手順**:
1. `git mv src/core/llm/unified_interface.py src/llm/unified/interface.py`
2. `src/llm/unified/__init__.py` を作成:
   ```python
   """LLM 統合インターフェースパッケージ。"""
   from src.llm.unified.interface import IUnifiedLLMClient  # noqa: F401
   from src.llm.unified.types import LLMRequest, LLMResponse, LLMUsage, StreamChunk  # noqa: F401
   from src.llm.unified.factory import create_unified_llm_client  # noqa: F401
   
   __all__ = [
       "IUnifiedLLMClient", "LLMRequest", "LLMResponse",
       "LLMUsage", "StreamChunk", "create_unified_llm_client",
   ]
   ```
3. `git mv src/core/llm/types.py src/llm/unified/types.py`
4. `git mv src/core/llm/factory.py src/llm/unified/factory.py`
5. `src/core/llm/__init__.py` の `_LAZY_EXPORTS` を更新:
   ```python
   # 旧パス → 新パス
   "IUnifiedLLMClient": ("src.llm.unified.interface", "IUnifiedLLMClient"),
   "LLMRequest": ("src.llm.unified.types", "LLMRequest"),
   "LLMResponse": ("src.llm.unified.types", "LLMResponse"),
   "LLMUsage": ("src.llm.unified.types", "LLMUsage"),
   "StreamChunk": ("src.llm.unified.types", "StreamChunk"),
   "create_unified_llm_client": ("src.llm.unified.factory", "create_unified_llm_client"),
   ```
6. `src/core/llm/__init__.py` の `TYPE_CHECKING` ブロックのパスも更新
7. `config/shim_registry.json` に `src/core/llm/__init__.py` を追加

**完了条件**:
```bash
python -m pytest tests/unit/test_unified_llm_interface.py tests/unit/test_llm_factory.py -v
python -c "from src.core.llm import IUnifiedLLMClient; print('OK')"
```

**リグレッションテスト追加**:
```python
# tests/regression/test_llm_unified_interface_shim.py
"""Step 11: src.core.llm の公開 API が維持されることを確認する。"""
import importlib

def test_core_llm_public_api():
    mod = importlib.import_module("src.core.llm")
    for symbol in ["IUnifiedLLMClient", "LLMRequest", "LLMResponse",
                   "LLMUsage", "StreamChunk", "create_unified_llm_client",
                   "LLMCircuitBreaker", "ResilientLLMGateway",
                   "LLMProvider", "BaseLLMClient",
                   "GeminiApiClient", "OpenAIApiClient"]:
        assert hasattr(mod, symbol), f"{symbol} が公開されていない"

def test_new_unified_path():
    from src.llm.unified import IUnifiedLLMClient, create_unified_llm_client
    assert IUnifiedLLMClient is not None
```

---

### Step 12: `circuit_breaker` の重複解消

**目的**: `src/llm/circuit_breaker.py`（本体）と `src/services/llm/circuit_breaker.py`（既に shim）の関係を整理する。

**現状**: `src/services/llm/circuit_breaker.py` は既に `src/llm/circuit_breaker.py` への shim。追加の移動は不要。

**手順**:
1. `src/services/llm/circuit_breaker.py` の内容を確認（shim であることを再確認）
2. `src/core/llm/__init__.py` の `_LAZY_EXPORTS` に `LLMCircuitBreaker` が `src.llm.circuit_breaker` を指していることを確認
3. `config/shim_registry.json` に `src/services/llm/circuit_breaker.py` を追加（未登記なら）

**完了条件**:
```bash
python -m pytest tests/unit/test_circuit_breaker.py tests/llm/test_circuit_breaker_concurrency.py -v
python -c "from src.services.llm.circuit_breaker import CircuitBreaker; print('OK')"
```

**リグレッションテスト追加**:
```python
# tests/regression/test_circuit_breaker_shim.py
"""Step 12: circuit_breaker の shim が動作することを確認する。"""
import importlib

def test_services_circuit_breaker_shim():
    mod = importlib.import_module("src.services.llm.circuit_breaker")
    for symbol in ["CircuitBreaker", "CircuitBreakerOpenException",
                   "CircuitState", "LLMCircuitBreaker", "ProviderHealthState"]:
        assert hasattr(mod, symbol), f"{symbol} が公開されていない"

def test_core_llm_circuit_breaker():
    mod = importlib.import_module("src.core.llm")
    assert hasattr(mod, "LLMCircuitBreaker")
```

---

### Step 13: LLM 関連テストの再配置

**目的**: LLM テストを新構成に合わせて整理する。

**手順**:
1. 既存テストの配置を確認:
   ```
   tests/unit/llm/                    → 維持（統合後の src/llm/ に対応）
   tests/unit/llm_clients/            → tests/unit/llm/clients/ に移設
   tests/unit/services/llm/           → tests/unit/llm/adapters/ に移設
   tests/unit/core/test_llm_factory.py → tests/unit/llm/test_unified_factory.py に移設
   tests/unit/test_unified_llm_interface.py → tests/unit/llm/ に移設
   tests/unit/test_llm_factory.py     → tests/unit/llm/ に移設
   ```
2. `git mv` で移動
3. `tests/unit/llm/__init__.py` を更新（必要に応じて）
4. `tests/unit/llm/clients/__init__.py` を作成
5. `tests/unit/llm/adapters/__init__.py` を作成

**完了条件**:
```bash
python -m pytest tests/unit/llm/ -v
# 全テストが通る
```

---

### Step 14: LLM 統合の総合リグレッションテスト

**目的**: LLM 統合が完了したことを包括的に確認する。

**テスト内容**:
```python
# tests/regression/test_llm_unification_complete.py
"""Step 14: LLM 4箇所の統合が完了し、全経路が動作することを確認する。"""
import importlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: 全ての LLM 関連 import 経路
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
    ("src.services.llm_service", ["LLMService"]),
    ("src.core.llm_gateway", ["LLMProviderFactory"]),
]

def test_all_llm_import_paths():
    """全ての LLM import 経路が動作する"""
    for module_path, symbols in LLM_IMPORT_PATHS:
        try:
            mod = importlib.import_module(module_path)
        except ImportError as e:
            pytest.fail(f"{module_path} の import に失敗: {e}")
        for symbol in symbols:
            assert hasattr(mod, symbol), \
                f"{module_path} に {symbol} が公開されていない"

def test_no_orphan_llm_files():
    """移動元に不要なファイルが残っていない"""
    # 移動元ディレクトリが shim のみになっていることを確認
    orphan_checks = [
        (ROOT / "src" / "core" / "llm_clients", ["base.py", "gemini.py", "openai.py"]),
        (ROOT / "src" / "core" / "llm" / "adapters",
         ["claude_unified_client.py", "gemini_unified_client.py",
          "mock_unified_client.py", "ollama_unified_client.py",
          "openai_unified_client.py"]),
        (ROOT / "src" / "services" / "llm",
         ["base.py", "factory.py", "gemini_adapter.py", "mock_adapter.py",
          "openai_adapter.py", "ollama_adapter.py", "claude_adapter.py",
          "vllm_adapter.py", "tracked_adapter.py", "provider_failover.py",
          "retry.py", "prompts.py", "prompt_cache_builder.py"]),
    ]
    for dir_path, removed_files in orphan_checks:
        for fname in removed_files:
            assert not (dir_path / fname).exists(), \
                f"{dir_path / fname} が残っている（削除すべき）"

def test_ruff_clean():
    """ruff check が通る"""
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "src/llm", "src/core/llm", "src/services/llm"],
        capture_output=True, text=True, cwd=ROOT
    )
    assert result.returncode == 0, f"ruff check 失敗:\n{result.stdout}\n{result.stderr}"
```

---

## Phase 2: API 統合 (Steps 15-20)

### 現状の問題

API 層が4箇所に分散:

| 場所 | 内容 | ルーター数 |
|------|------|-----------|
| `src/api/` | dashboard, conflicts, agent_memory, health(shim), middleware | 3 + 2 middleware |
| `src/backend/api/` | admin_phase2 | 1 |
| `src/backend/routers/` | 全ルーター本体 | 47 |
| `src/interfaces/api/` | app_factory, metrics, styles, platform_export | 3 + app_factory |

**決定**: **`src/backend/routers/` を統合先に指定**（47本のルーターがここにあり、`wiring.py` がここを配線）

---

### Step 15: `src/api/` のルーター → `src/backend/routers/` への移設

**目的**: 分散したルーターを統合先に移動する。

**手順**:
1. `git mv src/api/dashboard.py src/backend/routers/dashboard.py`
2. `git mv src/api/conflicts.py src/backend/routers/conflicts.py`
3. `git mv src/api/agent_memory.py src/backend/routers/agent_memory.py`
4. `src/api/dashboard.py` を shim に置き換え:
   ```python
   """後方互換 shim: 実体は src/backend/routers/dashboard.py に移設済み。"""
   from src.backend.routers.dashboard import router  # noqa: F401
   
   __all__ = ["router"]
   ```
5. 同様に `src/api/conflicts.py`, `src/api/agent_memory.py` も shim 化
6. `src/backend/wiring.py` に新しいルーターを追加（既存のルーター import に追加）
7. `src/api/health.py` は既に shim なので維持
8. `config/shim_registry.json` に `src/api/dashboard.py`, `src/api/conflicts.py`, `src/api/agent_memory.py` を追加

**完了条件**:
```bash
python -m pytest tests/api/ -v
# 全テストが通る
python -c "from src.api.dashboard import router; print('OK')"
python -c "from src.api.conflicts import router; print('OK')"
python -c "from src.api.agent_memory import router; print('OK')"
```

**リグレッションテスト追加**:
```python
# tests/regression/test_api_routers_shim.py
"""Step 15: src.api の shim が動作することを確認する。"""
import importlib

def test_api_dashboard_shim():
    mod = importlib.import_module("src.api.dashboard")
    assert hasattr(mod, "router")

def test_api_conflicts_shim():
    mod = importlib.import_module("src.api.conflicts")
    assert hasattr(mod, "router")

def test_api_agent_memory_shim():
    mod = importlib.import_module("src.api.agent_memory")
    assert hasattr(mod, "router")

def test_api_health_shim():
    mod = importlib.import_module("src.api.health")
    assert hasattr(mod, "router")
```

---

### Step 16: `src/backend/api/admin_phase2.py` → `src/backend/routers/` への移設

**目的**: admin ルーターを統合先に移動する。

**手順**:
1. `git mv src/backend/api/admin_phase2.py src/backend/routers/admin_phase2.py`
2. `src/backend/api/admin_phase2.py` を shim に置き換え:
   ```python
   """後方互換 shim: 実体は src/backend/routers/admin_phase2.py に移設済み。"""
   from src.backend.routers.admin_phase2 import (  # noqa: F401
       enrichment_router,
       rag_router,
       router,
   )
   
   __all__ = ["enrichment_router", "rag_router", "router"]
   ```
3. `src/backend/wiring.py` の import を更新（`src.backend.api.admin_phase2` → `src.backend.routers.admin_phase2`）
4. `config/shim_registry.json` に `src/backend/api/admin_phase2.py` を追加

**完了条件**:
```bash
python -m pytest tests/api/ -v
python -c "from src.backend.api.admin_phase2 import router; print('OK')"
```

**リグレッションテスト追加**:
```python
# tests/regression/test_admin_phase2_shim.py
"""Step 16: src.backend.api.admin_phase2 の shim が動作することを確認する。"""
import importlib

def test_admin_phase2_shim():
    mod = importlib.import_module("src.backend.api.admin_phase2")
    for symbol in ["enrichment_router", "rag_router", "router"]:
        assert hasattr(mod, symbol), f"{symbol} が公開されていない"
```

---

### Step 17: `src/interfaces/api/styles.py` と `src/interfaces/api/platform_export.py` の位置づけ確認

**目的**: `src/interfaces/api/` のルーターが「正しいレイヤー」かどうかを確認する。

**背景**: F3 アーキテクチャでは `src/interfaces/` が「正規レイヤー」で、`src/backend` や `src/services` から import してはいけない。しかし `styles.py` は `src.application.formatters` と `src.models` を import しており、これは正しい（interfaces → application → domain の依存方向）。

**手順**:
1. `src/interfaces/api/styles.py` の import を確認:
   - `src.application.formatters.cadence_reformatter` ✓ (interfaces → application)
   - `src.application.ports.style_distiller` ✓ (interfaces → application)
   - `src.models.style_profile` ✓ (interfaces → domain)
   - `src.presets.loader` ✓ (interfaces → domain)
2. `src/interfaces/api/platform_export.py` の import を確認
3. これらは「正しいレイヤー」なので移動不要と判断
4. `docs/MOVEMENT_MAPPING.md` に「Step 17: 移動不要（正しいレイヤー）」と追記

**完了条件**:
- `docs/MOVEMENT_MAPPING.md` に判断結果が記載される

**リグレッションテスト追加**:
```python
# tests/regression/test_interfaces_layer_purity.py
"""Step 17: src.interfaces が正しいレイヤー依存をしていることを確認する。"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def test_interfaces_no_backend_import():
    """src/interfaces/ が src.backend/ を import していない"""
    interfaces_dir = ROOT / "src" / "interfaces"
    for py_file in interfaces_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        content = py_file.read_text(encoding="utf-8")
        # src.backend の import を検出（コメントは除外）
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "src.backend" in stripped and "import" in stripped:
                assert False, \
                    f"{py_file.relative_to(ROOT)} が src.backend を import している: {stripped}"

def test_interfaces_no_services_import():
    """src/interfaces/ が src.services/ を import していない"""
    interfaces_dir = ROOT / "src" / "interfaces"
    for py_file in interfaces_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        content = py_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "src.services" in stripped and "import" in stripped:
                assert False, \
                    f"{py_file.relative_to(ROOT)} が src.services を import している: {stripped}"
```

---

### Step 18: `src/infrastructure/api/api_client.py` の命名修正

**目的**: `src/infrastructure/api/` に「APIクライアント」（外部APIへのクライアント）と「APIルーター」（FastAPIルーター）が混在して混乱を招いている。`api_client.py` は「外部APIクライアント」なので、名前を明確にする。

**手順**:
1. `src/infrastructure/api/api_client.py` の内容を確認
2. `src/infrastructure/external/` に移動（外部APIクライアントの正しい場所）:
   ```bash
   git mv src/infrastructure/api/api_client.py src/infrastructure/external/api_client.py
   ```
3. `src/infrastructure/api/__init__.py` を更新（必要なら削除）
4. import を更新（全ファイル）
5. `config/shim_registry.json` に `src/infrastructure/api/__init__.py` を追加（shim がある場合）

**完了条件**:
```bash
python -m pytest tests/infrastructure/ -v
python -c "from src.infrastructure.external.api_client import *; print('OK')"
```

**リグレッションテスト追加**:
```python
# tests/regression/test_infrastructure_api_client_shim.py
"""Step 18: api_client の移設が完了し、旧パスが動作することを確認する。"""
import importlib

def test_old_path_shim():
    """旧パスが shim として動作する"""
    try:
        mod = importlib.import_module("src.infrastructure.api.api_client")
        # shim がある場合
        assert mod is not None
    except ImportError:
        # shim がない場合、新パスが動作することを確認
        mod = importlib.import_module("src.infrastructure.external.api_client")
        assert mod is not None

def test_new_path_importable():
    from src.infrastructure.external.api_client import *  # noqa: F401
```

---

### Step 19: API 関連テストの再配置

**目的**: API テストを新構成に合わせて整理する。

**手順**:
1. 既存テストの配置を確認:
   ```
   tests/api/          → 維持（統合後の src/backend/routers/ に対応）
   tests/unit/api/     → tests/api/unit/ に移設（必要に応じて）
   ```
2. `tests/api/` 内のテストが新しいルーター配置に対応していることを確認
3. `git mv` で移動（必要に応じて）

**完了条件**:
```bash
python -m pytest tests/api/ -v
# 全テストが通る
```

---

### Step 20: API 統合の総合リグレッションテスト

**目的**: API 統合が完了したことを包括的に確認する。

**テスト内容**:
```python
# tests/regression/test_api_unification_complete.py
"""Step 20: API 4箇所の統合が完了し、全経路が動作することを確認する。"""
import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: 全ての API 関連 import 経路
API_IMPORT_PATHS = [
    # 新パス（統合後）
    ("src.backend.routers.dashboard", ["router"]),
    ("src.backend.routers.conflicts", ["router"]),
    ("src.backend.routers.agent_memory", ["router"]),
    ("src.backend.routers.admin_phase2", ["router", "enrichment_router", "rag_router"]),
    # 旧パス（shim、維持必須）
    ("src.api.dashboard", ["router"]),
    ("src.api.conflicts", ["router"]),
    ("src.api.agent_memory", ["router"]),
    ("src.api.health", ["router"]),
    ("src.backend.api.admin_phase2", ["router"]),
    # 正しいレイヤー（移動不要）
    ("src.interfaces.api.app_factory", ["create_app", "build_lifespan"]),
    ("src.interfaces.api.styles", ["router"]),
    ("src.interfaces.api.platform_export", ["router"]),
    ("src.interfaces.api.metrics", ["router"]),
]

def test_all_api_import_paths():
    """全ての API import 経路が動作する"""
    for module_path, symbols in API_IMPORT_PATHS:
        try:
            mod = importlib.import_module(module_path)
        except ImportError as e:
            pytest.fail(f"{module_path} の import に失敗: {e}")
        for symbol in symbols:
            assert hasattr(mod, symbol), \
                f"{module_path} に {symbol} が公開されていない"

def test_no_orphan_api_files():
    """移動元に不要なファイルが残っていない"""
    orphan_checks = [
        (ROOT / "src" / "api", ["dashboard.py", "conflicts.py", "agent_memory.py"]),
        (ROOT / "src" / "backend" / "api", ["admin_phase2.py"]),
    ]
    for dir_path, removed_files in orphan_checks:
        for fname in removed_files:
            # shim として残っていることを確認（実体ファイルが残っていない）
            path = dir_path / fname
            if path.exists():
                content = path.read_text(encoding="utf-8")
                assert "shim" in content.lower() or "後方互換" in content, \
                    f"{path} が shim ではなく実体ファイルとして残っている"
```

---

## Phase 3: config 統合 (Steps 21-27)

### 現状の問題

設定が4箇所に分散:

| 場所 | 内容 | ファイル数 |
|------|------|-----------|
| ルート `config/` | YAML + Python (erotic shims, container, settings 等) | 72 (29 .py) |
| `src/config/` | Python モジュール | 14 |
| `src/infrastructure/config/` | settings.py (Pydantic BaseSettings) | 1 |
| `src/backend/config.py` | shim → infrastructure/config | 1 |

**既存の成功例**:
- `config/container.py` は既に `src/core/container/` への deprecated wrapper
- `config/erotic_*.py` は既に `src/nsfw/` への shim
- `src/backend/config.py` は既に `src/infrastructure/config/settings.py` への shim

---

### Step 21: `config/container.py` → `src/core/container/` への完全移設

**目的**: `config/container.py` の deprecated wrapper を完全に移設する。

**手順**:
1. `config/container.py` の内容を確認（既に `src.core.container.AppContainer` を re-export）
2. `config/container.py` を shim に維持（既に shim なので追加作業なし）
3. `config/shim_registry.json` に `config/container.py` を追加（未登記なら）

**完了条件**:
```bash
python -m pytest tests/config/test_dependency_consistency.py -v
python -c "from config.container import Container; print('OK')"
```

**リグレッションテスト追加**:
```python
# tests/regression/test_config_container_shim.py
"""Step 21: config.container の shim が動作することを確認する。"""
import importlib

def test_config_container_shim():
    mod = importlib.import_module("config.container")
    assert hasattr(mod, "Container")
    assert hasattr(mod, "get_container")
```

---

### Step 22: `config/settings.py` → `src/infrastructure/config/` への統合

**目的**: ルート `config/settings.py` を統合先に移動する。

**手順**:
1. `config/settings.py` の内容を確認（Pydantic BaseSettings の実体か shim か）
2. 実体の場合:
   ```bash
   git mv config/settings.py src/infrastructure/config/settings_legacy.py
   ```
3. `config/settings.py` を shim に置き換え:
   ```python
   """後方互換 shim: 実体は src/infrastructure/config/settings.py に統合済み。"""
   from src.infrastructure.config.settings import *  # noqa: F401, F403
   from src.infrastructure.config.settings import (  # noqa: F401
       ROOT_DIR, STORAGE_DIR, Settings, settings,
   )
   
   __all__ = ["ROOT_DIR", "STORAGE_DIR", "Settings", "settings"]
   ```
4. `config/shim_registry.json` に `config/settings.py` を追加

**完了条件**:
```bash
python -m pytest tests/config/ -v
python -c "from config.settings import settings; print('OK')"
```

**リグレッションテスト追加**:
```python
# tests/regression/test_config_settings_shim.py
"""Step 22: config.settings の shim が動作することを確認する。"""
import importlib

def test_config_settings_shim():
    mod = importlib.import_module("config.settings")
    for symbol in ["ROOT_DIR", "STORAGE_DIR", "Settings", "settings"]:
        assert hasattr(mod, symbol), f"{symbol} が公開されていない"
```

---

### Step 23: `config/` 内の残り Python コードの棚卸し

**目的**: ルート `config/` に残っている 29 個の Python ファイルを分類し、移動対象を確定する。

**手順**:
1. `config/` の全 `.py` を確認:
   ```
   shim 類（移動不要）:
   - config/container.py          → src/core/container/ への shim
   - config/erotic_*.py (7個)     → src/nsfw/ への shim
   
   実体（移動対象）:
   - config/settings.py           → src/infrastructure/config/ への shim
   - config/archetypes.py         → src/config/ へ
   - config/archetypes_new.py     → src/config/ へ
   - config/constants.py          → src/config/ へ
   - config/cors_config.py        → src/infrastructure/config/ へ
   - config/domain_profile_manager.py → src/config/ へ
   - config/emotional_hook_vocabulary.py → src/config/ へ
   - config/file_watcher.py       → src/infrastructure/config/ へ
   - config/image_models.py       → src/config/ へ
   - config/imagen_models.py      → src/config/ へ
   - config/logging_config.py     → src/infrastructure/config/ へ
   - config/models.py             → src/domain/ へ
   - config/narrative.py          → src/domain/ へ
   - config/platform_censorship_rules.py → src/config/ へ
   - config/project_context.py    → src/infrastructure/config/ へ
   - config/sharp_edge_vocabulary.py → src/config/ へ
   - config/streamlit_adapter.py  → src/interfaces/ へ
   - config/styles.py             → src/domain/ へ
   - config/validator.py          → src/infrastructure/config/ へ
   ```
2. `docs/CONFIG_UNIFICATION_PLAN.md` を作成
3. 上記の分類を記載

**完了条件**:
- `docs/CONFIG_UNIFICATION_PLAN.md` が作成される

---

### Step 24: `config/` の実体 Python → `src/config/` への移設（第1バッチ）

**目的**: `config/` の Python コードのうち、`src/config/` へ移動できるものから移動する。

**対象**（`src/config/` へ移動）:
- `config/archetypes.py`
- `config/archetypes_new.py`
- `config/constants.py`
- `config/domain_profile_manager.py`
- `config/emotional_hook_vocabulary.py`
- `config/image_models.py`
- `config/imagen_models.py`
- `config/platform_censorship_rules.py`
- `config/sharp_edge_vocabulary.py`

**手順**:
1. 各ファイルを `git mv config/X.py src/config/X.py`
2. 各ファイルの旧パスに shim を作成:
   ```python
   # config/archetypes.py
   """後方互換 shim: 実体は src/config/archetypes.py に移設済み。"""
   from src.config.archetypes import *  # noqa: F401, F403
   ```
3. `config/shim_registry.json` に追加

**完了条件**:
```bash
python -m pytest tests/config/ tests/unit/config/ -v
python -c "from config.archetypes import *; print('OK')"
python -c "from config.constants import *; print('OK')"
```

**リグレッションテスト追加**:
```python
# tests/regression/test_config_python_shims.py
"""Step 24: config/ の Python shim が動作することを確認する。"""
import importlib

CONFIG_SHIMS = [
    "config.archetypes",
    "config.archetypes_new",
    "config.constants",
    "config.domain_profile_manager",
    "config.emotional_hook_vocabulary",
    "config.image_models",
    "config.imagen_models",
    "config.platform_censorship_rules",
    "config.sharp_edge_vocabulary",
]

@pytest.mark.parametrize("module_path", CONFIG_SHIMS)
def test_config_python_shim(module_path):
    mod = importlib.import_module(module_path)
    assert mod is not None
```

---

### Step 25: `config/` の実体 Python → `src/infrastructure/config/` への移設（第2バッチ）

**目的**: `config/` の Python コードのうち、`src/infrastructure/config/` へ移動できるものから移動する。

**対象**（`src/infrastructure/config/` へ移動）:
- `config/cors_config.py`
- `config/file_watcher.py`
- `config/logging_config.py`
- `config/project_context.py`
- `config/validator.py`

**手順**:
1. 各ファイルを `git mv config/X.py src/infrastructure/config/X.py`
2. 各ファイルの旧パスに shim を作成
3. `config/shim_registry.json` に追加

**完了条件**:
```bash
python -m pytest tests/config/ tests/unit/backend/test_config_production_validation.py -v
python -c "from config.cors_config import *; print('OK')"
python -c "from config.file_watcher import *; print('OK')"
```

**リグレッションテスト追加**:
```python
# tests/regression/test_config_infrastructure_shims.py
"""Step 25: config/ の infrastructure shim が動作することを確認する。"""
import importlib

INFRA_SHIMS = [
    "config.cors_config",
    "config.file_watcher",
    "config.logging_config",
    "config.project_context",
    "config.validator",
]

@pytest.mark.parametrize("module_path", INFRA_SHIMS)
def test_config_infrastructure_shim(module_path):
    mod = importlib.import_module(module_path)
    assert mod is not None
```

---

### Step 26: `config/` の残り Python → `src/domain/` と `src/interfaces/` への移設（第3バッチ）

**目的**: `config/` の Python コードのうち、`src/domain/` と `src/interfaces/` へ移動できるものから移動する。

**対象**:
- `config/models.py` → `src/domain/` へ
- `config/narrative.py` → `src/domain/` へ
- `config/styles.py` → `src/domain/` へ
- `config/streamlit_adapter.py` → `src/interfaces/` へ

**手順**:
1. 各ファイルを `git mv config/X.py src/domain/X.py`（または `src/interfaces/X.py`）
2. 各ファイルの旧パスに shim を作成
3. `config/shim_registry.json` に追加

**完了条件**:
```bash
python -m pytest tests/ -v -k "config or domain or narrative or styles"
python -c "from config.models import *; print('OK')"
python -c "from config.narrative import *; print('OK')"
python -c "from config.styles import *; print('OK')"
```

**リグレッションテスト追加**:
```python
# tests/regression/test_config_domain_shims.py
"""Step 26: config/ の domain shim が動作することを確認する。"""
import importlib

DOMAIN_SHIMS = [
    "config.models",
    "config.narrative",
    "config.styles",
    "config.streamlit_adapter",
]

@pytest.mark.parametrize("module_path", DOMAIN_SHIMS)
def test_config_domain_shim(module_path):
    mod = importlib.import_module(module_path)
    assert mod is not None
```

---

### Step 27: config 統合の総合リグレッションテスト

**目的**: config 統合が完了したことを包括的に確認する。

**テスト内容**:
```python
# tests/regression/test_config_unification_complete.py
"""Step 27: config 4箇所の統合が完了し、全経路が動作することを確認する。"""
import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: 全ての config 関連 import 経路
CONFIG_IMPORT_PATHS = [
    # 新パス（統合後）
    ("src.config.archetypes", []),
    ("src.config.constants", []),
    ("src.infrastructure.config.settings", ["settings", "Settings", "ROOT_DIR"]),
    # 旧パス（shim、維持必須）
    ("config.settings", ["settings", "Settings", "ROOT_DIR"]),
    ("config.container", ["Container", "get_container"]),
    ("config.archetypes", []),
    ("config.constants", []),
    ("config.cors_config", []),
    ("config.file_watcher", []),
    ("config.logging_config", []),
    ("config.project_context", []),
    ("config.validator", []),
    ("config.models", []),
    ("config.narrative", []),
    ("config.styles", []),
    ("config.streamlit_adapter", []),
    # erotic shims（既存、維持必須）
    ("config.erotic_vocabulary", ["METAPHOR_BANK"]),
    ("config.erotic_pacing", []),
    ("config.erotic_parameters", []),
    ("config.erotic_platform_presets", []),
    ("config.erotic_thresholds", []),
    ("config.erotic_video_patterns", []),
    ("config.erotic_vocabulary_ext", []),
    ("config.erotic_direct_mappings", []),
]

def test_all_config_import_paths():
    """全ての config import 経路が動作する"""
    for module_path, symbols in CONFIG_IMPORT_PATHS:
        try:
            mod = importlib.import_module(module_path)
        except ImportError as e:
            pytest.fail(f"{module_path} の import に失敗: {e}")
        for symbol in symbols:
            assert hasattr(mod, symbol), \
                f"{module_path} に {symbol} が公開されていない"

def test_config_yaml_intact():
    """config/ の YAML ファイルが無傷である"""
    config_dir = ROOT / "config"
    yaml_files = list(config_dir.glob("*.yaml")) + list(config_dir.glob("*.yml"))
    assert len(yaml_files) > 50, f"config/ の YAML ファイルが少なすぎ: {len(yaml_files)}"
```

---

## Phase 4: スキーマ統合 (Steps 28-32)

### 現状の問題

モデル/スキーマが6箇所に分散:

| 場所 | 内容 | ファイル数 |
|------|------|-----------|
| `src/models/` | DB モデル + API スキーマ | 48 |
| `src/domain/models/` | ドメインモデル | 7 |
| `src/domain/schemas/` | ドメインスキーマ | ? |
| `src/schemas/` | easy_mode のみ | 1 |
| ルート `schemas/` | 配布用スキーマ | ? |
| `src/types/` | **inlineRevision.ts (TSX混入!)** | 1 |
| `src/backend/schemas/` | バックエンドスキーマ | ? |

---

### Step 28: `src/schemas/easy_mode.py` → `src/domain/schemas/` への移設

**目的**: easy_mode スキーマをドメイン層に移動する。

**手順**:
1. `src/domain/schemas/` の内容を確認（既に存在するか）
2. `git mv src/schemas/easy_mode.py src/domain/schemas/easy_mode.py`
3. `src/schemas/__init__.py` を shim に置き換え:
   ```python
   """後方互換 shim: 実体は src/domain/schemas/easy_mode.py に移設済み。"""
   from src.domain.schemas.easy_mode import *  # noqa: F401, F403
   ```
4. `config/shim_registry.json` に `src/schemas/__init__.py` を追加

**完了条件**:
```bash
python -m pytest tests/ -v -k "easy_mode"
python -c "from src.schemas.easy_mode import *; print('OK')"
```

**リグレッションテスト追加**:
```python
# tests/regression/test_schemas_easy_mode_shim.py
"""Step 28: src.schemas の shim が動作することを確認する。"""
import importlib

def test_schemas_easy_mode_shim():
    mod = importlib.import_module("src.schemas.easy_mode")
    assert mod is not None

def test_domain_schemas_importable():
    from src.domain.schemas.easy_mode import *  # noqa: F401
```

---

### Step 29: `src/types/inlineRevision.ts` → `frontend/src/types/` への移設

**目的**: Python の `src/` に TypeScript ファイルが混入しているのを解消する。

**手順**:
1. `src/types/inlineRevision.ts` の内容を確認
2. `git mv src/types/inlineRevision.ts frontend/src/types/inlineRevision.ts`
3. `src/types/` ディレクトリを削除（空になる）
4. `frontend/src/types/` の既存ファイルと衝突しないことを確認

**完了条件**:
```bash
# src/types/ が存在しない
test ! -d src/types && echo "OK"
# frontend/src/types/inlineRevision.ts が存在する
test -f frontend/src/types/inlineRevision.ts && echo "OK"
```

**リグレッションテスト追加**:
```python
# tests/regression/test_no_ts_in_python_src.py
"""Step 29: Python の src/ に TypeScript ファイルが混入していないことを確認する。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def test_no_ts_in_src():
    """src/ 以下に .ts / .tsx ファイルが存在しない"""
    src_dir = ROOT / "src"
    ts_files = list(src_dir.rglob("*.ts")) + list(src_dir.rglob("*.tsx"))
    ts_files = [f for f in ts_files if "__pycache__" not in str(f)]
    assert not ts_files, f"src/ に TypeScript ファイルが混入: {ts_files}"
```

---

### Step 30: `src/models/` の分類（DBモデル vs APIスキーマ）

**目的**: `src/models/` の 48 ファイルを「DBモデル」と「APIスキーマ」に分類する。

**手順**:
1. `src/models/` の全 `.py` を確認
2. `docs/MODELS_CLASSIFICATION.md` を作成
3. 分類結果を記載:
   ```
   DB モデル（SQLAlchemy）:
   - src/models/db.py
   - src/models/character.py
   - src/models/bible.py
   - src/models/book.py
   - src/models/chapter.py
   - src/models/branch.py
   - src/models/plot.py
   - src/models/prompt_version.py
   
   API スキーマ（Pydantic）:
   - src/models/api_schemas.py
   - src/models/audit.py
   - src/models/beat_sheet.py
   - src/models/billing.py
   - src/models/context.py
   - src/models/editor.py
   - src/models/emotional_hook.py
   - src/models/foreshadowing.py
   - src/models/generation_progress.py
   - src/models/graph_schemas.py
   - src/models/style_profile.py
   ... (残り)
   ```
4. 分類結果を `docs/MODELS_CLASSIFICATION.md` に記載

**完了条件**:
- `docs/MODELS_CLASSIFICATION.md` が作成される

---

### Step 31: `src/backend/schemas/` の棚卸し

**目的**: `src/backend/schemas/` の内容を確認し、統合対象を確定する。

**手順**:
1. `src/backend/schemas/` の内容を確認
2. `src/models/` と重複していないか確認
3. 重複があれば統合計画を `docs/MODELS_CLASSIFICATION.md` に追記

**完了条件**:
- `docs/MODELS_CLASSIFICATION.md` に `src/backend/schemas/` の分類が追記される

---

### Step 32: スキーマ統合の総合リグレッションテスト

**目的**: スキーマ統合が完了したことを包括的に確認する。

**テスト内容**:
```python
# tests/regression/test_schemas_unification_complete.py
"""Step 32: スキーマ 6箇所の統合が完了し、全経路が動作することを確認する。"""
import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def test_no_ts_in_src():
    """src/ に TypeScript ファイルが混入していない"""
    src_dir = ROOT / "src"
    ts_files = list(src_dir.rglob("*.ts")) + list(src_dir.rglob("*.tsx"))
    ts_files = [f for f in ts_files if "__pycache__" not in str(f)]
    assert not ts_files, f"src/ に TypeScript ファイルが混入: {ts_files}"

def test_schemas_shim():
    """src.schemas の shim が動作する"""
    mod = importlib.import_module("src.schemas")
    assert mod is not None

def test_domain_schemas_importable():
    """src.domain.schemas が import 可能"""
    from src.domain.schemas import *  # noqa: F401

def test_models_importable():
    """src.models が import 可能"""
    from src.models import *  # noqa: F401
```

---

## Phase 5: services 分割 (Steps 33-36)

### 現状の問題

`src/services/` が **43,000行・279ファイル・40+サブパッケージ** の「何でも屋」:

```
生成系（エンジン）:
- anti_ai, cadence, character, compression, context_compression
- foreshadowing, narrative, nlp, prose, graph
- auditors, audit

出版/配信系:
- ebook, exporters, formatters, publishers, publishing
- illustration, manga

外部連携系:
- billing, marketing, cost_guard, observability, prefetch
- rag, vector_store, audio
- llm (統合後は shim のみ)
```

---

### Step 33: `src/services/` の分類と移動計画の確定

**目的**: `src/services/` の全サブパッケージを3つのカテゴリに分類し、移動計画を確定する。

**手順**:
1. `src/services/` の全サブパッケージを確認
2. `docs/SERVICES_REORGANIZATION_PLAN.md` を作成
3. 分類結果を記載:

| カテゴリ | 移動先 | サブパッケージ |
|----------|--------|---------------|
| 生成系 | `src/engine/` | anti_ai, cadence, character, compression, context_compression, foreshadowing, narrative, nlp, prose, graph, auditors, audit |
| 出版系 | `src/publishing/` | ebook, exporters, formatters, publishers, publishing, illustration, manga |
| 外部連携系 | `src/integrations/` | billing, marketing, cost_guard, observability, prefetch, rag, vector_store, audio |
| shim のみ | `src/services/` に維持 | llm (統合済み) |

4. 各サブパッケージの import 依存を記録

**完了条件**:
- `docs/SERVICES_REORGANIZATION_PLAN.md` が作成される

---

### Step 34: 生成系サブパッケージ → `src/engine/` への移設

**目的**: 生成系サブパッケージを `src/engine/` へ移動する。

**対象**:
```
src/services/anti_ai/          → src/engine/anti_ai/
src/services/cadence/          → src/engine/cadence/
src/services/character/        → src/engine/character/
src/services/compression/      → src/engine/compression/
src/services/context_compression/ → src/engine/context_compression/
src/services/foreshadowing/    → src/engine/foreshadowing/
src/services/narrative/        → src/engine/narrative/
src/services/nlp/              → src/engine/nlp/
src/services/prose/            → src/engine/prose/
src/services/graph/            → src/engine/graph/
src/services/auditors/         → src/engine/auditors/
src/services/audit/            → src/engine/audit/
```

**手順**:
1. `mkdir -p src/engine`
2. 各サブパッケージを `git mv` で移動
3. 各移動元に shim を作成（`src/services/anti_ai/__init__.py` 等）
4. `src/services/__init__.py` を更新（再エクスポート）
5. `config/shim_registry.json` に追加

**完了条件**:
```bash
python -m pytest tests/ -v -k "anti_ai or cadence or character or compression or foreshadowing or narrative or nlp or prose or graph or auditors or audit"
# 全テストが通る
python -c "from src.services.anti_ai import *; print('OK')"
python -c "from src.engine.anti_ai import *; print('OK')"
```

**リグレッションテスト追加**:
```python
# tests/regression/test_engine_shims.py
"""Step 34: 生成系サブパッケージの shim が動作することを確認する。"""
import importlib

ENGINE_SHIMS = [
    "src.services.anti_ai",
    "src.services.cadence",
    "src.services.character",
    "src.services.compression",
    "src.services.context_compression",
    "src.services.foreshadowing",
    "src.services.narrative",
    "src.services.nlp",
    "src.services.prose",
    "src.services.graph",
    "src.services.auditors",
    "src.services.audit",
]

@pytest.mark.parametrize("module_path", ENGINE_SHIMS)
def test_engine_shim(module_path):
    mod = importlib.import_module(module_path)
    assert mod is not None
```

---

### Step 35: 出版系サブパッケージ → `src/publishing/` への移設

**目的**: 出版系サブパッケージを `src/publishing/` へ移動する。

**対象**:
```
src/services/ebook/       → src/publishing/ebook/
src/services/exporters/   → src/publishing/exporters/
src/services/formatters/  → src/publishing/formatters/
src/services/publishers/  → src/publishing/publishers/
src/services/publishing/  → src/publishing/core/
src/services/illustration/ → src/publishing/illustration/
src/services/manga/       → src/publishing/manga/
```

**手順**:
1. `mkdir -p src/publishing`
2. 各サブパッケージを `git mv` で移動
3. 各移動元に shim を作成
4. `src/services/__init__.py` を更新
5. `config/shim_registry.json` に追加

**完了条件**:
```bash
python -m pytest tests/ -v -k "ebook or exporters or formatters or publishers or publishing or illustration or manga"
# 全テストが通る
python -c "from src.services.ebook import *; print('OK')"
python -c "from src.publishing.ebook import *; print('OK')"
```

**リグレッションテスト追加**:
```python
# tests/regression/test_publishing_shims.py
"""Step 35: 出版系サブパッケージの shim が動作することを確認する。"""
import importlib

PUBLISHING_SHIMS = [
    "src.services.ebook",
    "src.services.exporters",
    "src.services.formatters",
    "src.services.publishers",
    "src.services.publishing",
    "src.services.illustration",
    "src.services.manga",
]

@pytest.mark.parametrize("module_path", PUBLISHING_SHIMS)
def test_publishing_shim(module_path):
    mod = importlib.import_module(module_path)
    assert mod is not None
```

---

### Step 36: 外部連携系サブパッケージ → `src/integrations/` への移設 + 総合リグレッションテスト

**目的**: 外部連携系サブパッケージを `src/integrations/` へ移動し、全36ステップの完了を確認する。

**対象**:
```
src/services/billing/       → src/integrations/billing/
src/services/marketing/     → src/integrations/marketing/
src/services/cost_guard/    → src/integrations/cost_guard/
src/services/observability/ → src/integrations/observability/
src/services/prefetch/      → src/integrations/prefetch/
src/services/rag/           → src/integrations/rag/
src/services/vector_store/  → src/integrations/vector_store/
src/services/audio/         → src/integrations/audio/
```

**手順**:
1. `mkdir -p src/integrations`
2. 各サブパッケージを `git mv` で移動
3. 各移動元に shim を作成
4. `src/services/__init__.py` を更新
5. `config/shim_registry.json` に追加

**完了条件**:
```bash
python -m pytest tests/ -v -k "billing or marketing or cost_guard or observability or prefetch or rag or vector_store or audio"
# 全テストが通る
python -c "from src.services.billing import *; print('OK')"
python -c "from src.integrations.billing import *; print('OK')"
```

**総合リグレッションテスト追加**:
```python
# tests/regression/test_services_reorganization_complete.py
"""Step 36: services 再編が完了し、全経路が動作することを確認する。"""
import importlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: 全ての services 関連 import 経路
SERVICES_IMPORT_PATHS = [
    # 生成系（新パス）
    ("src.engine.anti_ai", []),
    ("src.engine.cadence", []),
    ("src.engine.character", []),
    ("src.engine.compression", []),
    ("src.engine.context_compression", []),
    ("src.engine.foreshadowing", []),
    ("src.engine.narrative", []),
    ("src.engine.nlp", []),
    ("src.engine.prose", []),
    ("src.engine.graph", []),
    ("src.engine.auditors", []),
    ("src.engine.audit", []),
    # 出版系（新パス）
    ("src.publishing.ebook", []),
    ("src.publishing.exporters", []),
    ("src.publishing.formatters", []),
    ("src.publishing.publishers", []),
    ("src.publishing.core", []),
    ("src.publishing.illustration", []),
    ("src.publishing.manga", []),
    # 外部連携系（新パス）
    ("src.integrations.billing", []),
    ("src.integrations.marketing", []),
    ("src.integrations.cost_guard", []),
    ("src.integrations.observability", []),
    ("src.integrations.prefetch", []),
    ("src.integrations.rag", []),
    ("src.integrations.vector_store", []),
    ("src.integrations.audio", []),
    # 旧パス（shim、維持必須）
    ("src.services.anti_ai", []),
    ("src.services.cadence", []),
    ("src.services.character", []),
    ("src.services.compression", []),
    ("src.services.context_compression", []),
    ("src.services.foreshadowing", []),
    ("src.services.narrative", []),
    ("src.services.nlp", []),
    ("src.services.prose", []),
    ("src.services.graph", []),
    ("src.services.auditors", []),
    ("src.services.audit", []),
    ("src.services.ebook", []),
    ("src.services.exporters", []),
    ("src.services.formatters", []),
    ("src.services.publishers", []),
    ("src.services.publishing", []),
    ("src.services.illustration", []),
    ("src.services.manga", []),
    ("src.services.billing", []),
    ("src.services.marketing", []),
    ("src.services.cost_guard", []),
    ("src.services.observability", []),
    ("src.services.prefetch", []),
    ("src.services.rag", []),
    ("src.services.vector_store", []),
    ("src.services.audio", []),
    ("src.services.llm", ["BaseLLMAdapter", "get_llm_adapter"]),
]

def test_all_services_import_paths():
    """全ての services import 経路が動作する"""
    for module_path, symbols in SERVICES_IMPORT_PATHS:
        try:
            mod = importlib.import_module(module_path)
        except ImportError as e:
            pytest.fail(f"{module_path} の import に失敗: {e}")
        for symbol in symbols:
            assert hasattr(mod, symbol), \
                f"{module_path} に {symbol} が公開されていない"

def test_ruff_clean_all():
    """全 src/ が ruff check を通る"""
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "src", "config"],
        capture_output=True, text=True, cwd=ROOT
    )
    assert result.returncode == 0, \
        f"ruff check 失敗:\n{result.stdout}\n{result.stderr}"

def test_no_orphan_services_files():
    """移動元に不要なファイルが残っていない"""
    # 全移動元ディレクトリが shim のみになっていることを確認
    moved_packages = [
        "anti_ai", "cadence", "character", "compression",
        "context_compression", "foreshadowing", "narrative",
        "nlp", "prose", "graph", "auditors", "audit",
        "ebook", "exporters", "formatters", "publishers",
        "publishing", "illustration", "manga",
        "billing", "marketing", "cost_guard", "observability",
        "prefetch", "rag", "vector_store", "audio",
    ]
    services_dir = ROOT / "src" / "services"
    for pkg_name in moved_packages:
        pkg_dir = services_dir / pkg_name
        if pkg_dir.exists():
            # __init__.py が shim であることを確認
            init_file = pkg_dir / "__init__.py"
            if init_file.exists():
                content = init_file.read_text(encoding="utf-8")
                assert "shim" in content.lower() or "後方互換" in content, \
                    f"{init_file} が shim ではなく実体ファイルとして残っている"
```

---

## 完了チェックリスト

全36ステップ完了後、以下を確認:

```bash
# 1. 全テストが通る
python -m pytest tests/ -v --tb=short

# 2. ruff check が通る
ruff check src config tests

# 3. mypy が通る（ベースライン内）
mypy src

# 4. lint ratchet テストが通る
python -m pytest tests/regression/test_lint_budget.py -v

# 5. 全 shim の import が動作する
python -m pytest tests/regression/test_shim_imports.py -v

# 6. shim_registry が最新である
python -m pytest tests/regression/test_new_shims_registered.py -v

# 7. import グラフに新しい循環がない
python -m pytest tests/regression/test_import_graph_baseline.py -v
```

---

## リスクと軽減策

| リスク | 軽減策 |
|--------|--------|
| 移動に伴う import エラー | 各ステップで「関連テストが全緑」を確認してから次へ |
| lint ratchet の悪化 | `config/ci_lint_baseline.json` をステップごとに更新 |
| Dockerfile の COPY パスが壊れる | 各 Phase 完了後に `docker build` を確認 |
| wheel のパッケージングが壊れる | `python -m build` で確認 |
| テストの実行時間が伸びる | 各ステップのテストは関連するもののみ実行 |
| shim の削除漏れ | `test_new_shims_registered.py` で機械的に検出 |

---

## 参考資料

- `docs/SHIM_PATTERN.md` — シムテンプレート（Step 2）
- `docs/MOVEMENT_MAPPING.md` — 移動マッピング表（Step 6）
- `docs/LLM_UNIFICATION_PLAN.md` — LLM 統合計画（Step 7）
- `docs/CONFIG_UNIFICATION_PLAN.md` — config 統合計画（Step 23）
- `docs/MODELS_CLASSIFICATION.md` — スキーマ分類（Step 30）
- `docs/SERVICES_REORGANIZATION_PLAN.md` — services 再編計画（Step 33）
- `config/shim_registry.json` — shim 一覧（Step 5）
- `var/import_graph.json` — import 依存グラフ（Step 1）
