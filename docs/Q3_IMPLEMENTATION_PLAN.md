# PLAN_Q3 完了報告と後続計画書

作成日: 2026-11-16
対象ブランチ: `fix/q1-red-gate-recovery`
最終コミット: `73b007db`（diff review 不整合修正）

---

## 1. PLAN_Q3 完了サマリ

### 1.1 成果（実測）

| 指標 | 目標 | 実測 | 状態 |
|------|------|------|------|
| shim registry | 0 件 | **0 entries** | ✅ 達成 |
| unit suite | 0 failed | **7755 passed / 0 failed** | ✅ 達成 |
| regression（主要） | 0 failed | **70 passed / 0 failed** | ✅ 達成 |
| ruff | 0 errors | **0 / baseline 0** | ✅ 達成 |
| mypy | burn-down | **500 / baseline 500** | ✅ 緑 |
| format | 0 files | **0 / baseline 0** | ✅ 達成 |
| `make ci-parity` | exit 0 | **ratchet + unit + regression 全緑** | ✅ 達成 |

### 1.2 主要変更ファイル

| カテゴリ | ファイル | 変更内容 |
|----------|----------|----------|
| **本番コード** | `src/agents/specialists/adapter.py` | `create_default_specialists()` 削除、`get_aggregator` は `specialists=[]` |
| **本番コード** | `src/llm/service.py` | `generate_text`/`generate_json` 互換復元（purpose解決、tempマッピング、フォールバック） |
| **本番コード** | `src/core/llm_gateway.py` | `LLMGateway` factory 復元（LLMService 代替） |
| **本番コード** | `src/backend/database/core.py` | shim マーカー除去（実モジュールとして維持） |
| **本番コード** | `src/domain/models/prompt_version.py` | shim マーカー除去 |
| **本番コード** | `src/models/db.py` | shim マーカー除去 |
| **テスト** | `tests/regression/test_llm_unification_complete.py` | 新パスのみ検証、旧 shim 削除確認追加 |
| **テスト** | `tests/regression/test_api_unification_complete.py` | 旧パス shim 除外 |
| **テスト** | `tests/regression/test_v53_long_form_integrity.py` | 正規表現＋アサーション修正 |
| **テスト** | `tests/regression/test_shim_deprecation_warning.py` | 空レジストリ対応（skip 時動的検証スキップ） |
| **テスト** | `tests/regression/test_H1_lint_ratchet.py` | mypy ベースラインで understated 検証に変更 |
| **テスト** | `tests/regression/test_schemas_unification_complete.py` | 削除済み plot.py 参照除外 |
| **テスト** | `tests/regression/test_env_var_hygiene.py` | ALLOWED_FILES に ssrf_guard 追加 |
| **設定** | `config/shim_registry.json` | `[]`（0 entries） |
| **設定** | `config/ci_lint_baseline.json` | mypy 500、履歴整合、日本語可読化 |
| **ドキュメント** | `README.md` | mypy 500、LLM 呼出回数 10 回/未達 |
| **ドキュメント** | `docs/STATUS.md` | mypy 500、§3 PDCA 記載訂正、§4 Q3 完了時点実測 |
| **ドキュメント** | `docs/SHIM_PATTERN.md` | 新規 shim 禁止方針 |
| **ドキュメント** | `docs/MOVEMENT_MAPPING.md` | Q3 完了注記 |
| **ドキュメント** | `CHANGELOG.md` | Q1〜Q3 成果記載 |
| **再生成** | `docs/openapi.json` | app との drift 解消 |

---

## 2. 現状評価

### 2.1 品質ゲート状態

- **CI ラチェット**: ruff/mypy/format 3 ツールすべて green
- **unit suite**: 7755 passed / 0 failed / 36 skipped / 9 xfailed
- **regression（主要）**: shim 関連・API・LLM・スキーマ・監査契約すべて green
- **DeprecationWarning ゲート**: `test_no_deprecation_warnings.py` passing
- **shim registry**: 0 件（Q3 目標達成）

### 2.2 残存リスク

