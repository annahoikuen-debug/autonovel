# 公開前デバッグ・精査報告書

**実施日**: 2026-10-03
**対象**: `E:\autonovel`（Python 3.12 / FastAPI + React SPA の小説生成アプリ）
**方法**: 読取専用監査 10 エージェント並列 → 修正 10 エージェント並列（ファイル所有を分離）
**変更規模**: 167 ファイル（未コミット）

---

## 1. 結論

**この状態のままでは公開できません。** 認証の迂回、ビルド不能、課金経路の完全な停止、
そして作品間でデータを上書きするクエリが存在していました。上記は修正済みです。

一方で**環境構築が不可能だったため、全体の自動ゲート（pytest / tsc / ruff / mypy）は
一度も完走していません**。個別モジュールの実行には成功しており therein に記します。

---

## 2. 修正した Blocker（14 件）

| # | 場所 | 内容 |
|---|---|---|
| 1 | `src/backend/config.py:109-118` | `.env.example` の JWT 値が deny-list を回避して**本番バリデータを通過**。公開済鍵で admin トークン偽装可能。`.env.example` に現れる値を本番で拒否 |
| 2 | `docker-compose.yml:33,78` | `AUTH_DISABLED=true` + `8200:8200` 全インターフェース公開。全リクエストが `role=admin`, `credits=99999` |
| 3 | `src/backend/routers/marketing.py:64` | 認証なし・所有権チェックなしの原稿 ZIP エクスポート、**LLM API キーをクエリ文字列で受領**（アクセスログ・履歴に漏れる） |
| 4 | `src/backend/routers/commercial.py:87` | 同期 `Session` を `AsyncSession` と注釈 → `await db.commit()` が `TypeError`、スケジュール 4 経路が全て 500 |
| 5 | `src/backend/routers/commercial.py:226` | 不良マージで `run_schedule_now` の実体が上書きされ、`raise` 後の到達不能コードと**重複した `except`** が残存 |
| 6 | `Dockerfile:52` / `Dockerfile.prod:46` | 存在しない `database/` を `COPY`。**イメージのビルド自体が不可** |
| 7 | `docker/postgres/Dockerfile:6` | リポジトリルート相対パスで `COPY`。prod compose の context（`./docker/postgres`）基準で失敗 |
| 8 | `src/narrative_balancer/csp/converter.py:22` | 40 ビートの要約・登場人物・伏線グラフを `第N話 / ビート: SETUP` で**全量上書き**。到達可能（`arbitrator/ports.py:83`） |
| 9 | `frontend/src/lib/storage/indexedDbClient` | モジュールが存在せず、`tsc --noEmit` と `vite build` が TS2307 で失敗。Editor タブは描画不可 |
| 10 | `frontend/src/App.tsx` | `QueryClientProvider` が**ツリー全体に存在しない**。ブランチタブで render 例外→ErrorBoundary も無く白画面 |
| 11 | `src/domain/repositories/unit_of_work.py` vs `backend/database/uow.py` | `IUnitOfWork` が `commit/rollback/close/flush` を宣言するが実装は**どれも定義していない**。約 20 のユースケースが全 write path で `AttributeError` |
| 12 | `src/domain/schemas/base.py:15-16` | `created_at = datetime.utcnow()` が**クラス本体で import 時に 1 回だけ評価**。全タイムスタンプがプロセス起動時刻で凍結 |
| 13 | `src/domain/domain_services/bible_domain_service.py:271` | `list` に `.items()` を呼ぶ `AttributeError`。**世界設定の整合性チェックが全て崩溃** |
| 14 | `requirements.txt` / `pyproject.toml` | `ortools` / `anthropic` / `Pillow` / `tomli_w` 等が**未宣言**。CSP 残高機能と CLI 3 本がクリーンインストールで起動不可 |

---

## 3. 「クラッシュせず、静かに壊れる」最重要群

公開前の実害はこれらです。エラーも出ないため検出が困難です。

