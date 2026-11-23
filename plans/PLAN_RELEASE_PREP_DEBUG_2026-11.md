# PLAN_RELEASE_PREP_DEBUG — 公開前デバッグ 詳細実装計画書

- **作成日**: 2026-11-23
- **対象ブランチ**: `merge/q7-integration`
- **作成者**: OpenCode Agent
- **ステータス**: ドラフト（未承認）
- **関連コミット**: `4a7d770f fix: resolve pre-release test failures and spec drift`

---

## 1. 概要

本計画書は、AutoNovel プロジェクトの公開前デバッグにおける残課題を解決するための詳細実装計画である。

前回のデバッグ調査（`tests/` 全実行: 9375 passed / 8 failed）により、8件のテスト失敗は全て修正・コミット済みである。しかし、リリースに向けては以下の**構造的・環境的課題**が未解決であり、CI（`make verify`）をパスさせるために対応が必要。

未解決課題:
1. **`alembic check` 失敗（exit 255）** — モデルメタデータとマイグレーションファイルのスキーマ乖離
2. **mypy バージョン不一致** — 要求 `2.3.1` に対しインストール済み `2.4.1`；Python `3.13.5` に対し要求 `>=3.12`（3.12 推奨）
3. **ruff format 未整形** — 935ファイルが `ruff format --check` で未整形と判定（baseline: 0ファイル）

---

## 2. 目標（Definition of Done）

以下すべてを達成した状態を完了とする。

| No. | 目標 | 測定方法 |
|-----|------|----------|
| D1 | `alembic check` が exit 0 で完了 | `.venv/bin/python -m alembic check` |
| D2 | `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` の往復が成功 | `make test-migration` |
| D3 | mypy バージョンが `2.3.1` に固定され、`make typecheck` が fail-fast で止まらない | `.venv/bin/python -m mypy --version` |
| D4 | Python 3.12 環境で `.venv` が再構築され、バックエンドが起動可能 | `python3.12 --version` + `import src.backend.server` |
| D5 | `ruff format --check src tests config scripts` が 0ファイル未整形 | `make format-check` |
| D6 | `make verify` が全体で緑（ci-parity + lint-layers + typecheck + test-contract + test-migration） | `make verify` |
| D7 | フロントエンドの `test:ci` / `lint` / `typecheck` が緑 | `make frontend-test` / `make frontend-lint` |

---

## 3. 課題別詳細実装手順

### 課題 A: `alembic check` 失敗（スキーマ乖離）

#### 3.1 現状
- `alembic check` は **exit 255** で失敗
- 検出された乖離（モデルメタデータに存在し、マイグレーションに未反映）:
  - `digest_rollups` テーブル（およびインデックス `ix_digest_rollups_book_level`, `ix_digest_rollups_stale_at`）
  - `rag_reflection_history` テーブル（およびインデックス 3件）
  - `audit_specialist_results` テーブル（およびインデックス 2件）
  - `audit_lessons` テーブル（およびインデックス `ix_audit_lessons_book_status_dim`）
  - `episode_digests` テーブル（およびインデックス 2件）
  - `foreshadowings` テーブル（およびインデックス `ix_foreshadowings_book_status`）
  - `credit_transactions.created_at` の nullability（NOT NULL 付与が未反映）

#### 3.2 リスク
- 新規DB構築時や `alembic upgrade head` でスキーマが不整合になり、テスト・本番デプロイで失敗する可能性
- `make test-migration`（`make verify` の一部）が失敗し、PRマージをブロック

#### 3.3 実装手順

**Step A1: 現状のマイグレーション履歴を記録**
```bash
cd /home/annahoikuen/autonovel
.venv/bin/python -m alembic heads
.venv/bin/python -m alembic history --verbose | head -50
```
出力を `plans/alembic-history-before-fix.txt` に保存。

**Step A2: 既存DBのバックアップ**
```bash
cp autonovel.db autonovel.db.bak.$(date +%Y%m%d%H%M%S)
```
※ 本番相当データが含まれる可能性があるため、必ず実施。

**Step A3: 差分マイグレーションを自動生成**
```bash
HUEY_BACKEND=sqlite DATABASE_URL=sqlite:///./autonovel.db \
.venv/bin/python -m alembic revision --autogenerate -m "fix schema drift after model changes"
```
生成されたファイルを `src/backend/alembic/versions/` に確認。

