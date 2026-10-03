# AutoNovel v6.0.0 公開前最終監査レポート

監査日: 2026-10-03
対象: `main` @ `dc8c87a` + 未コミット修正（16ファイル）
手法: シニアQA による「デバッグ → 修正 → 検証」3サイクル + サブエージェント4名の並列監査

---

## 0. エグゼクティブサマリ

| 指標 | 監査前 (HEAD) | 監査後 | 差 |
|---|---|---|---|
| 失敗 | **150** | **133** | −17 |
| エラー | **12** | **9** | −3 |
| 成功 | 9,243 | 9,274 | +31 |
| **新規回帰** | — | **0 件** | **回帰ゼロを証明** |

### 発見された本番バグ（いずれも「公開全额NG」級）

| # | 場所 | 内容 | 影響 |
|---|---|---|---|
| B1 | `src/backend/routers/episodes.py:80` | 未定義名 `_verify_branch_belongs_to_book` を参照 | **チャ保存 API が全滅**（NameError→500） |
| B2 | `src/backend/routers/stream_writing.py:39` | 存在しない `uow.books.get_by_id` を呼び | **執筆 SSE API が全リクエストで即エラー** |
| B3 | `src/backend/database/repository.py` | `isawaitable` 判定 vs coroutine 必須 API の前提食い違い | 汎用 awaitable で TypeError/ValueError |

> B1・B2 は **モジュール import は成功する**ため既存テストも CI も検出できておらず、
> 実際に API を叩くまで表面化しませんでした。**チャ編集（Studio）と執筆保存（Wizard）が
> 本番で動作しない状態だった**重要な事実です。

### 未修正で報告のみ（今回スコープ外・要判断）

| 件数 | 内容 |
|---|---|
| 0 Critical / **3 High** | IDOR 2件 ＋ 認証バイパス警告欠落 |
| 4 Medium | 管理者API保護弱さ / NULL owner fall-through 3箇所 / メンバー照合 / POSTキー受領 |
| 7 テスト | 既存失敗（全て監査前から存在、回帰ではない） |

---

## 1. 監査前の状況整理

前フェーズでサブエージェント作業の撤回と検証を実施済みです。
本監査は **pristine な HEAD を基準**として独立に実施しました。

### 1.1 過去の副産物として処理済み
- 壊れた collection error ファイル（テストスイート全体 9,493件を起動不能にしていたもの）を削除
- 実行されない `.ts` テストファイル 6件（JS ランナーが root に存在せず死んでいた）を削除
- `pytest.ini` / `tests/conftest.py` / ベンチマーク基準値の未検証変更を revert

### 1.2 ベースライン取得（重要）
`git worktree add E:\autonovel_baseline HEAD` で pristine コピーを作成し、
同一コマンド・同一環境で修正前後を比較できる状態を作りました。
（作業ツリーには一切影響しない）

---

## 2. サイクル1：静的解析ゲートと F821 未定義名

### 調査
`ruff check src --select F821` が **1 件**ヒット。

```
F821 Undefined name `_verify_branch_belongs_to_book`
  --> src\backend\routers\episodes.py:80:15
```

### 根本原因
`episodes.py:10` が `verify_branch_belongs_to_book`（先頭 `_` なし）を import しているのに、
`upsert_chapter()` は `_verify_branch_belongs_to_book` と呼んでいた。
同じファイルの `delete_chapter`（119行）は正しく `verify_branch_belongs_to_book` を呼んでおり、
**80行だけの孤立した typo**。

### 検証（再現 → 修正 → 確認）
```
has verify_branch_belongs_to_book  : True
has _verify_branch_belongs_to_book : False   ← 実行時に NameError
```
- 参照は関数本体内にあるため **import は成功する** → テストもCI も検出不可
- `upsert_chapter` は Studio の章追加・編集・並び替えと Wizard の執筆保存が共通で使う
  → **主要ユーザー導線が全面的に 500**

### 修正
`src/backend/routers/episodes.py:80` を正しい名前に変更（1行）。

### 検証
- `ruff check src --select F821` → All checks passed
- 既存ファイル内の正しい用法（119行）との一致を確認

### 付随修正：lint ゲートと回帰テスト
監査OLAで判明した W292（末尾改行欠落）を修正：
- `tests/unit/backend/test_rate_limit_key_eviction.py`（**コミット済みの既存違反**。純整形）

