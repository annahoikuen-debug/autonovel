# 案B 実装後の残課題 実装計画書 (PLAN_C_POST_REORGANIZATION.md)

> **目的**: 案B（36ステップのレイヤー再編）完了後に行うべき 3 つの残課題を、
> 低性能LLMでも実装できる粒度で手順化する。
>
> **前提**: 案B 全36ステップ完了済み。全後方互換 shim は `config/shim_registry.json` に登録済み。
> Python 実行は `.venv/bin/python3`。

---

## 調査結果サマリー（現状）

| 課題 | 現状 | 影響範囲 |
|------|------|---------|
| A. tests/ 物理配置 | tests/ 直下に39個の孤テスト、`tests/services/`, `tests/unit/services/` に旧レイヤー名のまま残る | テスト発見性・CI ワークフロー |
| B. src/services/ ルート89ファイル | サブパッケージ28個は shim 化済みだが、ルートの .py が89個残存 | コードレビューの可読性 |
| C. Docker COPY パス | `Dockerfile` は `COPY src/ config/` とディレクトリ丸ごとコピーのため**移動自体は影響なし**。ただし shim も同梱される | イメージサイズ・起動時 import |

---

## Phase A: tests/ ディレクトリの物理配置整理 (Steps A1-A6)

### 課題の詳細

- `tests/` 直下に39個の `test_*.py` が裸で存在（`test_image_service.py`, `test_health.py` 等）
- `tests/services/` に旧レイヤー名のまま（anti_ai, foreshadowing 等）
- `tests/unit/services/` に17個のサブディレクトリ（exporters, formatters 等 → 既に `src/publishing/` へ移設済み）
- `tests/unit/llm_clients/`（Step 13 で `tests/unit/llm/` に移設済みだが旧ディレクトリが残存する可能性）
- CI (`.github/workflows/*.yml`) が `tests/unit/pipeline/**` 等のパスを `on.paths` で参照 → 移動で発火しなくなるリスク

### Step A1: tests/ 直下39ファイルの分類表作成

**目的**: どのテストがどのディレクトリへ移すべきかを決定する。

**手順**:
1. `tests/` 直下の全 `test_*.py` を列挙
2. 各ファイルの import から被テスト対象を推定:
   - `from src.services.*` / `from src.engine.*` → `tests/unit/engine/` or `tests/unit/services/`
   - `from src.backend.*` → `tests/unit/backend/`
   - `from src.models.*` / `from src.domain.*` → `tests/unit/models/` or `tests/unit/domain/`
   - FastAPI ルータ参照 → `tests/unit/api/`
   - 複数レイヤー跨ぎ（統合的） → `tests/integration/`
3. `docs/TEST_CLASSIFICATION.md` に分類表を作成

**テスト**: 分類表の各行に「移動元パス・移動先パス・根拠」が記載されていること。

**対象例（調査済み）**:
| ファイル | 被テスト対象 | 移動先 |
|---------|------------|--------|
| `tests/test_image_service.py` | `src.services.image_service` | `tests/unit/services/image/` |
| `tests/test_health.py` | `src.backend` health | `tests/unit/backend/` |
| `tests/test_styles_router.py` | `src.interfaces.api.styles` | `tests/unit/api/` |
| `tests/test_constants.py` | `src.config.constants` | `tests/unit/config/` |
| `tests/test_uow.py` | DB UoW | `tests/unit/database/` |
| `tests/test_migrations.py` | alembic | `tests/integration/` |
| `tests/test_conftest_fixtures.py` | conftest 自身 | `tests/regression/` |

### Step A2: CI ワークフローのパス参照棚卸し

**目的**: 移動で CI の `on.paths` フィルタが壊れないようにする。

**手順**:
1. `.github/workflows/*.yml` から全 `tests/...` パス参照を抽出:
   ```bash
   grep -n "tests/" .github/workflows/*.yml
   ```
2. 調査結果を `docs/CI_PATH_REFERENCES.md` に一覧化
3. 移動後に更新が必要なエントリをマーク

