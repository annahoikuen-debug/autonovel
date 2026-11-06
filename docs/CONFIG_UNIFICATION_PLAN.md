# config 統合計画 (CONFIG_UNIFICATION_PLAN.md)

> **目的**: ルート `config/` に散在する Python 設定コードを `src/` 配下の正規レイヤーに移動し、
> YAML 設定ファイルは `config/` に純化する。
>
> **方針**: 各ファイルを移動後、旧パスに shim を残して後方互換を維持する。

---

## 現状: config/ の Python ファイル (29個)

### shim 類（移動不要、既に shim として機能）

| ファイル | 移設先 | shim_registry 登録 |
|----------|--------|-------------------|
| `config/container.py` | `src/core/container/` | ✅ |
| `config/settings.py` | `src/infrastructure.config.settings` | ✅ (Step 22) |
| `config/erotic_*.py` (8個) | `src/nsfw/` | ✅ (既存) |

### 実体（移動対象、18個）

#### 第1バッチ: `src/config/` へ移動 (Step 24)

| 移動元 | 移動先 | シム |
|--------|--------|------|
| `config/archetypes.py` | `src/config/archetypes.py` | `config/archetypes.py` |
| `config/archetypes_new.py` | `src/config/archetypes_new.py` | `config/archetypes_new.py` |
| `config/constants.py` | `src/config/constants.py` | `config/constants.py` |
| `config/domain_profile_manager.py` | `src/config/domain_profile_manager.py` | `config/domain_profile_manager.py` |
| `config/emotional_hook_vocabulary.py` | `src/config/emotional_hook_vocabulary.py` | `config/emotional_hook_vocabulary.py` |
| `config/image_models.py` | `src/config/image_models.py` | `config/image_models.py` |
| `config/imagen_models.py` | `src/config/imagen_models.py` | `config/imagen_models.py` |
| `config/platform_censorship_rules.py` | `src/config/platform_censorship_rules.py` | `config/platform_censorship_rules.py` |
| `config/sharp_edge_vocabulary.py` | `src/config/sharp_edge_vocabulary.py` | `config/sharp_edge_vocabulary.py` |

#### 第2バッチ: `src/infrastructure/config/` へ移動 (Step 25)

| 移動元 | 移動先 | シム |
|--------|--------|------|
| `config/cors_config.py` | `src/infrastructure/config/cors_config.py` | `config/cors_config.py` |
| `config/file_watcher.py` | `src/infrastructure/config/file_watcher.py` | `config/file_watcher.py` |
| `config/logging_config.py` | `src/infrastructure/config/logging_config.py` | `config/logging_config.py` |
| `config/project_context.py` | `src/infrastructure/config/project_context.py` | `config/project_context.py` |
| `config/validator.py` | `src/infrastructure/config/validator.py` | `config/validator.py` |

#### 第3バッチ: `src/domain/` や `src/interfaces/` へ移動 (Step 26)

| 移動元 | 移動先 | シム |
|--------|--------|------|
| `config/models.py` | `src/domain/models/` または `src/domain/schemas/` | `config/models.py` |
| `config/narrative.py` | `src/domain/narrative.py` | `config/narrative.py` |
| `config/styles.py` | `src/domain/styles.py` | `config/styles.py` |
| `config/streamlit_adapter.py` | `src/interfaces/streamlit_adapter.py` | `config/streamlit_adapter.py` |

---

## shim テンプレート

各移動元には以下の shim を作成する（パターンA: ファイル単位):

```python
"""後方互換 shim: 実体は src/... に移設済み。"""
from __future__ import annotations

from src.<新パス> import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
```

---

## 進捗チェックリスト

| Step | 内容 | ステータス |
|------|------|-----------|
| 21 | `config/container.py` shim 確認・登録 | ✅ 完了 |
| 22 | `config/settings.py` shim 確認・登録 | ✅ 完了 |
| 23 | `config/` の残り Python コードの棚卸し（本ファイル） | ✅ 完了 |
| 24 | 第1バッチ: `config/` → `src/config/`（9ファイル） | 未着手 |
| 25 | 第2バッチ: `config/` → `src/infrastructure/config/`（5ファイル） | 未着手 |
| 26 | 第3バッチ: `config/` → `src/domain/`, `src/interfaces/`（4ファイル） | 未着手 |
| 27 | config 統合の総合リグレッションテスト | 未着手 |