新規リグレッションテスト：
- `tests/regression/test_no_undefined_names.py`（3 tests）
  - `ruff F821 == 0` をゲート化（サブプロセス隔離・`encoding="utf-8"` 明示）
  - `upsert_chapter` のガード参照を直接検査
  - **設計判断**: 「`_` 接頭辞の呼び出し」を正規表現で弾く案は**採用せず**。
    `collab.py:35` の `_verify_book_access` のように同一モジュール内の正当な
    プライベート関数があり誤検出になるため。ruff F821 はスコープを正しく解決する。

---

## 3. サイクル2：テスト基盤と環境の不具合

### 3.1 認証テスト3件（実装は正しく、テストがグローバル設定と衝突）

`tests/conftest.py:32` が `AUTH_DISABLED=true` を全テストに適用しています。
そのため「実際の認証経路を検証したいテスト」が short-circuit します。

| テスト | 症状 | 実装側の挙動 |
|---|---|---|
| `test_auth_jwt_security.py::test_auth_validate_api_key` | `False` を期待 → `"dev-key"` が返る | `auth.py:152-153` 検証前に dev-key |
| `test_cors_auth_headers.py` | 401 を期待 → 200 が返る | `auth.py:47-48` DB を参照せずモック返却 |
| `test_auth_real_session.py` | DB の user(id=101) を期待 → id=1 | 同上 |

**3件すべて**に `monkeypatch.setattr(settings, "AUTH_DISABLED", False)` を追加し、
検証対象の経路を確実に通すようにしました。実装は**1行も変更していません**。

> 注: 前フェーズで別エージェントが conftest の既定を `false` へ変更し 55 件を破壊しました。
> 本監査はそれを**行わず**、必要なテストだけを局所的に正する方式を選びました。

### 3.2 OpenAPI 仕様書の drift

```
app にあるが仕様に無い: ['/api/auth/refresh']
```

**重要な罠**を踏みました。`.env:32` が `APP_ENV=development` のため
`scripts/generate_openapi.py` を素朴に実行すると `/api/easy-mode/*` が含まれ、
`tests/conftest.py:29` が `APP_ENV=testing` で走るテストと必ず drift します。

**修正**: `APP_ENV=testing` を明示して再生成。
- `/api/auth/refresh` が追加
- 認証要件の `security: [OAuth2PasswordBearer]` 宣言漏れが 462 行分是正
  （= 公開される API 仕様が認証要件を示していなかった）

### 3.3 Windows CP932 エンコーディング（リグレッションゲート自体の死）

`test_status_md_counts_match_reality.py` が pytest を `subprocess.run(text=True)` で起動し
`encoding=` 未指定 → CP932 で `UnicodeDecodeError` → **计数ゲートが collection 不能で
黙って無効化**。修正: `encoding="utf-8", errors="replace"`。

**全 26 箇所の同種リスクが未特定**のため、ゲートは「pytest を起動する呼び出し」に絞って実装
（実証された故障モードのみを対象にし、git/docker/yaml の無関係な20箇所に機械変更を不强いる）。

新規: `tests/regression/test_subprocess_encoding_gate.py`（3 tests、検出能力の自己テスト含む）

### 3.4 未宣言のテスト依存

`test_emotional_residue_regression.py` が `fakeredis` を使用するが
`pyproject.toml` に宣言されておらず、クリーン環境では **setup ERROR で
リグレッションゲートが無効化**。→ `[dev]` に `fakeredis>=2.21.0` を宣言し導入。
結果、4件すべてが実行可能に（4 passed）。

---

## 4. サイクル3：残存不具合

### 4.1 本番バグ B3：coroutine と汎用 awaitable の取り違え

```python
# 修正前
if inspect.isawaitable(res):          # 汎用 awaitable を受理する判定
    loop.create_task(res)              # ← coroutine のみ受理 → TypeError
    # もしくは
    asyncio.run(res)                   # ← coroutine のみ受理 → ValueError
```
判定と実行で前提が食い違っていました。`AsyncMock` や独自 `__await__` で必ず例外。

**修正**: `_await_awaitable()` ヘルパーで coroutine へ正規化してから渡す。

**検証（挙動等価性の確認）**
- coroutine 経路: 例外処理・ログ・`RuntimeError` 分岐とも完全に等価（実行時実験で確認）
- 汎用 awaitable 経路: 従来は例外 → 現在は正常通過（受理範囲の拡大のみ）
- `test_backend_database_repository.py` → **20 passed**

### 4.2 本番バグ B2：SSE 執筆エンドポイント