**既知の参照（調査済み）**:
- `emotional_residue.yml`: `tests/unit/pipeline/**`, `tests/unit/config/**`, `tests/unit/stores/**`, `tests/unit/templates/**`, `tests/integration/pipeline/**`, `tests/integration/agent/**`
- `dsp_balancer.yml`: `tests/**/test_*dsp*.py`（glob のため影響小）
- `ci.yml`: `tests/security`, `tests/regression/`, 個別ファイル数個

**テスト**: `docs/CI_PATH_REFERENCES.md` に全ワークフローの参照パスが列挙されていること。

### Step A3: tests/services/ → tests/unit/engine/ への移設（生成系）

**目的**: 案B で `src/engine/` へ移したサブパッケージのテスト配置を揃える。

**対象**:
| 移動元 | 移動先 |
|--------|--------|
| `tests/services/anti_ai/` | `tests/unit/engine/anti_ai/` |
| `tests/services/test_foreshadowing_*.py` | `tests/unit/engine/foreshadowing/` |
| `tests/services/test_hook_*.py` | `tests/unit/engine/foreshadowing/`（hook は foreshadowing 系） |
| `tests/services/test_pipeline_base.py` | `tests/unit/engine/` |
| `tests/services/test_illustration_point_generation_step.py` | `tests/unit/publishing/illustration/` |
| `tests/services/test_manga_pipeline.py` | `tests/unit/publishing/manga/` |

**手順**:
1. `mkdir -p` で移動先作成
2. `git mv` で移動（履歴維持）
3. 移動先に `__init__.py` を作成
4. import 文が変わらないか確認（pytest.ini の `pythonpath = .` によりルートからの import は変更不要）
5. 実行: `.venv/bin/python3 -m pytest tests/unit/engine/ tests/unit/publishing/ -v`

**テスト**: 移動後も全テスト緑（件数一致をログで確認）。

### Step A4: tests/unit/services/ のサブディレクトリ再配置

**目的**: 案B の移設先（engine/publishing/integrations）に対応する。

**対象マッピング**:
| 移動元 | 移動先 |
|--------|--------|
| `tests/unit/services/{audit,auditors,compression,context_compression,foreshadowing,nlp,prose}/` | `tests/unit/engine/{同名}/` |
| `tests/unit/services/{exporters,formatters,illustration,manga}/` | `tests/unit/publishing/{同名}/` |
| `tests/unit/services/{marketing,prefetch}/` | `tests/unit/integrations/{同名}/` |
| `tests/unit/services/llm/`（0ファイル） | 削除 |
| `tests/unit/services/*.py`（ルートファイル群: age_client, audio_adapters 等） | `tests/unit/services/` に残す（ルートサービス対応のため） |

**手順**:
1. マッピング表を確認
2. `git mv` で一括移動
3. 空になった `tests/unit/services/llm/` は `git rm`
4. 実行:
   ```bash
   .venv/bin/python3 -m pytest tests/unit/engine tests/unit/publishing tests/unit/integrations tests/unit/services -q
   ```

**テスト**: 全テスト緑 + 件数一致。

### Step A5: tests/ 直下39ファイルの移設

**目的**: 裸で置かれたテストを適切なサブディレクトリへ。

**手順**:
1. Step A1 の分類表に従い `git mv` を実行
2. `tests/test_conftest_fixtures.py` のみ `tests/regression/` へ（conftest の回帰確認のため）
3. 全体収集確認:
   ```bash
   .venv/bin/python3 -m pytest --collect-only -q 2>&1 | tail -5
   ```
   移動前後の収集件数が一致すること（件数の記録は移動前に `--collect-only -q | tail -1` で取る）。

**テスト**: 収集件数一致 + `tests/` 直下に `test_*.py` が残っていないこと。

### Step A6: CI パス参照の更新と総合リグレッション

