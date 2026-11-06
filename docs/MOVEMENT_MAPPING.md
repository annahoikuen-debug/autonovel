# 移動マッピング表 (MOVEMENT_MAPPING.md)

> **目的**: 案B の全36ステップで「どこからどこへ移動するか」を記録し、
> 迷子を防止する。各ステップ完了後にこの表を更新する。

---

## Phase 0: 基盤準備 (Steps 1-6)

| Step | 内容 | ステータス |
|------|------|-----------|
| 1 | import 依存グラフ生成スクリプト作成 | ✅ 完了 |
| 2 | シムテンプレート文書作成 | ✅ 完了 |
| 3 | リグレッションテスト基盤作成 | ✅ 完了 |
| 4 | lint ratchet ベースライン手順文書化 | ✅ 完了 |
| 5 | CIガードライン追加（shim_registry.json） | ✅ 完了 |
| 6 | 移動マッピング表作成（本ファイル） | ✅ 完了 |

---

## Phase 1: LLM 統合 (Steps 7-14)

統合先: `src/llm/`

| Step | 移動元 | 移動先 | シム残し場所 | ステータス |
|------|--------|--------|-------------|-----------|
| 7 | LLM 統合計画文書作成 | `docs/LLM_UNIFICATION_PLAN.md` | — | 未着手 |
| 8 | `src/core/llm_clients/{base,gemini,openai}.py` | `src/llm/clients/{base,gemini,openai}.py` | `src/core/llm_clients/__init__.py` | 未着手 |
| 9 | `src/core/llm/adapters/{claude,gemini,mock,ollama,openai}_unified_client.py` | `src/llm/unified/adapters/{claude,gemini,mock,ollama,openai}.py` | `src/core/llm/adapters/__init__.py` | 未着手 |
| 10 | `src/services/llm/{base,factory,gemini,mock,openai,ollama,claude,vllm,tracked,failover,retry,prompts,prompt_cache}.py` | `src/llm/adapters/{base,factory,gemini,mock,openai,ollama,claude,vllm,tracked,failover,retry,prompts,prompt_cache}.py` | `src/services/llm/__init__.py` | 未着手 |
| 11 | `src/core/llm/{unified_interface,types,factory}.py` | `src/llm/unified/{interface,types,factory}.py` | `src/core/llm/__init__.py` (_LAZY_EXPORTS パス更新) | 未着手 |
| 12 | `src/services/llm/circuit_breaker.py` | 移動なし（既に `src/llm/circuit_breaker.py` への shim） | `src/services/llm/circuit_breaker.py` | 未着手 |
| 13 | LLM 関連テストの再配置 | `tests/unit/llm/{clients,adapters}/` | — | 未着手 |
| 14 | LLM 統合の総合リグレッションテスト | `tests/regression/test_llm_unification_complete.py` | — | 未着手 |

---

## Phase 2: API 統合 (Steps 15-20)

統合先: `src/backend/routers/`

| Step | 移動元 | 移動先 | シム残し場所 | ステータス |
|------|--------|--------|-------------|-----------|
| 15 | `src/api/{dashboard,conflicts,agent_memory}.py` | `src/backend/routers/{dashboard,conflicts,agent_memory}.py` | `src/api/{dashboard,conflicts,agent_memory}.py` | 未着手 |
| 16 | `src/backend/api/admin_phase2.py` | `src/backend/routers/admin_phase2.py` | `src/backend/api/admin_phase2.py` | 未着手 |
| 17 | `src/interfaces/api/styles.py`, `platform_export.py` | 移動不要（正しいレイヤー） | — | 未着手（判断のみ） |
| 18 | `src/infrastructure/api/api_client.py` | `src/infrastructure/external/api_client.py` | `src/infrastructure/api/__init__.py` | 未着手 |
| 19 | API 関連テストの再配置 | `tests/api/` | — | 未着手 |
| 20 | API 統合の総合リグレッションテスト | `tests/regression/test_api_unification_complete.py` | — | 未着手 |

---

## Phase 3: config 統合 (Steps 21-27)

