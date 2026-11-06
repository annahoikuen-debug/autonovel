# CI パス参照一覧 (CI_PATH_REFERENCES.md)

> **目的**: テストディレクトリの移設に伴い、CI ワークフローおよび Makefile のパス参照が壊れないように棚卸しする。
>
> **作成**: Phase A Step A2
> **更新タイミング**: tests/ ディレクトリの物理配置を変更するたびに更新。

---

## 前提

Phase A の移設対象ディレクトリ：
- `tests/services/` → `tests/unit/engine/` / `tests/unit/publishing/` / `tests/unit/integrations/`
- `tests/unit/services/*` → `tests/unit/engine/*` / `tests/unit/publishing/*` / `tests/unit/integrations/*`
- `tests/test_*.py` (39ファイル) → `tests/unit/api/` / `tests/unit/backend/` / `tests/unit/config/` / `tests/unit/database/` / `tests/unit/domain/` / `tests/unit/engine/` / `tests/unit/models/` / `tests/unit/services/` / `tests/integration/` / `tests/regression/`

これらの移動は、**CI の `on.paths` フィルタやテスト実行パスに影響する可能性がある**ため、以下を参照パスを更新対象とする。

---

## .github/workflows/*.yml 内の tests/ 参照

### ci.yml

| 行 | 内容 | 影響判定 | 更新要否 |
|----|------|---------|---------|
| 50 | コメント: `tests/conftest.py` | コメントのみ | 不要 |
| 65 | `pytest tests/regression/test_v5_version_consistency.py` | 個別ファイル指定 | 不要 (regression は移動対象外) |
| 67 | `pytest tests/regression/test_tenant_fk_integrity.py` | 個別ファイル指定 | 不要 |
| 69 | `pytest tests/regression/test_H1_tautology_guard.py` | 個別ファイル指定 | 不要 |
| 71 | `pytest tests/security/test_server_route_mount_parity.py` | `tests/security/` | 不要 (移動対象外) |
| 134 | `pytest tests/security -q` | ディレクトリ指定 | 不要 |
| 136 | `pytest tests/regression/ -v` | ディレクトリ指定 | 不要 (regression は移動対象外) |

**判定**: ci.yml は移動対象外（regression, security のみ参照）。**更新不要**。

### dsp_balancer.yml

| 行 | 内容 | 影響判定 | 更新要否 |
|----|------|---------|---------|
| 7 | `- "tests/**/test_*dsp*.py"` | glob パターン | 不要 (階層によらない) |
| 28 | `pytest tests/ -k dsp` | ルートから `-k` フィルタ | 不要 |

**判定**: glob かつ `-k` フィルタのため、**更新不要**。

### emotional_residue.yml

| 行 | 内容 | 影響判定 | 更新要否 |
|----|------|---------|---------|
| 19 | `on.paths: tests/unit/pipeline/**` | ディレクトリ指定 | **要確認** |
| 20 | `on.paths: tests/unit/config/**` | ディレクトリ指定 | **要確認** |
| 21 | `on.paths: tests/unit/stores/**` | ディレクトリ指定 | 不要 |
| 22 | `on.paths: tests/unit/templates/**` | ディレクトリ指定 | 不要 |
| 23 | `on.paths: tests/integration/pipeline/**` | ディレクトリ指定 | 不要 |
| 24 | `on.paths: tests/integration/agent/**` | ディレクトリ指定 | 不要 |
| 25 | `on.paths: tests/regression/test_emotional_residue_regression.py` | 個別ファイル | 不要 |
| 38-44 | (プッシュ時と同じパス群) | 同上 | 同上 |
| 65 | `pytest tests/unit/pipeline/ tests/unit/config/ tests/unit/stores/ tests/unit/templates/` | テスト実行パス | **要確認** |
| 91 | `pytest tests/integration/pipeline/ tests/integration/agent/` | テスト実行パス | 不要 |
| 111 | `pytest tests/regression/test_emotional_residue_regression.py` | 個別ファイル | 不要 |