**手順**:
1. Step A2 の一覧に基づき `.github/workflows/*.yml` の `on.paths` を更新
2. Makefile の test ターゲット確認（`tests/unit`, `tests/integration`, `tests/contract`, `tests/perf` はサブディレクトリ移動のため影響なし）
3. 総合テスト:
   ```bash
   .venv/bin/python3 -m pytest tests/regression/ -q
   .venv/bin/python3 -m pytest tests/unit -q --tb=short
   ```

**テスト**: `tests/regression/test_shim_imports.py`, `test_new_shims_registered.py` 含め全緑。

---

## Phase B: src/services/ ルート89ファイルの整理 (Steps B1-B5)

### 課題の詳細

`src/services/` 直下に89個の `.py` が残存。案B ではサブパッケージのみ 3 パッケージへ移設し、ルートファイルは「ルートサービス」として残した。これらを精査し、移設対象を決定する。

**調査済み・参照数トップ（src/ 内）**:
| 参照数 | ファイル | 推奨移設先 |
|-------|---------|-----------|
| 12 | `llm_service.py` | `src/llm/service.py`（LLM 統合の最終ピース） |
| 10 | `image_service.py` | `src/publishing/illustration/image_service.py` |
| 9 | `rag_service.py` | `src/integrations/rag/`（shim で `src.services.rag_service` 維持） |
| 8 | `audit_aggregator.py` | `src/engine/audit/` |
| 7 | `semantic_cache.py` | `src/integrations/` |
| 5 | `embedding_service.py` | `src/integrations/rag/` |
| 5 | `book_score_*.py` (3ファイル) | `src/engine/` |
| 4 | `quality_scorer.py` | `src/engine/` |
| 4 | `pipeline_base.py` | `src/engine/` |
| 4 | `foreshadowing_service.py` | `src/engine/foreshadowing/` |
| 4 | `cost_analytics.py` | `src/integrations/cost_guard/` |
| 4 | `auto_workflow_pipeline.py` | `src/engine/`（Orchestrator） |

### Step B1: 89ファイルの分類と移動計画の確定

**目的**: 全89ファイルを「移設する / ルートに残す / shim 化する」に三分類する。

**手順**:
1. 各ファイルの import 先と参照数を機械的に収集:
   ```bash
   for f in src/services/*.py; do
     mod=$(basename $f .py)
     n=$(grep -rl "services\.$mod\b" src/ --include="*.py" | grep -v __pycache__ | wc -l)
     echo "$n $mod"
   done | sort -rn
   ```
2. 参照数 ≥3 かつ単一レイヤーに属するものは移設対象
3. `errors.py`, `resilience.py`, `retry_decorator.py` 等の横断ユーティリティは `src/services/` に残す（他レイヤーから使われる共通基盤）
4. `docs/SERVICES_ROOT_CLASSIFICATION.md` に分類表作成（移動元・移動先・参照数・根拠）

**テスト**: 分類表で89ファイルすべてが網羅されていること（行数カウントで確認）。

### Step B2: 高参照数ファイルの移設（バッチ1: LLM・出版・RAG 関連）

**対象（8ファイル程度）**:
| 移動元 | 移動先 | shim |
|--------|--------|------|
| `src/services/llm_service.py` | `src/llm/service.py` | `src/services/llm_service.py` |
| `src/services/image_service.py` | `src/publishing/illustration/image_service.py` | `src/services/image_service.py` |
| `src/services/rag_service.py` | `src/integrations/rag/rag_service.py` | `src/services/rag_service.py` |
| `src/services/embedding_service.py` | `src/integrations/rag/embedding_service.py` | `src/services/embedding_service.py` |
| `src/services/semantic_cache.py` | `src/integrations/semantic_cache.py` | `src/services/semantic_cache.py` |
| `src/services/sparse_retriever.py` | `src/integrations/rag/sparse_retriever.py` | `src/services/sparse_retriever.py` |
| `src/services/hybrid_retriever.py` | `src/integrations/rag/hybrid_retriever.py` | `src/services/hybrid_retriever.py` |
| `src/services/reflective_rag.py` | `src/integrations/rag/reflective_rag.py` | `src/services/reflective_rag.py` |