既存テスト `test_stream_writing.py` の**期待するエラー**を追う過程で
`uow.books.get_by_id` が存在しないことが判明。

**根本原因の深掘り**: `BookRepository` が **2つ存在します**。
- `src/infrastructure/repositories/book.py` ← UnitOfWork が使用（`uow.py:20`）
- `src/backend/database/repository.py` ← 別クラス

誤った方を調べると `get_book_async` 等一系列が見つかり誤修正していた。
コードベースの既存慣習（`collab.py:43`, `export.py:72`, `branch_guard.py:26` すべて
`uow.books.get_book(book_id)`）に合わせて修正。

**このテストは最初は通りませんでした。** 作品行が無い・`AppContainer.db` が
Singleton で順序依存・FK制約の3重の問題があり、**`:

- 一時SQLite を `AppContainer.db` **provider override** で確実に束縛（順序依存を断つ）
- FK 制約を満たすため User 行も投入
- 診断メッセージを assert に付与

結果、**SSE 執筆エンドポイントが初めて実際に happy path を通ります**。

### 4.3 陳腐化したテスト（実装に追従）

| テスト | 実装の現状 | 対応 |
|---|---|---|
| `test_foreshadowing_registration_step.py` | `FS-001` 形式・プロット由来（`DUMMY-001` 前提は陳腐化） | モック階層を実装に一致、期待値を実測値で更新 |
| `test_plots_expand_beats.py` | Spine の beat 数に追従（12固定を廃止） | 固定値をやめ `resolve_spine()` から導出 |
| 同上（fallback） | LLM失敗は 502 に**意図的に**変更 | 契約を2本に分割（502 と JSON整形失敗時の縮退） |
| `test_openai_adapter.py` | SDK を遅延 import（モジュール属性なし） | patch 先を `openai.AsyncOpenAI` へ |
| `test_backend_background.py` | 基本 `StatusReporter` はログのみ（仕様通り） | Spy で `report()` 呼び出しを**厳密**に検証 |
| `anti_ai/test_integration.py` | import 欠落 | ファイル先頭へ移動 |

> `test_backend_background.py` は検証が**厳密化**しました
> （部分一致 → level 含むタプル完全一致。モジュールグローバル汚染も解消）。

> `test_plots_expand_beats.py` では削除した
> `assert "チート能力" in data[3]["outline"]` を、**実装に即した形で復活**しました
> （LLM プロンプトに `【チート度 (1-5)】4` が渡ることを検証）。

---

## 5. 回帰ゼロの証明

### 5.1 方法
`git worktree` で pristine な HEAD コピーを作成し、**同一コマンド・同一環境**で比較。
失敗ファイル集合を集合演算で突合。

```powershell
git worktree add E:\autonovel_baseline HEAD --detach
python -m pytest tests -q --tb=no --timeout=300 --continue-on-collection-errors --ignore=tests/load
```

### 5.2 結果
```
baseline files: 81  current files: 68
=== NEW failures (current only) ===
（空）
=== FIXED (baseline only) ===  13
```

**新規失敗ファイル = 0 件**。サブエージェントによる独立再計算でも
ノード単位（より厳しい粒度）で **0 件** と一致。

| 解消した13ファイル |
|---|
| `tests/integration/test_local_startup.py`, `tests/performance/test_fusion_perf.py`, `tests/regression/test_docs_router_count_matches_reality.py`, `tests/regression/test_lint_budget.py`, `tests/services/anti_ai/test_integration.py`, `tests/services/test_foreshadowing_registration_step.py`, `tests/unit/api/test_plots_expand_beats.py`, `tests/unit/backend/test_auth_real_session.py`, `tests/unit/backend/test_backend_background.py`, `tests/unit/backend/test_cors_auth_headers.py`, `tests/unit/routers/test_auth_jwt_security.py`, `tests/unit/test_openai_adapter.py`, `tests/unit/backend/test_rate_limit_key_eviction.py` |

### 5.3 整合性（副作用）
- テスト実行が開発データを書き換えていないことを `git status` で確認
- `tests/benchmarks/compression_baseline.json` と `templates/subtext/index.yaml` は
  テスト実行の副作用で書き換わる問題があるため、** reverted 済み**
- 作業ツリーに残るのは意図した変更のみ

### 5.4 src/ 3ファイル的安全性（独立レビュー結果）
| ファイル | 判定 | 根拠 |
|---|---|---|
| `episodes.py` | 安全 | 同一ファイル119行の正しい用法への統一のみ。旧コードは必ず NameError |
| `stream_writing.py` | 安全 | 他3路由と同一イディiomへの統一。旧コードは必ず AttributeError |
| `repository.py` | 安全 | 受理範囲の**拡大のみ**。coroutine 経路は例外処理・ログとも等価 |

---

## 6. サブエージェントによる並列監査結果

### 6.1 残存失敗の根本原因分析（4件）

| テスト | 分類 | リスク | 対応 |
|---|---|---|---|
| `test_filler_removal` | **製品起因** | **High** | 要修正（下記） |
| `test_foreshadowing_resolution_step`（6件） | テスト起因 | Medium | 要判断（削除/xfail） |
| `test_trim_all_pinned_cannot_reduce` | テスト起因（環境依存） | Medium | 要修正 |
| `test_async_wait_huey_result` | テスト起因 | Low-Medium | 要修正 |

**特筆すべき発見**:

**(a) `test_filler_removal` は本物の機能バグ**
`src/services/anti_ai/syntax_refiner.py:58` のフィラーパターンが先頭 `\s+` を必須要求します。
```python
re.compile(r"\s+(たぶん|おそらく|もしかしたら)\s*")
```
文分割されるため**文頭・読点直後のフィラーが必ず除去対象外**。実測:

| 入力 | 結果 |
|---|---|
| `たぶん、彼は…`（文頭） | 無変更 ❌ |
| `彼は、たぶん成功する。`（読点後） | 無変更 ❌ |
| `彼は たぶん成功する。`（半角スペース後） | 除去成功 ✓ |

さらに `「きっと」` はパターンに未登録。日本語ではフィラーは節頭に置かれることが多いため
**anti-AI 文体改善機能がほぼ無効**。公開後ユーザーから見える品質に直結。

**(b) `ForeshadowingResolutionStep` は一度も実装されたことがない**
`git log -S "ForeshadowingResolutionStep" -- src/services/pipeline_steps.py` は空。
`PHASE_1_IMPLEMENTATION_PLAN.md` に沿って書いた**未実装の赤テスト**が
`test_foreshadowing_resolution_step.py:2` で `ForeshadowingRegistrationStep as ForeshadowingResolutionStep`
と alias ことで import を通してしまい、別物（登録ステップ）を叩いている。

> **この偽の赤が (a) の本物の赤を隠しています。** 公開前に必ず解消すべき。

**(c) 圧縮テストは tiktoken 依存化に追随できていない**
`len(tiktoken.encode("F"*200))` = **25**。旧フォールバック（`len*1.5`）= 300。
テストが 300 をハードコードしているため前条件が成立せず空振り。
`Layer4SceneTrimmer` 自体に仕様変更はない。

**(d) Huey テストはデッドロックではない**
実メッセージは `Failed: DID NOT RAISE TimeoutError`（0.42秒で終了）。
素の `MagicMock` は `is_ready()` に常に truthy を返し、`get()` が None を返して
ループせず即終了する。モックが pending を模擬できていない。

### 6.2 セキュリティ監査

| 深刻度 | 件数 |
|---|---|
| Critical | **0** |
| **High** | **3** |
| Medium | 4 |
| Low | 2 |

**High #1: `AUTH_DISABLED=true` の起動時警告が存在しない**

多層防御は**機能しています**（実測）:
- `config.py:103` の既定は `False`（フェイルセーフ）
- `docker-compose.prod.yml` は `env_file` を使用しない（`.env` の値が注入されない）
- `config.py:126-127` は `APP_ENV=production` かつ `AUTH_DISABLED` 真なら起動拒否
- `_get_dev_mock_user()` は `role="admin"` なので、`AUTH_DISABLED=true` は
  認証無効化ではなく**認可の全面無効化**

したがって**標準デプロイ経路で本番バイパスは発生しません**。
残る穴は「警告が出ないこと」だけ。運用者が `.env` に `AUTH_DISABLED=true` を設定して
戻し忘れた場合、`APP_ENV` は `development` のままでバリデータに到達せず、
ログにもそれを示す行が1行も出ない。→ **発生検知不能**。
`server.py` の `lifespan` は LLM キー欠落には `logger.warning` を出すのに
認証無効化は（CORS の危険設定には [SECURITY WARNING] を出す慣例があるのに）入っていない。

**High #2: `POST /api/marketing/export_package/{book_id}` の IDOR**（ personally 確認済み）

```python
# marketing.py:50-60（POST）
async def export_package_post(book_id: int, req: MarketingExportRequest):
    await validate_api_key_or_raise(req.api_key)     # 空文字で素通り
    zip_data, _ = await engine.marketing.create_export_package(book_id)
    # current_user 依存なし、verify_book_ownership なし