統合先: `src/` 配下（YAML は `config/` に純化）

| Step | 移動元 | 移動先 | シム残し場所 | ステータス |
|------|--------|--------|-------------|-----------|
| 21 | `config/container.py` | `src/core/container/`（既に移設済み） | `config/container.py`（shim 維持） | 未着手 |
| 22 | `config/settings.py` | `src/infrastructure/config/settings.py` | `config/settings.py` | 未着手 |
| 23 | `config/` の残り Python コードの棚卸し | `docs/CONFIG_UNIFICATION_PLAN.md` | — | 未着手 |
| 24 | `config/` の実体 Python → `src/config/`（第1バッチ） | `src/config/` | 各 `config/X.py` | 未着手 |
| 25 | `config/` の実体 Python → `src/infrastructure/config/`（第2バッチ） | `src/infrastructure/config/` | 各 `config/X.py` | 未着手 |
| 26 | `config/` の残り Python → `src/domain/`, `src/interfaces/`（第3バッチ） | `src/domain/`, `src/interfaces/` | 各 `config/X.py` | 未着手 |
| 27 | config 統合の総合リグレッションテスト | `tests/regression/test_config_unification_complete.py` | — | 未着手 |

---

## Phase 4: スキーマ統合 (Steps 28-32)

| Step | 移動元 | 移動先 | シム残し場所 | ステータス |
|------|--------|--------|-------------|-----------|
| 28 | `src/schemas/easy_mode.py` | `src/domain/schemas/easy_mode.py` | `src/schemas/__init__.py` | 未着手 |
| 29 | `src/types/inlineRevision.ts` | `frontend/src/types/inlineRevision.ts` | —（削除） | 未着手 |
| 30 | `src/models/` の分類（DBモデル vs APIスキーマ） | `docs/MODELS_CLASSIFICATION.md` | — | 未着手 |
| 31 | `src/backend/schemas/` の棚卸し | `docs/MODELS_CLASSIFICATION.md` に追記 | — | 未着手 |
| 32 | スキーマ統合の総合リグレッションテスト | `tests/regression/test_schemas_unification_complete.py` | — | 未着手 |

---

## Phase 5: services 分割 (Steps 33-36)

| Step | 移動元 | 移動先 | シム残し場所 | ステータス |
|------|--------|--------|-------------|-----------|
| 33 | `src/services/` の分類と移動計画確定 | `docs/SERVICES_REORGANIZATION_PLAN.md` | — | 未着手 |
| 34 | 生成系サブパッケージ → `src/engine/` | `src/engine/{anti_ai,cadence,...}/` | `src/services/{anti_ai,cadence,...}/__init__.py` | 未着手 |
| 35 | 出版系サブパッケージ → `src/publishing/` | `src/publishing/{ebook,exporters,...}/` | `src/services/{ebook,exporters,...}/__init__.py` | 未着手 |
| 36 | 外部連携系サブパッケージ → `src/integrations/` | `src/integrations/{billing,marketing,...}/` | `src/services/{billing,marketing,...}/__init__.py` | 未着手 |

---

## 完了チェックリスト

全36ステップ完了後、以下を確認:

```bash
# 全テストが通る
.venv/bin/python3 -m pytest tests/ -v --tb=short

# ruff check が通る
.venv/bin/python3 -m ruff check src config tests

# mypy が通る（ベースライン内）
.venv/bin/python3 -m mypy src

# shim import テストが通る
.venv/bin/python3 -m pytest tests/regression/test_shim_imports.py -v

# shim 登録テストが通る
.venv/bin/python3 -m pytest tests/regression/test_new_shims_registered.py -v

# import グラフに新しい循環がない
.venv/bin/python3 scripts/generate_import_graph.py
.venv/bin/python3 -m pytest tests/regression/test_import_graph_baseline.py -v
```

---

## 更新履歴

| 日付 | ステップ | 変更内容 |
|------|----------|----------|
| 2026-11-06 | Steps 1-6 | Phase 0 基盤準備 完了 |