**手順（各ファイル共通）**:
1. `git mv src/services/X.py src/<dest>/X.py`
2. 旧パスに shim を作成:
   ```python
   """後方互換 shim: 実体は src/<dest>/X.py に移設済み。"""
   from __future__ import annotations
   from src.<dest>.X import *  # noqa: F401, F403
   __all__ = [name for name in dir() if not name.startswith("_")]
   ```
3. `config/shim_registry.json` に登録
4. 移設先ディレクトリ内部の `src.services.X` 参照を `src.<dest>.X` に修正（`grep -rn "services\.X" src/<dest>/`）
5. サブモジュール直接参照（`from src.services.X import Y` が複数シンボル）は shim の `__getattr__` では解決不可 → `from src.<dest>.X import Y` に一括置換:
   ```bash
   grep -rln "src\.services\.X" src/ tests/ --include="*.py" | xargs sed -i 's/src\.services\.X/src.<dest>.X/g'
   ```
6. import 確認 + テスト:
   ```bash
   .venv/bin/python3 -c "import src.services.X; print('OK')"
   .venv/bin/python3 -m pytest tests/unit/test_rag_service.py tests/unit/test_graphrag.py -q
   ```

**テスト**: shim import テスト + 対象ユニットテスト全緑。

### Step B3: 高参照数ファイルの移設（バッチ2: engine 関連）

**対象（10ファイル程度）**:
| 移動元 | 移動先 |
|--------|--------|
| `src/services/audit_aggregator.py` | `src/engine/audit/aggregator.py` |
| `src/services/audit_adapter.py` | `src/engine/audit/adapter.py` |
| `src/services/audit_service.py` | `src/engine/audit/service.py` |
| `src/services/foreshadowing_service.py` | `src/engine/foreshadowing/service.py` |
| `src/services/quality_scorer.py` | `src/engine/quality_scorer.py` |
| `src/services/pipeline_base.py` | `src/engine/pipeline_base.py` |
| `src/services/pipeline_steps.py` | `src/engine/pipeline_steps.py` |
| `src/services/auto_workflow_pipeline.py` | `src/engine/auto_workflow_pipeline.py` |
| `src/services/book_score_{mapping,models,service}.py` | `src/engine/book_score/` |
| `src/services/cost_analytics.py` | `src/integrations/cost_guard/analytics.py` |

**手順**: Step B2 と同一（git mv → shim → registry 登録 → 参照置換 → テスト）。

**注意**: `src/services/pipeline_steps.py` は15ファイルから参照される中核。shim ではなく全参照を先に置換してから shim を残す。

**テスト**: `.venv/bin/python3 -m pytest tests/regression/test_H1_audit_agent_smoke.py tests/unit/services/ -q`

### Step B4: 残りファイルの分類確定（横断ユーティリティのルート残置）

**対象**: `errors.py`, `resilience.py`, `retry_decorator.py`, `redis_cache.py`, `token_tracker.py`, `prompt_*.py` 等。

**手順**:
1. Step B1 の分類表で「ルート残置」と判定したファイルを確定
2. 残置理由を `docs/SERVICES_ROOT_CLASSIFICATION.md` に明記（例: 「src/backend と src/engine の双方から使われる横断基盤」）
3. ルートファイル数が目標（目安: 30ファイル以下）に収まっているか確認
   ```bash
   ls src/services/*.py | grep -v __pycache__ | wc -l
   ```
4. 収まらない場合、参照数 1-2 のファイルを追加バッチで移設

**テスト**: `tests/regression/test_services_root_count.py` を新規作成:
```python
"""src/services/ ルートのファイル数が増加しないことのラチェット。"""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
MAX_ROOT_FILES = 35  # Step B4 完了時の実測値 + 余裕5

def test_services_root_file_count_within_budget():
    files = [f for f in (ROOT / "src" / "services").glob("*.py")
             if f.name != "__init__.py"]
    assert len(files) <= MAX_ROOT_FILES, (
        f"src/services/ ルートに {len(files)} ファイル（上限 {MAX_ROOT_FILES}）。"
        "新規ルートファイルの追加ではなく src/engine|publishing|integrations への移設を検討すること"
    )
```