| リスク | 影響 | 対策 |
|--------|------|------|
| `src.core.llm_gateway` の `LLMGateway` が関数 | isinstance/サブクラス化で型エラー | 後続計画でクラスエイリアス化検討 |
| `src.services/` に空パッケージ残存 | 不要ディレクトリの混在 | 後続計画で削除検討 |
| benchmark baseline の測定ノイズ | フレーキーなベンチ比較 | `tests/benchmarks/compression_baseline.json` の安定化 |
| `tests/e2e/` から 6 ファイル削除 | カバレッジ喪失 | 代替テストの作成を follow-up で検討 |
| `tests/integration/` から 2 ファイル削除 | 旧 8 オーディター依存の削除 | `AuditAggregatorNode` の統合テスト再構築 |
| mypy 500 件の残山 | 型安全性の未整備 | バーンダウン目標（§3）へ継続 |

---

## 3. 後続計画（PLAN_Q4）

### 3.1 mypy バーンダウン

**目標**: mypy errors を 250 件以下に削減（2026-12-31 まで）

**現状**: 500 件
**目標**: 250 件（50% 削減）

**主要な残山**:
- `Column` 系 194 件 → `Mapped[...]` 注釈移行で解消
- `union-attr` 95 件 → `None` ガード追加
- `arg-type` 個別修正

**実装手順**:
1. `Column` 系エラーを `Mapped[...]` 注釈に一括移行
2. `union-attr` エラーに `None` ガードを追加
3. `arg-type` エラーを個別修正
4. 各バッチで ratchet で進捗を確認

**リスク**: `Mapped[...]` 移行は ORM モデルの広範囲に影響するため、慎重なステップバイステップで実施

### 3.2 `LLMGateway` クラスエイリアス化

**現状**: `src/core/llm_gateway.py` の `LLMGateway` は関数（factory）
**問題**: `isinstance(x, LLMGateway)` / サブクラス化 / クラス属性参照で型エラー

**実装**:
```python
# src/core/llm_gateway.py
class LLMGateway(LLMService):
    """旧 LLMGateway 互換クラス（LLMService のサブクラス）"""
    pass
```

**利点**:
- 既存の `LLMGateway()` 呼び出しを維持
- isinstance/サブクラス化をサポート
- mypy の型チェックが正常に動作

**リスク**: `LLMService` の __init__ 引数と互換性を確認する必要あり

### 3.3 `src/services/` 空パッケージ削除

**現状**: `src/services/llm/`、`src/services/llm_clients/`、`src/services/adapters/` が空（__pycache__ のみ）

**実装**:
1. `git rm -r src/services/llm/ src/services/llm_clients/ src/services/adapters/`
2. `src/services/__init__.py` から該当インポートを削除
3. `test_new_shims_registered.py` の整合性確認

**リスク**: 参照元の確認が必要（import が残っていないこと）

### 3.4 e2e / integration テスト再構築

**現状**: Q2/Q3 で 8 ファイル削除（旧 8 オーディター依存）

**代替テストの作成**:

| 削除ファイル | 代替 | 作成理由 |
|--------------|------|----------|
| `test_pillar1_fault_tolerance.py` | `UnifiedAuditor` の degraded 経路テスト | LLM 未設定時の fail-closed 動作確認 |
| `test_pillar1_pipeline_e2e.py` | `AuditAggregatorNode` 統合テスト | 監査→合格/差し戻し経路の E2E |
| `test_regeneration_loop_e2e.py` | `to_agent_result` の再生成ループテスト | 差し戻し→再生成→合格のフロー |
| `test_p1_quality_enhancement_e2e.py` | 品質ゲート閾値テスト | 70 点合格ラインの挙動確認 |
| `test_p2_architecture_ux_e2e.py` | `UnifiedAuditor` 集成テスト | 統合監査の出力形式確認 |
| `test_phase2_full_flow.py` | `AuditAggregator` メトリクステスト | `publish_aggregated_metrics` 動作確認 |

**リスク**: E2E テストの作成は時間がかかる。優先度の高いものから順次

### 3.5 benchmark baseline 安定化

**現状**: `tests/benchmarks/compression_baseline.json` の stdev が 115ms に膨れ上がる測定ノイズ

**実装**:
1. `scripts/benchmark_compression.py` の測定回数を増加（10 → 30 回）
2. 外れ値除去（median + MAD ベース）
3. CI で自動更新しない（手動更新のみ）

**リスク**: 測定回数の増加で CI 実行時間が長くなる

### 3.6 `src.services.llm.circuit_breaker` 削除確認