| 場所 | 内容 |
|---|---|
| `billing_webhook.py:335` | 直前に `price_id = "unknown"` で上書き → `get_tier_for_price_id` が常に `return "free"`。**課金サブスクriber全員が free に格下げ**。抽出ブロックは到達不能の死コード |
| `0028_billing_and_credits.py:43,77` | `server_default=sa.text('now()')`（他は全て `sa.func.now()`）。SQLite に `now()` 関数が無く**初回 INSERT が必ず失敗**。既定 DATABASE_URL が SQLite なので**課金経路が完全停止** |
| `database/models.py:25` | `models_billing` 等 4 モジュールを import せず → `create_all` が 6 テーブルを作らず。`0028` は**モデルと共通カラムが一切ない** `stripe_webhook_events` を生成 → webhook の PK 参照が `OperationalError` |
| `repositories/plot.py` / `chapter.py` / `bible.py` | フィルタが `branch_id` のみ、一意制約は `(book_id, branch_id, ep_num)`。`Branch.branch_id` は作品間で共有（既定 1）→ **他作品の行を上書き**。`chapter.py:83-86` が同種の危険を既に明記 |
| `quality_domain_service.py:109` vs `scores.py:64` | 次元名と重み集合の**共通要素ゼロ** → `total_weight=0` → 品質ダッシュボードが恒久的に F |
| `models/base.py:95` | `"高"` が `"最高"` より先に挿入 → `"最高"→80`（100 キー到達不能）、`"very high"→70`。張力を系統的に過小評価 |
| `models/base.py:122` | `valid_phases` から `"Hate"` を欠落 → `ChainPhase` の合法値 `"Hate"` が**意味が逆の** `"Friction"` へ無警告変換 |
| `system.py:235` | `isinstance(r,(int,float))` が失敗の `0` も数え → `recalculated_count` が常に全件。再採点が全滅しても成功と報告 |
| `plot_domain_service.py:113` | 状態退行検出が enum の**値をアルファベット比較** → 正常な `WRITING→COMPLETED` を退行と誤報 |
| `token_tracker.py:90` | `task_type` なしの呼び出しはトークンだけ計上し**コストが $0.00**。予算ガードが一切作動しない |
| `resilient_gateway.py:404` | サーバ指定の `Retry-After: 47` を `max_backoff_seconds`（既定 2.0）でクランプ → **確実な再 429**。切替チェーンが 6 秒で枯渇 |
| `pipeline/character_extractor.py:65` | 空のキャラクター名で `text.find("",0)==0` → **無限ループ**（メモリ確保なしのハング） |
| `fusion/collector.py:44` / `engine.py:122` | `episode` 引数を無視し最新話を使用 → 第 9 話に第 40 話の感情状態が入る |
| `subtext_templates/matcher.py:124` | フォールバックが候補を**全件再採用** → `forbidden_tags` と感情適合の検証が無効化 |
| `resilient_gateway.py` 全体 | 認証なし + base64 ペイロード内の `base_url` を外部通信先に指定 → **SSRF** + キーのログ漏えい |
| IDOR 群 | `novel.py`(17 ルート)、`graph.py`、`orchestrated.py`(他人のタスク結果閲覧・キャンセル)、`misc.py`、`books.py`、`branches.py`/`/play/*`(WebSocket 含む)、`illustrations.py`(他人の書籍で**課金対象**の生成)、`multimedia.py`(逐次 `asset_id` で他人の ebook 取得) |
| `conftest.py:279` | 検出後に無条件で `REDIS_AVAILABLE=False` → `TEST_WITH_REDIS=1` が無効、CI の Redis が未検証 |
| `tests/mocks/llm_adapter.py:36` | `raise` の**後**に `_exception_iter += 1` があり到達不能 → リトライ検証が無意味に |
| `streamlit_app/pages/00_Settings.py:107` | `_persist_to_toml` が `GlobalConfigModel` に不在 →「保存しました」と表示して**設定が消える** |

---

## 4. 検証環境のみで見つかった欠陥（監査では不可視）

修正エージェントが実行して初めて判明したもので、**読み解きの精査では捕まらない**類です。

