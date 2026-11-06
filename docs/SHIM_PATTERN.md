# シムテンプレート (SHIM_PATTERN.md)

> **目的**: 後方互換を保ちつつモジュールを移動する際の「旧パス → 新パス」shim の作成パターンを定義する。
>
> **使用タイミング**: `src/` や `config/` 内のファイルを別パスに移動した後、旧 import 経路（`from src.old.path import ...`）を維持する必要がある場合。

---

## パターンA: ファイル単位の shim（1ファイル → 1ファイル）

**適用例**: `src/backend/config.py` → `src/infrastructure/config/settings.py`

```python
# 旧パス: src/backend/config.py
"""後方互換 shim: 設定の実体は ``src.infrastructure.config.settings``。

TRACK / F3 ポート化: 正規レイヤー（infrastructure）へ移設し、旧パス
``src.backend.config`` は再エクスポートとして維持する。
``monkeypatch.setattr(cfg_mod, "ROOT_DIR", ...)`` 等の旧来の使い方を
壊さないよう、属性は本モジュールの名前空間にも再束縛する。
"""

from __future__ import annotations

from src.infrastructure.config.settings import *  # noqa: F403
from src.infrastructure.config.settings import (  # noqa: F401
    ROOT_DIR,
    STORAGE_DIR,
    Settings,
    is_auth_bypass_enabled,
    is_nsfw_enabled,
    settings,
)

__all__ = [
    "ROOT_DIR",
    "STORAGE_DIR",
    "Settings",
    "is_auth_bypass_enabled",
    "is_nsfw_enabled",
    "settings",
]
```

**チェックリスト**:
- [ ] 先頭に `"""後方互換 shim: ...` docstring を記載
- [ ] `from 新パス import *` で全シンボルを再エクスポート
- [ ] 重要なシンボルを明示的に `from 新パス import (...)` で再束縛（`monkeypatch` 対応）
- [ ] `__all__` に全公開シンボルを列挙
- [ ] `config/shim_registry.json` に登録

---

## パターンB: パッケージ単位の shim（ディレクトリ全体を移設）

**適用例**: `src/services/llm/__init__.py` → `src/llm/adapters/`（サブモジュール群）

```python
# 旧パス: src/services/llm/__init__.py
"""LLM サービスパッケージ（後方互換 shim）。

実体は src/llm/adapters/ に移設済み。
"""

from src.llm.adapters.base import BaseLLMAdapter  # noqa: F401
from src.llm.adapters.factory import get_llm_adapter  # noqa: F401
from src.llm.adapters.gemini import GeminiAdapter  # noqa: F401
from src.llm.adapters.mock import MockLLMAdapter  # noqa: F401
from src.llm.adapters.openai import OpenAIAdapter  # noqa: F401

__all__ = [
    "BaseLLMAdapter",
    "GeminiAdapter",
    "MockLLMAdapter",
    "OpenAIAdapter",
    "get_llm_adapter",
]
```

**チェックリスト**:
- [ ] 先頭に `"""...（後方互換 shim）..."""` docstring を記載
- [ ] 必要なシンボルを個別に `from 新パス import ...` で再エクスポート
- [ ] `__all__` に全公開シンボルを列挙
- [ ] `config/shim_registry.json` に登録

---

## パターンC: PEP 562 遅延 import shim（公開 API モジュール）

**適用例**: `src/core/llm/__init__.py`

複数のサブモジュールからシンボルを集約し、初回アクセス時に遅延 import するパターン。

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Any

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "シンボル名": ("モジュールパス", "属性名"),
}

if TYPE_CHECKING:
    # 型チェック用の即時 import
    from 新パス.モジュール import シンボル名  # noqa: F401

def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib
    module_path, attr = target
    value = getattr(importlib.import_module(module_path), attr)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


__all__ = [...]
```

**チェックリスト**:
- [ ] `_LAZY_EXPORTS` に全公開シンボルを登録
- [ ] `TYPE_CHECKING` ブロックに型チェック用 import を記載
- [ ] `__getattr__` で遅延 import を実装
- [ ] `__dir__` で `_LAZY_EXPORTS` のキーを含める
- [ ] `__all__` に全公開シンボルを列挙

---

## 共通ルール

1. **docstring に「後方互換 shim」または「shim」を含める**  
   CI（`test_new_shims_registered.py`）で検出するためのマーカー。

2. **`config/shim_registry.json` に登録する**  
   新しい shim を作ったら必ず登録する。未登録の shim は CI で検出される。

3. **shim は実体ファイルを残さない**  
   移動元の元ファイル（実体）は削除し、shim だけを残す。実体が残っていると「どちらが正しいか」の混乱を招く。

4. **新規コードは常に新パスを import する**  
   shim は「既存コードの互換維持」のためだけに残す。新規作成ファイルから shim への import はしない。