**Step A4: 生成マイグレーションのレビューと修正**
- `upgrade()` / `downgrade()` が意図した変更のみを含むか確認
- 不要な `drop_table` / `drop_index` が含まれていないか確認（モデル側でテーブル定義が削除された場合のみ正当）
- `credit_transactions.created_at` の `modify_nullable` が正しく反映されているか確認
- 必要に応じて手動でマイグレーションファイルを編集

**Step A5: マイグレーション適用と往復検証**
```bash
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m alembic downgrade -1
.venv/bin/python -m alembic upgrade head
```
すべて exit 0 であることを確認。

**Step A6: `alembic check` が通ることを確認**
```bash
.venv/bin/python -m alembic check
```
exit 0 であること。

**Step A7: テスト実行**
```bash
HUEY_BACKEND=sqlite DATABASE_URL=sqlite:///./autonovel.db \
.venv/bin/python -m pytest -q -m "not integration and not perf and not slow" --timeout=120
```
回帰がないことを確認。

---

### 課題 B: mypy バージョン不一致 + Python バージョン不整合

#### 3.1 現状
| 項目 | 要求 | 現状 |
|------|------|------|
| Python | 3.12（推奨、AGENTS.md） | 3.13.5 (`.venv`) |
| mypy | 2.3.1（`Makefile` / `pyproject.toml` / CI でピン） | 2.4.1 |

- AGENTS.md ルール #1: mypy バージョン不一致だとラチェット判定（`config/ci_lint_baseline.json` の mypy=450）が偽 FAIL/GOOD になる
- mypy 2.3.1 は Python 3.13 の新構文（`type` ステートメント等）に非対応
- `make typecheck` はバージョンチェックで fail-fast して実行されない

#### 3.2 実装手順

**Step B1: Python 3.12 の利用可能性を確認**
```bash
python3.12 --version 2>/dev/null || py3.12 --version 2>/dev/null || which python3.12
```
見つからない場合は `pyenv` やシステムパッケージで Python 3.12 をインストール。

**Step B2: 既存 `.venv` の記録と削除**
```bash
.venv/bin/pip freeze > plans/requirements-before-recreate.txt
rm -rf .venv
```

**Step B3: Python 3.12 で `.venv` を再作成**
```bash
python3.12 -m venv .venv
source .venv/bin/activate
# または Windows の場合: .venv/Scripts/Activate.ps1
```

**Step B4: 依存関係をインストール**
```bash
pip install -e ".[dev,rag]"
pip install 'mypy==2.3.1'
```

**Step B5: バージョン確認**
```bash
python --version        # 3.12.x であること
pip show mypy | grep Version  # 2.3.1 であること
pip show ruff | grep Version  # 0.16.5 に合わせる（オプション、baselineと整合）
```

**Step B6: `make typecheck` が fail-fast で止まらないことを確認**
```bash
make typecheck
```
mypy バージョンチェックを通過し、実際の型チェックが実行されること。

**Step B7: mypy エラー件数をベースラインと比較**
- `config/ci_lint_baseline.json` の mypy_errors=450、unused_ignore_errors=216 を参照
- Python 3.12 + mypy 2.3.1 での実測件数を記録し、ベースラインを超えないことを確認
- 超える場合は個別修正または baseline の再実測（`README.md` のベースライン行も同時更新）

---

### 課題 C: ruff format 未整形（935ファイル）

#### 3.1 現状
- `ruff format --check src tests config scripts` → 935ファイル未整形
- インストール済み ruff: **0.17.4**
- `config/ci_lint_baseline.json` の `format_files: 0` は ruff 0.16.5 での実測値
- ruff バージョン差による整形式の違いの可能性が高い

#### 3.2 実装手順

**Step C1: ruff バージョン差の影響を切り分け**
```bash
pip install 'ruff==0.16.5'
.venv/bin/python -m ruff format --check src tests config scripts 2>&1 | tail -5
```
- 0.16.5 で 0ファイル未整形になれば、バージョン差が原因
- 0.16.5 でも未整形が残れば、実際の整形不備

**Step C2: CIと同じ ruff バージョンを固定**
- バージョン差が原因の場合、`pip install 'ruff==0.16.5'` を維持
- `Makefile` / CI（`.github/workflows/ci.yml`）で ruff バージョンが固定されているか確認

**Step C3: 実際の整形不備を修正（もし0.16.5でも残る場合）**
```bash
.venv/bin/python -m ruff format src tests config scripts
```
- `git diff` で変更内容をレビュー
- 意図しない大規模変更がないか確認

**Step C4: `make format-check` が緑になることを確認**
```bash
make format-check
```

---