**判定**: `tests/unit/pipeline/**` と `tests/unit/config/**` は Phase A で移動対象に含まない（`tests/services/` や `tests/test_*.py` の移動先ではない）ため、**更新不要**。ただし、Step A5 で `tests/test_constants.py` を `tests/unit/config/` に移動する場合、`tests/unit/config/**` のフィルタ範囲に含まれるため発火条件は維持される。

### fusion.yml

| 行 | 内容 | 影響判定 | 更新要否 |
|----|------|---------|---------|
| 23 | `pytest tests/unit/fusion/ tests/unit/templates/` | テスト実行パス | 不要 |
| 38 | `pytest tests/integration/fusion/ tests/integration/api/` | テスト実行パス | 不要 |
| 53 | `pytest tests/regression/test_week4_regression.py` | 個別ファイル | 不要 |
| 68 | `pytest tests/performance/test_fusion_perf.py` | 個別ファイル | 不要 |

**判定**: **更新不要**。

### rule_engine.yml

| 行 | 内容 | 影響判定 | 更新要否 |
|----|------|---------|---------|
| 12 | `on.paths: tests/unit/rules/**` | ディレクトリ指定 | 不要 |
| 13 | `on.paths: tests/unit/config/test_emotional_rules_yaml.py` | 個別ファイル | 不要 |
| 14 | `on.paths: tests/unit/config/test_plot_events_yaml.py` | 個別ファイル | 不要 |
| 15 | `on.paths: tests/integration/rules/**` | ディレクトリ指定 | 不要 |
| 16-17 | `on.paths: tests/regression/...` | 個別ファイル | 不要 |
| 38 | `pytest tests/unit/rules/ tests/unit/config/...` | テスト実行パス | 不要 |
| 40 | `pytest tests/unit/stores/...` | テスト実行パス | 不要 |
| 42 | `pytest tests/unit/pipeline/test_rule_engine_stage.py` | 個別ファイル | 不要 |
| 55 | `pytest tests/integration/rules/...` | テスト実行パス | 不要 |
| 73 | `pytest tests/regression/...` | テスト実行パス | 不要 |
| 75 | `pytest tests/performance/...` | テスト実行パス | 不要 |

**判定**: **更新不要**。

---

## Makefile 内の tests/ 参照

| 行 | 内容 | 影響判定 | 更新要否 |
|----|------|---------|---------|
| 62 | `pytest tests/unit -q` | ディレクトリ指定 (再帰) | 不要 (サブディレクトリ移動は再帰対象内に含まれる) |
| 65 | `pytest tests/integration -v` | ディレクトリ指定 | 不要 |
| 68 | `pytest tests/contract -v` | ディレクトリ指定 | 不要 |
| 71 | `pytest tests/perf -v` | ディレクトリ指定 | 不要 |

**判定**: `tests/unit` 再帰走査のため、サブディレクトリ移動後も自動で発見される。**更新不要**。

---

## まとめ

| ワークフロー/ファイル | 更新要否 | 理由 |
|-------------------|---------|------|
| `.github/workflows/ci.yml` | 不要 | regression / security のみ参照 |
| `.github/workflows/dsp_balancer.yml` | 不要 | glob / `-k` フィルタ |
| `.github/workflows/emotional_residue.yml` | 不要 | 対象ディレクトリは移動対象外 |
| `.github/workflows/fusion.yml` | 不要 | 対象ディレクトリは移動対象外 |
| `.github/workflows/rule_engine.yml` | 不要 | 対象ディレクトリは移動対象外 |
| `Makefile` | 不要 | `tests/unit` 再帰走査 |

**Step A2 完了条件**: `docs/CI_PATH_REFERENCES.md` に上記一覧が記載され、更新不要と判定されていること。

> 補足: Phase A のテスト移設後、CI を実行して `tests/regression/`, `tests/security/`, `tests/unit/` などの既定パスが正しく収集・実行されることを確認すること（Step A6）。