**現状**: `src/services/llm/circuit_breaker.py` が ModuleNotFoundError（Q3 で削除済み）

**確認**:
- `tests/regression/test_llm_unification_complete.py` で `test_old_llm_circuit_breaker_removed` が pass
- `src.services.llm` パッケージが空であることの確認

---

## 4. 実装順序

### Phase 1: 低リスク修正（1-2 日）
1. `LLMGateway` クラスエイリアス化（§3.2）
2. `src/services/` 空パッケージ削除（§3.3）
3. mypy `Column` 系エラーの `Mapped[...]` 移行（§3.1 の一部）

### Phase 2: 品質向上（3-5 日）
4. mypy `union-attr` エラーの `None` ガード追加（§3.1）
5. e2e / integration テスト再構築（§3.4）
6. benchmark baseline 安定化（§3.5）

### Phase 3: リリース準備（2-3 日）
7. mypy `arg-type` エラーの個別修正（§3.1）
8. `make ci-parity` 完走確認
9. ドキュメント最終同期

---

## 5. リスク管理

### 5.1 ステップバイステップアプローチ

各ステップの完了後に必ず以下を確認:
1. `pytest tests/unit -q --timeout=120` → 0 failed
2. `python scripts/ci_lint_ratchet.py --tool all` → exit 0
3. `pytest tests/regression -q --timeout=120 --maxfail=15` → 0 failed

### 5.2 ロールバック戦略

- 各変更は個別にコミット
- 重大なリグレッション発生時は `git revert` で個別ロールバック
- benchmark baseline の変更は手動更新のみ（自動更新禁止）

### 5.3 CI ゲート

- `make ci-parity` は ratchet + unit + frontend を実行
- regression テストは `pytest -m "not integration and not perf and not slow` に含まれる
- `tests/e2e/` と `tests/integration/` は別ジョブで実行

---

## 6. 検証手順（各 Phase 完了後）

```bash
# Phase 1 完了後
.venv/bin/python -m pytest tests/unit -q --timeout=120
.venv/bin/python scripts/ci_lint_ratchet.py --tool all
.venv/bin/python -m pytest tests/regression/test_llm_unification_complete.py -q
.venv/bin/python -m pytest tests/regression/test_api_unification_complete.py -q

# Phase 2 完了後
.venv/bin/python -m pytest tests/integration/test_audit_aggregator_pipeline.py -q
.venv/bin/python -m pytest tests/regression/test_audit_degraded_gate_contract.py -q

# Phase 3 完了後
make ci-parity
```

---

## 7. 成功基準

| Phase | 成功基準 |
|-------|----------|
| Phase 1 | `LLMGateway` クラス化成功、空パッケージ削除、mypy 450 件以下 |
| Phase 2 | e2e/integration テスト再構築完了、mypy 350 件以下 |
| Phase 3 | mypy 250 件以下、`make ci-parity` exit 0、ドキュメント同期 |

---

## 8. 依存関係と前提条件

- Python 3.13.5 + mypy 2.3.1（ローカル環境）
- CI は Python 3.12（mypy 件数が構造的に異なる）
- `src/llm/adapters/` の `generate_json` 実装は未着手（後続で検討）
- `src/agents/specialists/adapter.py` の `get_aggregator` は unified 経路と整合済み

---

## 9. 付録

### 9.1 変更履歴サマリ

| コミット | 内容 |
|----------|------|
| `1d04565c` | Q3 Step 8: alembic テスト 2 件修復 |
| `c0b236a8` | mypy baseline 自動引き下げ（524→516） |
| `b0a32cc4` | ドキュメント Q3 完了状態同期 |
| `4f388c3d` | Q3 shim removal and test suite clean-up |
| `c67ac2bb` | P0-P2 レビュー対応（監査経路・LLMService・regression） |
| `73b007db` | diff review 不整合修正（baseline/README/STATUS 整合） |

### 9.2 関連ドキュメント

- `docs/STATUS.md` — 現況ステータス（SSOT）
- `docs/SHIM_PATTERN.md` — shim パターン定義（新規 shim 禁止方針）
- `docs/MOVEMENT_MAPPING.md` — 移動マッピング表
- `CHANGELOG.md` — 変更履歴（[Unreleased] セクション）
- `config/ci_lint_baseline.json` — ラチェットベースライン
- `config/shim_registry.json` — shim 登録簿（0 件）