### 課題 D: alembic リビジョン番号重複（予防的整理）

#### 3.1 現状
- `0029_add_foreshadowing_scope.py` / `0030_add_foreshadowing_scope.py`（ファイル名がほぼ同一）
- `0035_audit_lessons.py` / `0035_digest_rollups.py`（両方 0035 番台）
- `alembic heads` は単一ヘッド（`0036_task_wal_logs_worker_id`）なので動作上は問題なし
- 将来のマイグレーション追加で複数ヘッド・衝突のリスク

#### 3.2 実装手順（オプション、リリース後に延期可）

**Step D1: リビジョン番号の連番整理**
- `0035_audit_lessons.py` → `0035_audit_lessons.py`（維持、既に線形化済み）
- `0035_digest_rollups.py` → `0036_...` にリネームし、`down_revision` を調整
- 以降のリビジョン番号を連番に再振り

**Step D2: `alembic heads` が単一であることを再確認**

---

## 4. 検証・テスト手順

すべての課題対応後、以下を順に実行し、全て緑であることを確認する。

```bash
# 1. バックエンド単体テスト
make test

# 2. リント（ruff）
make lint

# 3. レイヤー境界チェック
make lint-layers

# 4. 形式チェック
make format-check

# 5. 型チェック（mypy 2.3.1 必須）
make typecheck

# 6. 契約テスト（OpenAPIスナップショット等）
make test-contract

# 7. マイグレーション往復検証
make test-migration

# 8. フロントエンド
cd frontend && npm run test:ci && npm run lint && npm run typecheck

# 9. フル検証（CIと同一）
make verify
```

---

## 5. ロールバック計画

| 課題 | ロールバック手順 |
|------|-----------------|
| A (alembic) | `autonovel.db.bak.*` からDBを復元；生成マイグレーションファイルを削除 |
| B (mypy/Python) | 既存 `.venv` をバックアップから復元；または `plans/requirements-before-recreate.txt` から再インストール |
| C (ruff format) | `git diff` を `git checkout` で元に戻す |
| D (alembicリビジョン) | マイグレーションファイルを元の状態に戻す |

---

## 6. スケジュール（目安）

| フェーズ | 作業 | 見積もり |
|----------|------|----------|
| Phase 1 | alembic 差分マイグレーション生成・適用・検証（A1–A7） | 2–4時間 |
| Phase 2 | Python 3.12 + mypy 2.3.1 環境再構築（B1–B7） | 1–2時間 |
| Phase 3 | ruff format 切り分け・整形（C1–C4） | 0.5–1時間 |
| Phase 4 | フル検証 `make verify`（D6） | 15–20分 |
| Phase 5 | フロントエンド検証（D7） | 5–10分 |
| **合計** | | **約5–8時間** |

---

## 7. チェックリスト（PR前）

- [ ] `alembic check` が exit 0
- [ ] `alembic upgrade head` / `downgrade -1` / `upgrade head` が成功
- [ ] mypy バージョンが `2.3.1` に固定
- [ ] Python 3.12 で `.venv` が動作
- [ ] `make typecheck` が fail-fast で止まらず、型チェックが実行される
- [ ] `make format-check` が 0ファイル未整形
- [ ] `make verify` が全体で緑
- [ ] `make frontend-test` / `make frontend-lint` が緑
- [ ] `docs/openapi.json` が最新（API変更後は `make openapi` で再生成）
- [ ] フロントエンド型同期 `npm run type:sync`（API変更後）
- [ ] `config/ci_lint_baseline.json` と `README.md` のベースライン行が一致
- [ ] `docs/` を変更したら `mkdocs build --strict` でリンクチェック
- [ ] ユーザー向け変更を `CHANGELOG.md` Unreleased セクションに追記

---

## 8. 参照ドキュメント

- `AGENTS.md` — リポジトリ固有の手順書（mypyピン、ラチェット、alembic、OpenAPI等）
- `CONTRIBUTING.md` — ブランチ・コミット規約（Conventional Commits）
- `Makefile` — `test`, `lint`, `typecheck`, `format-check`, `verify`, `test-migration` ターゲット
- `pyproject.toml` — バージョン SSOT（7.0.0）、mypy/ruff/coverage設定
- `config/ci_lint_baseline.json` — 静的解析ラチェット基準（ruff=0, mypy=450, format=0）
- `docs/architecture.md` — 4層アーキテクチャ
- `docs/STATUS.md` — 実装状況 SSOT

---

**本計画書の承認後、Phase 1 から順次実施すること。**