### Step B5: services 統合の総合リグレッションテスト

**新規作成**: `tests/regression/test_services_root_unification_complete.py`

**内容**:
1. 全移設済みファイルの旧パス shim が import 可能（パラメータ化リスト）
2. `src/services/` ルートに「shim でない実体」が残っていない（docstring で `後方互換` を含まないファイルは分類表の「残置」リストに含まれること）
3. `config/shim_registry.json` に全 shim が登録済み（既存 `test_new_shims_registered.py` で担保）
4. `ruff check src/services src/engine src/publishing src/integrations` が通過
5. `src/services/` から `src/engine/` 等への直接参照（shim を経由しない新規依存）が発生しないこと（アーキテクチャガード）

**テスト**: 上記5項目が全パス。

---

## Phase C: Docker・デプロイ設定の確認と最適化 (Steps C1-C3)

### 調査結果（現状）

- `Dockerfile`: `COPY --chown=appuser:appuser src/ ./src/` / `config/ ./config/` と**ディレクトリ丸ごとコピー** → 案B のファイル移動は**問題なし**
- `docker-compose.yml`: `./storage:/app/storage` のみ（ソースはイメージ同梱）
- ただし **shim ファイルも同梱される** → イメージに不要な後方互換コードが積まれる

### Step C1: Docker ビルドの動作確認

**手順**:
1. ビルド実行:
   ```bash
   docker build -t autonovel-test -f Dockerfile . 2>&1 | tail -20
   ```
2. コンテナ内で import 確認:
   ```bash
   docker run --rm autonovel-test python -c "from src.backend.server import app; print('app OK')"
   ```
3. `docker-compose.yml` の `config/` マウント有無を確認（`config/settings.toml` 等の YAML はホストから見える必要がある場合あり）

**テスト**: ビルド成功 + app import 成功。

**フォールバック**: Docker が使えない環境では `Dockerfile` の COPY パスと `src/` 構造の整合を静的検証:
```bash
grep -n "^COPY" Dockerfile Dockerfile.prod
# src/ config/ formatters/ plugins/ prompts/ schemas/ が存在することを確認
for d in src config formatters plugins prompts schemas; do [ -d "$d" ] || echo "MISSING: $d"; done
```

### Step C2: shim のイメージ除外検討（任意・ラチェット維持）

**目的**: 本番イメージから後方互換 shim を除外してサイズ・起動を最適化する。

**方針（2案）**:
- **案1（非推奨・早い）**: Dockerfile で `RUN find src -name "*.py" -exec grep -l "後方互換 shim" {} + | xargs rm` — 危険（grep で shim 判定は脆い）
- **案2（推奨・安全）**: shim を削除せず、起動時の import 数を監視するだけにとどめる。shim は `__init__.py` 経由の遅延 import のため起動コストは小さい

**判断**: **案2 を採用**。shim 削除は案B の後方互換方針と矛盾するため、本ステップでは監視のみ。

**手順**:
1. `tests/regression/test_docker_copy_paths.py` を作成:
   ```python
   """Dockerfile の COPY パスが実在するディレクトリを指していることの検証。"""
   from pathlib import Path
   ROOT = Path(__file__).resolve().parents[2]

   def test_dockerfile_copy_paths_exist():
       dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
       for line in dockerfile.splitlines():
           line = line.strip()
           if line.startswith("COPY") and "--from=" not in line:
               parts = line.split()
               src_path = parts[-2]
               if src_path.startswith("./") or src_path.endswith("/"):
                   target = ROOT / src_path.rstrip("/")
                   assert target.exists(), f"Dockerfile の COPY 先が存在しない: {src_path}"
   ```
2. `Dockerfile.prod` にも同様のテストを追加（parametrize）

**テスト**: 新規テストがパス。

### Step C3: docker-compose のボリューム・エントリポイント確認