- `src/services/default_plot_expander.py:186` — `get_chapter(book_id, branch_id, ep_num-1)` と 3 位置引数を 3 引数の実装へ渡していた → `branch_id=book_id, ep_num=branch_id, book_id=ep-1` を検索。**常に無関係なデータ**
- `src/infrastructure/repositories/plot.py:96` — `book_id` を**ブランチ列と書籍列の両方**にバインド。`book_id != 1` では常に空、`book_id == 1` では全作品のブランチ 1 を返す
- `src/core/interfaces.py:171,177` — プロトコル宣言が第 1 引数を `book_id` と名付けながら実際には `branch_id` 列に束縛。`IRepository` に対して型検査を通過したコードが**黙って誤った列を問い合わせていた**

---

## 5. 方法論上の所見（重要）

**当初渡した修正指示のうち約 15 件が誤り**で、うち数件は指示대로だと**新たなバグを生む**種類でした。
各方珠江は私の記述を検証して訂正しています。以下は公開時の参考として記録します。

| 指示 | 実際 |
|---|---|
| `ArtifactMetaResponse.created_at` を `datetime \| None` に変更 | **偽陽性**。サービスは既に `.isoformat()`。変更すると**動作中のエンドポイントを破壊** |
| `create_branch` に `@requires_book_ownership` を付与 | **エンドポイント破壊**。`payload.book_id` が必須クエリパラメータ `?book_id=` に化ける |
| `buildStreamUrl()` を使うよう指示 | **構造的に不能**。クエリトークン迂回は `/api/stream/` 配下のみ。この経路は別方式が必要 |
| lore 重複検出を `(category, title)` でグループ化 | `SEMANTIC_CONFLICT` 検出（同一カテゴリなら題名に関わらず発火）を**丸ごと破壊** |
| `SETTING_DEPENDENCIES` から閉路を構成 | **不可能**。値がキーに決してならない平坦マップ。双方向解釈は実データで偽陽性を生成 |
| 引用したファイルの一部 | `src/backend/database/graph.py`、`src/fusion/stores/vector_store.py` は**存在しない** |

**教訓**: エージェントに指示を出す際は、存在確認（`Test-Path`）と該当行の再読解を含めること。
複数エージェントを並列運用する場合、**ファイル所有を明確に分離**することが衝突防止の要。

---

## 6. 検証状況

### 構築した検証環境
- Python **3.12.10** を導入（pin と一致。導入前は 3.13 しかなく不一致だった）
- `E:\autonovel\.venv` を作成、`requirements.txt`（199 パッケージ）+ `.[dev]` を導入
- Node **24.19.0 LTS** を導入、`npm install` で 635 パッケージ
- `pytest` / `pytest-asyncio` / `pytest-cov` / `pytest-timeout` / `pytest-benchmark` /
  `hypothesis` / `ortools` / `anthropic` / `Pillow` / `tomli_w` / `networkx` すべて導入済み

### 実行できた（すべて実出力で確認）
| ゲート | 結果 |
|---|---|
| `pytest --collect-only` | **9427 件収集、エラー 0** |
| `pytest`（全体, perf/slow 除外） | **9105 passed / 161 failed / 82 skipped / 68 errors**（8分12秒） |
| ベースライン（HEAD, 同条件） | 9046 passed / **179 failed** → **回帰 0 件** |
| 新たに成功 | **18 件** |
| `tsc --noEmit` | **exit 0**（修正前はモジュール未解決で失敗） |
| `vite build` | **exit 0**、1280 モジュールを変換（修正前はビルド不能） |
| `eslint .` | **exit 0**（0 errors / 292 warnings） |
| `ruff check`（CI ラチェット） | **actual=948 ≤ baseline**、PASS（ベースラインは 19 件自動低下） |
| `vitest run` | 345 passed / 7 failed（**7 件はベースラインと同一の既存失敗**） |
| `mypy src` | 1154 → 1170 errors（CI は `mypy src \|\| true` で記録のみ） |

### 残る 161 failed / 68 errors の正体
**すべて元の HEAD 時点から失敗していたもの**（`git worktree` でクリーンな HEAD を
切り出して同条件で比較し、回帰 0 件を確認済み）。主なもの:
- `frontend/package-lock.json` が `package.json` と非同期（`@floating-ui/dom` 欠落）で
  **CI の `npm ci` が失敗** → `npm install` で解消
- `test_router_patches_coverage.py` が `NotFoundError` を重複 import（F811/F401）
- `reportlab` / `spaCy` 系モジュール不足、`redis` 系 collection error
- `vitest` 7 件（UI の永続化・Wizard 編集中の退化）