# marketing.py:63-81（GET）
async def export_package_get(..., current_user: User = Depends(get_current_user)):
    await verify_book_ownership(book_id, current_user)  # ← こちらは正しく実装済み
```
同一ファイルの GET 版は正しく修正済みで、**POST 版だけが未修正**。
任意の認証ユーザーが `{"api_key": ""}` で任意の book_id を走査し、
**全作品の本文・世界設定・プロットを含む ZIP を一括取得できる**。

**High #3: `collab` コメントの resolve/delete に所有権検証なし**（ personally 確認済み）

```python
# collab.py:154 / :172
async def resolve_comment(comment_id: int, ..., current_user: User = Depends(get_current_user)):
    async with UnitOfWork(AppContainer.db()) as uow:
        n = await uow.collab.resolve_comment(comment_id, resolved)
    # _verify_book_access も verify_book_ownership も呼ばない
```
`comment_id` はグローバル採番で `comment_id -> book_id` を辿らない。
同ファイル他5ルート（65, 77, 91, 110, 130行）はすべて `_verify_book_access` を呼ぶが、
**この2つだけ脱落**。

**Medium 4件**:
- `system.py` の管理者API 13箇所が `require_api_key`（ロール未検証）で保護。
  `require_admin_user_or_key`（`api_readonly` に降格する実装済）が既に存在
- `user_id IS NULL` のとき所有者チェックが暗黙通過する独自判定が3箇所
  （`collab.py:51`, `publishing.py:33`, `orchestrated.py:194`）。
  `owner_guard.py:46-52` は NULL を明確に 403 で拒否する仕様だが、この3箇所は
  **別ルールの独自インライン判定**を使っている
- コラボメンバー認可が `display_name` / `email` の**文字列一致**
- `marketing.py` の POST 3経路が API キーを**リクエストボディ**で受領（GET版は修正済み）

**Low 2件**: `APP_ENV` 既定が `development` / `/docs`・`/openapi.json` が無認証公開

**否定的な確認（重要）**: 以下は**いずれも検出されなかった**
- `shell=True` / `os.system`: 0件（subprocess 51件すべてリスト形式）
- `pickle` / 非 safe `yaml.load`: 0件
- SQLインジェクション: `text()` への f-string 連結 0件
- パストラバーサル: `_safe_artifact_file_path()` が `resolve()` + containment 検証済み
- CORS `*` + `allow_credentials=True`: 併存せず（`config.py:306-315` が強制 False）
- ハードコード秘密: `.env` は `.gitignore:11` で除外、実鍵の git 管理下なし

---

## 7. リグレッションテスト計画

詳細は `QA_REGRESSION_TEST_PLAN.md` を参照。方針は4本柱:

1. **不具合クラスごとに1ゲート**（テストを大量に追加しない）
2. 実行時に死ぬ型は**静的ゲートで先に落とす**
3. **ゲートは自身の検出能力の自己テストを持つ**
4. **期待値は実装の権威ある源から導く**（ハードコード禁止）

### 実装済みゲート（3件）

| ファイル | 対象クラス | テスト数 |
|---|---|---|
| `test_no_undefined_names.py` | 未定義名の typo（ruff F821） | 3 |
| `test_auth_bypass_contract.py` | 認証バイパス契約（両方向） | 5（うち1 xfail） |
| `test_subprocess_encoding_gate.py` | Windows CP932 デコード事故 | 3 |

### 未着手のゲート（P0 提案）

| 提案 | 検出対象 | 手法 |
|---|---|---|
| collect 健全性ゲート | collection error による**ゲート自体の死**（fakeredis 事例） | `--continue-on-collection-errors` 付きで collection し ERROR=0 を assert |
| 未宣言依存ゲート | テストが import する第三者モジュールの宣言漏れ | tests/ の import を `pyproject.toml` の全 extra と照合 |
| repo メソッド契約ゲート | 存在しないリポジトリメソッド呼び出し（**B2 の再発防止**） | AST で `uow.<prop>.<method>` を列挙し、property の返却型のメソッド集合と照合 |
| awaitable 契約ゲート | coroutine/awaitable 取り違え（**B3 の再発防止**） | `_await_awaitable` 利用の強制 |

### 優先度
- **P0**: collect 健全性 → 未宣言依存 → repo メソッド契約 → awaitable 契約
- **P1**: 陳腐化期待値の原則運用 → easy-mode / security 宣言検査
- **P2**: `generate_openapi.py` の `--app-env` 化、`BookRepository` の重複定義解消

### 重要な運用知見
`scripts/generate_openapi.py` は `APP_ENV` を設定せず `.env`（development）で走るため、
生成とテスト検証で必ず drift します。**`APP_ENV=testing` を明示して生成する**手順を
計画書に規定しました（コード変更なしで解消可能）。

---

## 8. 既知の残存リスク（要判断）

### 8.1 認証リグレッションが検出できない（最重要）
`tests/conftest.py:32` の `AUTH_DISABLED=true` により、認証テストが無効化されています。
**真の解決には約55件の API テストへの依存オーバーライド移行が必要**で、単独では完了できません。
現状は `test_auth_bypass_contract.py` の **xfail** として可視化し、
修正されたら XPASS で通知される形にしました。

> 前フェーズで別エージェントがこれを行い 55 件を破壊しました。
> 本監査は意図的に**行わず**、必要最小限に留めました。方針決定は上位者へ委ねます。

### 8.2 `ForeshadowingResolutionStep` が未実装
453 行のテストが未実装機能を検証しています。実装するかテストを廃止するかは
**製品判断**が必要です。現状は偽の赤として本番品質を損ねています。

### 8.3 `BookRepository` の重複定義
`src/infrastructure/repositories/book.py` と `src/backend/database/repository.py` に
同名のクラスが存在します。誤った方を参照すると B2 のような AttributeError に
気づけず、もう一方は循環 import（`ImportError`）ächeになります。
**リポジトリ名の重複は根本原因を取り除いていない**ため再発余地があります。

### 8.4 `getattr` による動的ディスパッチ
静的解析では検出できない実行時到達不能コードが残存します。

---

## 9. 変更ファイル一覧

### 本番コード（3ファイル・3行の実質変更）
```
src/backend/routers/episodes.py       1行（未定義名 → 実在する関数）
src/backend/routers/stream_writing.py 1行（実在しないメソッド → 実在するメソッド）
src/backend/database/repository.py    +14行（_await_awaitable ヘルパー）
```

### 依存・仕様
```
pyproject.toml          fakeredis>=2.21.0 を dev に宣言
docs/openapi.json       APP_ENV=testing で再生成（refresh 追加・security 宣言 462行）
```

### テスト（既存 11ファイル修正 / 新規 3ファイル）
既存: conftest 依存の局所修正3件、`test_foreshadowing_registration_step.py`、
`test_plots_expand_beats.py`、`test_stream_writing.py`、`test_backend_background.py`、
`test_openai_adapter.py`、`test_cors_auth_headers.py`、`test_auth_jwt_security.py`、
`test_auth_real_session.py`、`test_rate_limit_key_eviction.py`、
`test_status_md_counts_match_reality.py`、`anti_ai/test_integration.py`

新規ゲート: `tests/regression/{test_no_undefined_names,test_auth_bypass_contract,test_subprocess_encoding_gate}.py`

### 成果物
```
QA_REGRESSION_TEST_PLAN.md   リグレッションテスト計画書
reports/qa_baseline_head.txt  HEAD ベースライン失敗一覧（worktree via）
reports/qa_final_failures.txt 修正後失敗一覧
```

---

## 10. 推奨する次のアクション

**公開阻害（要判断）**
1. High #2 の IDOR を修正（`marketing.py:50` に `current_user` 依存 + `verify_book_ownership` 追加）
2. High #3 の IDOR を修正（`collab.py:154,172` に所有権検証）
3. `AUTH_DISABLED` の方針決定（xfail のまま残すか、55件移行して真にDetection可能にするか）

**品質（推奨）**
4. `syntax_refiner.py` のフィラーパターン修正（anti-AI 機能がほぼ無効）
5. `test_foreshadowing_resolution_step.py` の削除 or xfail 化（偽の赤の解消）
6. `server.py` に `AUTH_DISABLED` の critical 警告ログを追加

**中期**
7. `BookRepository` の重複解消（同名クラスの存在自体が B2 の温床）
8. `collect` 健全性ゲート・未宣言依存ゲートの追加（P0）