**手順**:
1. `docker/backend/entrypoint.sh` 内のパス参照を確認:
   ```bash
   grep -n "src/\|config/" docker/backend/entrypoint.sh
   ```
2. 移動で壊れるパス（例: `python -m src.services.X`）がないことを確認
3. `docker-compose.prod.yml` の build context・args が新しい構造を前提にしていることを確認
4. e2e 用 `docker-compose.e2e.yml` の同様確認

**テスト**: entrypoint 内に削除済み/移動済みパスの参照がないことの静的検証を `test_docker_copy_paths.py` に追加:
```python
def test_entrypoint_no_stale_paths():
    ep = ROOT / "docker" / "backend" / "entrypoint.sh"
    content = ep.read_text(encoding="utf-8")
    # 案B で実体が消えたパス（例: src/core/llm_clients の直接実行）
    stale = ["src/core/llm_clients", "src/api/dashboard.py"]
    for s in stale:
        assert s not in content, f"entrypoint.sh に旧パス参照が残っている: {s}"
```

---

## 全体スケジュール

| Phase | Step | 内容 | 見積 | 前提 |
|-------|------|------|------|------|
| A | A1 | tests/ 直下39ファイル分類表 | 小 | — |
| A | A2 | CI パス参照棚卸し | 小 | — |
| A | A3 | tests/services/ → tests/unit/engine|publishing/ | 中 | A1 |
| A | A4 | tests/unit/services/ サブディレクトリ再配置 | 中 | A1 |
| A | A5 | tests/ 直下39ファイル移設 | 中 | A1, A2 |
| A | A6 | CI 更新 + 総合リグレッション | 小 | A3-A5 |
| B | B1 | src/services/ ルート89ファイル分類表 | 小 | — |
| B | B2 | バッチ1: LLM・出版・RAG 関連8ファイル移設 | 大 | B1 |
| B | B3 | バッチ2: engine 関連10ファイル移設 | 大 | B1 |
| B | B4 | 残り分類確定 + ラチェットテスト | 小 | B2, B3 |
| B | B5 | services 統合総合リグレッション | 小 | B4 |
| C | C1 | Docker ビルド動作確認 | 小 | — |
| C | C2 | COPY パス静的検証テスト | 小 | — |
| C | C3 | entrypoint/compose 確認 | 小 | C1 |

**推奨実行順**: A → B → C（A と B は独立のため並行も可。C は最終確認）

---

## 各 Step の共通ルール（低性能LLM向け）

1. **必ず `git mv` を使う**（履歴維持。`mv` ではなく `git mv`）
2. **移動 → shim 作成 → registry 登録 → 参照置換 → import 確認 → テスト** の順を守る
3. **サブモジュール直接参照**（`from src.services.X.Y import Z`）は shim の `__getattr__` で解決不可。**参照側を必ず新パスに置換する**
4. **テスト実行は必ず件数をログに残す**:
   ```bash
   .venv/bin/python3 -m pytest <対象> -q 2>&1 | tail -3
   ```
   移動前後で件数が一致することを確認
5. **1 Step ごとに `config/shim_registry.json` を更新**（`tests/regression/test_new_shims_registered.py` が CI で検出）
6. **失敗したら直前の Step まで戻る**。一括置換の取り消しは `git checkout -- <file>` が使える（ただし shim 作成済みの場合は手動で戻す）

## 検証コマンド（各 Phase 終了時）

```bash
# shim 整合性
.venv/bin/python3 -m pytest tests/regression/test_shim_imports.py tests/regression/test_new_shims_registered.py -q

# lint ラチェット
.venv/bin/python3 -m pytest tests/regression/test_lint_budget.py -q

# サマリーテスト（案B で作成済み）
.venv/bin/python3 -m pytest tests/regression/test_llm_unification_complete.py \
  tests/regression/test_api_unification_complete.py \
  tests/regression/test_config_unification_complete.py \
  tests/regression/test_schemas_unification_complete.py -q

# 収集件数の全体確認
.venv/bin/python3 -m pytest --collect-only -q 2>&1 | tail -3
```