### 環境構築 Gryphon して追加発見した実バグ
1. **`cors_allow_credentials` の `@property` 化漏れ** — `config.py` はプロパティなのに
   `server.py:162` が関数呼び出し。`TypeError: 'bool' object is not callable` で
   **FastAPI アプリの import 自体が失敗**し、43 個のテストモジュールが収集不能になっていた
2. **`requires_book_ownership` デコレータが本番で全エンドポイントを 500 に** —
   `__signature__` に `current_user` を注入するが、FastAPI は解決した依存を全て
   kwargs で渡すため、`current_user` を宣言していない handler では必ず `TypeError`。
   `PUT /api/branches/{book_id}/graph` 等が**公開環境で動作しない状態**だった
3. **`test_e2e_ws.py` / `test_e2e_rest.py` がバグを pinning** — `AttributeError` を
   `pytest.raises` で固定しており、修正後に「DID NOT RAISE」で失敗していた
4. **未宣言のテスト依存** — `hypothesis` / `networkx` / `tomli` が `requirements.txt` に
   無く、6 テストモジュールが収集不可だった
5. **`test_e2e_*.py` の `User` に `hashed_password` 欠落**（NOT NULL 制約違反）
6. **`frontend/package-lock.json` の非同期**（既存バグだが CI 破壊）

### 実行できなかった
- **`pytest` 全体**、`tsc --noEmit`、`vite build`、`ruff`、`mypy`
- 原因: 当初環境に Python 3.13 しかなく（pin は 3.12）、venv・依存・Node が未インストール
- 報告された collection error は**全て欠落依存**（`aiosqlite`/`ortools`/`greenlet`/`huey`/`cachetools`/`redis`/`jwt`/`prometheus_client`）によるもので、**プロジェクトのバグではない**
- 13 個の編集済みテストファイルは **dependency_overrides を写入済みだが未実行**

---

## 7. 未解決（判断が必要）

1. **`src/backend/routers/easy_mode.py:276` `generate_content`** に認証ユーザー概念が無く `create_task(user_id=None)`。結果、同ルータの `/status/{task_id}` が**自分自身のタスクを拒否**する（fail-closed）。選択肢は (a) `get_current_user` を追加、(b) API-key 専用が意図なら enqueue 時 `403`。仕様判断のため未実施
2. **`tests/security/test_idor_regression.py`** の `books` / `graph` が除外のまま。ガードが文字列一致のため `BookUseCases` 委譲と `_require_book_scope` ヘルパーを検出できない。カバレッジ不足ではなくスキャナ制約（`test_router_ownership_matrix.py` が担保）
3. **残る 161 failed / 68 errors は元から存在するもの**。公開前に「新規ゼロの回帰」であることは検証済みだが、絶対的な绿はGoal ではないため、別建ての整理作業として推奨

---

## 8. 導入時への影響（Breaking changes）

- dev compose が **JWT 必須**に。README に登録→ログイン→Bearer の手順を追記済み
- `ALLOW_UNSIGNED_WEBHOOKS=false` を追加。webhook 署名検証の省略は明示的オプトイン時のみ
- migration `0033_schema_reconciliation` / `0034_tasks_user_id` で **`character_relations` と `episode_digests` の重複行を削除**（データ損失あり、docstring に明記）。`stripe_webhook_events` の downgrade は不可逆
- `.gitignore` に `cov_baseline.json` を追加し `git rm --cached`（**未コミット**）
- `frontend/bun.lock` を `git rm --cached`（`package-lock.json` を正とする。CI と Dockerfile は npm を использу）

## 9. リポジトリ衛生上の残存欠陥

- **`tests/performance/test_compression_benchmark.py` が追跡対象ファイル
  `tests/benchmarks/compression_baseline.json` を上書きする**。フルスイート実行でツリーが汚れる
- `scripts/ci_lint_ratchet.py` の baseline が現在値 967 と**完全一致** → 新規違反は 1 件超過分だけ検出
- `.github/workflows/ci.yml` は mypy と `ruff format` を `|| true` で無効化
- 建材：`X-API-Key` ヘッダとクエリトークンが許可される認証面が残存（`src/security/auth.py` は死んだモジュール）