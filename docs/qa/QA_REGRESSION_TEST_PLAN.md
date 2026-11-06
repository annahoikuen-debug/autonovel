# リグレッションテスト計画書（AutoNovel）

作成者: シニアQAエンジニア / 対象: 公開前監査で発見された 8 件の不具合クラスの再発防止
最終更新: 2026-10-03

---

## 1. 目的と方針

### 1.1 目的
本計画書は、公開前監査で実際に発見・修正した不具合が **再発して CI が緑のまま本番で壊れる** ことを防ぐ。
対象は「テスト数を増やすこと」ではなく、**壊れたときに必ず落ちobarrier（ゲート）を1つずつ定義すること**にある。

### 1.2 方針（4本柱）

| # | 方針 | 内容 |
|---|------|------|
| A | **不具合クラスごとに1ゲート** | 8 クラスそれぞれに「そのクラスが再発したら必ず落ちる」ゲートを1つだけ割当てる。徵候ごとのテストを量産しない。同一観測点への二重実装は禁止。 |
| B | **実行時より静的を先** | import は成功するが実行時に死ぬ型（F821 参照、存在しないメソッド、awaitable 取り違え）は、どちらも静的解析で機械的に検出可能。実行時にtrapさせるな、**AST ゲートで落とす**。 |
| C | **検出手段自体の自己検証** | ゲートは必ず「既知の違反パターンを実際に検出できること」を 1 テスト持つ（`test_subprocess_encoding_gate.py::test_gate_detects_the_known_offender_pattern` が模範）。無条件に通るゲートは無価値。 |
| D | **期待値は実装の権威ある源から導く** | ハードコードした数値・ID 形式・件数をテストに埋め込まない（不具合クラス 6 の直接原因）。仕様はコード／`pyproject.toml`／実際の app から機械的に取得する。 |

### 1.3 既に実装済みのゲート（再設計・重複作成禁止）

以下 3 ファイルは**内容確認済み**。本計画書では「既存で充足」と明記し对这些の代替品を作らない。

| ファイル | 役割 | カバーするクラス |
|---|---|---|
| `tests/regression/test_no_undefined_names.py` | ruff F821 ゲート（subprocess 隔離・`encoding="utf-8"` 明示）+ `upsert_chapter` のガード参照検査（`hasattr(m,"verify_branch_belongs_to_book")` / `inspect.getsource` で `_verify_branch_belongs_to_book` 禁止・正しい呼び出しの存在確認） | クラス1（未定義名） |
| `tests/regression/test_auth_bypass_contract.py` | `AUTH_DISABLED=True` → dev モックを返す／`False` → 401 と `validate_api_key_sync(...) is False`。加えて `tests/conftest.py` を AST で読み `os.environ.setdefault("AUTH_DISABLED", ...)` を列挙し、`=true` なら `pytest.xfail` で既知リスク可視化 | クラス4（認証設定とテストの衝突） |
| `tests/regression/test_subprocess_encoding_gate.py` | `tests/**/*.py` の `subprocess.{run,check_output,check_call,Popen}` を AST で列挙し、pytest 起動astringshort-circuit（`text=True` かつ `encoding=` なし）ostatic検査。ゲート自身の検出ロジックを検証する自己テスト付き | クラス5（Windows CP932） |

---

## 2. 不具合クラスごとの回帰テスト計画

| # | クラス | 再発モード（何がどうずれると再発するか） | 追加すべきテスト | テスト種別 | 検証コマンド | 実装状態 |
|---|--------|------------------------------------------|----------------|-----------|--------------|---------|
| 1 | 未定義名の typo（F821） | 関数本体内の `_verify_*` のような 1 文字差の参照 typosagain。import は成功 → 実行時に NameError → 500 | **既存で充足**（`test_no_undefined_names.py`: ruff F821 + `upsert_chapter` ガード）。加算enda ルール: **新モジュール追加時は必ず `ruff check src --select F821` を local でも回す**（pre-commit 化は §4） | 静的解析ゲート | `python -m pytest tests/regression/test_no_undefined_names.py -q` / `python -m ruff check src --select F821` | **実装済み** |
| 2 | 存在しないリポジトリメソッド呼び出し | `uow.<repo>.<method>` のメソッド名が別クラス（`src.infrastructure.repositories.book` と `src.backend.database.repository` の 2 つの `BookRepository`）を前提に書かれる。UnitOfWork が使う側を実装者が取り違える → AttributeError → SSE が全リクエストで死 | **新規**: `tests/regression/test_repository_method_contract.py`（設計は §3.1）。 UnitOfWork の各 repository プロパティの返却型クラスから実メソッド集合を機械取得し、`src/backend/routers/**` の `uow.<prop>.<method>` 呼び出しと照合 | 静的チェック（AST） | `python -m pytest tests/regression/test_repository_method_contract.py -q` | **未着手（提案 P0）** |
| 3 | coroutine / 汎用 awaitable の取り違え | `inspect.isawaitable()` 真だが `loop.create_task()` / `asyncio.run()` は coroutine 限定。`AsyncMock` や独自 `__await__` で TypeError/ValueError。`src/backend/database/repository.py:170` `_safe_commit()` / `:191` `_safe_refresh()` が該当箇所 | **新規（2点）**: (a) 振る舞いテスト `test_await_awaitable_contract.py` — 独自 `__await__` / `AsyncMock` を渡して `TypeError`/`ValueError` が出ないこと、(b) linter 風ゲート — `_await_awaitable` の外围で `create_task`/`asyncio.run` に未正規化 awaitable を渡さない（§3.2） | 契約テスト + 静的チェック | `python -m pytest tests/regression/test_await_awaitable_contract.py -q` | **未着手（提案 P0）** |
| 4 | 認証設定とテストの衝突 | `tests/conftest.py:32` が `AUTH_DISABLED=true` を全局適用 → 認証検証テストが short-circuit。`validate_api_key_sync("invalid-key")` が `"dev-key"` を返す等 3 件が構造的に成立しない | **既存で充足**（`test_auth_bypass_contract.py`。両方方向の契約を monkeypatch で固定し、conftest の既定倒退は xfail で可視化）。残る真の解決（認証有効が既定 + 約 55 件への依存オーバーライド移行）は §6 の残存リスクとして管理し、本計画では**新規ゲートを作らない** | 契約テスト | `python -m pytest tests/regression/test_auth_bypass_contract.py -q` | **実装済み（真の解決は未着手・§6）** |
| 5 | Windows CP932 エンコーディング | `subprocess.run(..., text=True)` の `encoding=` 漏れで pytest 出力（UTF-8）を CP932 でデコード失敗 → **リグレッションゲートが collection 不能になり黙って無効化** | **既存で充足**（`test_subprocess_encoding_gate.py`）。補足運用: 追加で `pytest.ini`/CI に `PYTHONUTF8=1` を設定し、Windows でも全 subprocess の既定を UTF-8 に寄せる（多層防御） | 静的チェック | `python -m pytest tests/regression/test_subprocess_encoding_gate.py -q` | **実装済み** |
| 6 | 陳腐化したテスト | 実装変更（`FS-001` ID 形式、`resolve_spine` ベース話数設計、LLM 失敗時 502 化）にテストが追随せず失敗。またはテストが **期待値をハードコード**liner，导致下次変更で誤検知 | **新規（原則の明文化 + 機械化）**: (a) 方針 1.2-D を本節に明文化、(b) ハードコード ID 書式のゲート `test_stale_expectations.py` — `FS-` 系 ID をリテラル `r"FS-\d{3}"` として列挙している箇所を列挙し、正規表現クラス或は生成関数から導いていることを確認（§3.3） | 静的チェック | `python -m pytest tests/regression/test_stale_expectations.py -q` | **未着手（提案 P1）** |
| 7 | 未宣言のテスト依存 | テストが import する第三方モジュールが `pyproject.toml` の dev/nlp extra に宣言されていない → クリーン環境で setup ERROR → **リグレッションゲートが無効化**（`fakeredis` の事例。`pyproject.toml:89` に追加済み） | **新規**: `tests/regression/test_test_dependencies_declared.py`（§3.4）。`tests/**/*.py` のトップレベル import を収集し、`importlib.metadata` で installed / `pyproject.toml` の `[project.optional-dependencies]` で宣言済みを照合 | 静的チェック | `python -m pytest tests/regression/test_test_dependencies_declared.py -q` | **未着手（提案 P0）** |
| 8 | 仕様書の drift | `docs/openapi.json` に `/api/auth/refresh` が無い・`security` 宣言漏れ。または生成と検証で `APP_ENV` が食い違い、**必ず drift する**（§3.5） | **既存で充足**: `test_docs_router_count_matches_reality.py::test_openapi_json_has_no_path_drift_against_the_app` が app の route 集合と仕様を両方向比較。`security` 宣言の検査と APP_ENV 一致手順は本計画で追加する運用規定のみ | 静的チェック + 運用手順 | `python -m pytest tests/regression/test_docs_router_count_matches_reality.py -q` | **実装済み**（APP_ENV 手順のみ本計画で規定） |

---

## 3. 未着手のゲートの具体設計

### 3.1 存在しないリポジトリメソッド呼び出し（クラス2）

**なぜ ruff では足りないか**: F821 は「モジュール/ローカルスコープで未解決の名」を見るだけで、`AttributeError` 相当（型に対して存在しない属性）は対象外。`uow.books.get_by_id()` の `get_by_id` は識別子としては書けているため F821 も mypy の緩い設定も通過する。

**アプローチ（UnitOfWork プロパティ型との照合）**:

1. `src.backend.database.uow.UnitOfWork`（UnitOfWork が実際に使う実装、`:92-161` に各 `@property` がある）を **import して** `dir(UnitOfWork)` から `books` / `chapters` / `characters` / `branches` / `bible` / `plots` / `misc` / `rules` / `audit` / `book_scores` / `prompt_versions` / `illustrations` / `collab` / `cost` などを列挙。
2. 各プロパティに `inspect.getattr_static` または `typing.get_type_hints` を使い、返却型クラス（例: `books -> BookRepository`）を解決。
3. 各クラスから `inspect.getmembers(cls)` でメソッド集合を取得（`_` で始まる内部属性と `is_async` など property は呼び出し候補から除外）。
4. `src/backend/routers/**`（および `src/` 全体）を AST で走査し、`uow.<prop>.<method>` 形式の `ast.Attribute` チェーン（value が `ast.Attribute(attr="uow")`）を収集。デプロイト行程で `getattr(uow, ...)` の文字列渡す動的解決がある場合は `stringmode` の_literals__` を別途対象外として明示。
5. プロパティ名が UnitOfWork に無い／メソッドがその型に無い ＝ 違反。**モジュール名単位ではなく `file:lineno` 単位で違反を列挙**して CI を落とす。

**自己検証（方針C）**: 最小の文字列例 `uow.books.definitely_missing_method` をゲート関数に通し、違反として検出されることを 1 テストで固定する。

**運用上の注意**: `BookRepository` が `src/infrastructure/repositories/book` と `src/backend/database/repository` の 2 つ存在する問題そのものへのゲートéntリ。omalously、**UnitOfWork が import している側だけを権威にする**（動的 import 解決）ことを docstring に明記する。

**任意（P2）**: `BookRepository` の重複定義自体を検出するゲート（同一クラス名の定義が複数モジュールにある場合は警告）。ただし「2 つを一気に 1 つに畳む」破壊的リファクタの是非は本計画の範囲外。

### 3.2 coroutine / 汎用 awaitable 取り違え（クラス3）

**(a) 契約テスト（振る舞い）** — `tests/regression/test_await_awaitable_contract.py`
- `AsyncMock()`（coroutine 風） / `AsyncMock(spec=lambda: None)` / `__await__` のみ実装した自前クラスを `_await_awaitable()` に渡し、**完了すること**（`TypeError`/`ValueError` が出ないこと）を確認。
- 実行が前提の判定ロジックを直接単体検証する: `inspect.isawaitable(x) is True` かつ `asyncio.iscoroutine(x) is False` のような入力で、**旧実装（`loop.create_task(x)` 直呼び）は落ちる**ことを最小コードで再現し、修正後は通ることを確認。
- この契約は「Future/Task は渡せない」「coroutine は渡せる」の境界も 1 件ずつ固定する。

**(b) linter 風ゲート（静的）** — `tests/regression/test_await_helper_usage.py`
- `src/` を AST で走査し、`loop.create_task(` / `asyncio.run(` / `ensure_future(` の引数が「そのままの `.commit()` / `.refresh()` / `.execute()` の戻り値」で、`_await_awaitable(...)` で包まれていない箇所を検出。
- 検出条件は「呼び出し属性が `create_task`/`ensure_future`/`run` かつ、その引数が `_await_awaitable` 呼び出しでない」。一致したら `file:line` を列挙して落とす。

**Assertions について**: `isawaitable` の誤用は「警告ログだけ出して fire-and-forget で commit する」性质的であり、ログ出力のアサートではなく**意味的に commit が完了erioAcknowledged に称之为** `session.commit()` の呼ばれ回数（fake session なので数えれる）＋例外tegrity の 2 つで固定する。

### 3.3 陳腐化したテスト（クラス6）

**原則の明文化（この計画書の規程として本文に明記する）**:

1. **期待値はハードコードしない。** テストがアサートする ID 形式・件数・話数・ステータスコードは、実装（定数・リポジトリメソッド）または `pyproject.toml` / `docs/` から **実行時に取得**する。定数の場合:「リテラル定数の宣言側」をgate の対象とする（宣言側だけを単一ソースにする）。
2. **一个新機能には必ず「新機能将通过する behavior テスト」を同时追加し、** behavior テストは「固有名 API（例: `resolve_sine`）」を呼んで結果の形（型・範囲・意味）を確認する。
3. **期待値を変更するときは、実装 diff とテスト diff を同一 PR でレビューする。** テストの期待値だけを機械的に合わせる commit を禁止する。

**ゲート（P1）**: `tests/regression/test_stale_expectations.py`
- `tests/**/*.py` 内で `r"FS-\d{3}"` のような ID 書式がリテラル直書きされた箇所を AST で列挙する。
- 正規表現クラス（`[FS]-\d+`）または生成関数（`next_id()` 等）から導いている箇所は「合格」。リテラル直書きのうち、正規表現クラスでも生成でもないものだけ objet.
- 本ゲートは「直書き自体」を禁止するのではなく、**ID 書式の正準が 2 箇所以上に存在すること**だけを禁止する（同じリテラル文字列が `src/` と `tests/` の両方に hardcode されているケースを検出）。

### 3.4 未宣言のテスト依存（クラス7）

**ゲート**: `tests/regression/test_test_dependencies_declared.py`

1. `tests/**/*.py` を AST で walk し、`ast.Import` / `ast.ImportFrom` でモジュールルート名のみを収集（`from foo import bar` は `foo`）。
2. シャドー Variable / ローカル定義モジュールの誤検出を避けるため、`tests/` 内のローカルモジュール名（`tests/` 配下のBasename）と `conftest` は集合から除外。
3. **宣言済みを `pyproject.toml` の `[project]`(dependencies) + `[project.optional-dependencies]` の全 extra（`dev` / `rag` / `nlp` / `observability` 等）から import 名（`-` → `_` 変換、`casefold`）.Collect。
4. **installed を `importlib.metadata.packages_distributions()` で取得し、** 「installed なのに宣言なし」のみ違反とする（宣言済みだが未インストールは「当該 extra 入れていない」ので違反にしない）。
5. 出力は `module — used in file:line` 形式で列挙。**gate 自身は `fakeredis` を使う。故に `pyproject.toml:89` の宣言が存在することが前提**（既に追加済み）。
6. **自己検証**: テスト内に「宣言されていない架空モジュール」を 1 つ書き込む（例 `definitely_undeclared_pkg_xyz`）、検出されることを確認。

**付随ゲート（silent setup ERROR の検出、P1）**: `tests/regression/test_regression_collects_cleanly.py` — `pytest --collect-only tests/regression -q` を `encoding="utf-8"` 付きで subprocess 実行し、`ERROR` / `ModuleNotFoundError` が 0 件であることを確認。**クラス5・7 の「ゲートが黙って無効化される」モードそのものを直接检测する**。

### 3.5 仕様書 drift（クラス8）— APP_ENV の一致手順（重要）

**罠の正体（コードで確認済み）**:

- `src/backend/server.py:192-193` — `if settings.APP_ENV == "development": app.include_router(easy_mode.router, prefix="/api/easy-mode", ...)`。**`/api/easy-mode/*` は `APP_ENV=development` のときだけ mount される。**
- `scripts/generate_openapi.py` は `APP_ENV` を一切設定していない → `.env:32` の `APP_ENV=development` が読み込まれ → **`/api/easy-mode/*` を含む仕様書を生成する。**
- 一方 `tests/conftest.py:29` は `os.environ.setdefault("APP_ENV", "testing")` → テスト実行時は `APP_ENV=testing` → **`/api/easy-mode/*` を含まない app** compares になる。

このため **「生成（development）」と「検証（testing）」が必ず食い違い、`test_openapi_json_has_no_path_drift_against_the_app` が毎回失敗する**。これはテストのバグではなく**手順のバグ**。

**解決手順（明文化・コード変更なしで運用規定として定着させる）**:

1. 仕様の生成と検証は **同一 APP_ENV** で行う。推奨: いずれも `APP_ENV=testing` で揃える（CI と一致させる）。
   - 生成: `APP_ENV=testing python scripts/generate_openapi.py` （PowerShell: `$env:APP_ENV="testing"; py scripts/generate_openapi.py; Remove-Item Env:APP_ENV`）
   - 検証: `python -m pytest tests/regression/test_docs_router_count_matches_reality.py -q`（conftest が `testing` を setdefault）
2. **`.env` の `APP_ENV=development` に依存させない。** 開発者が素で `py scripts/generate_openapi.py` を叩くと必ず development になる。**`generate_openapi.py` の冒頭で `.env` 読み込み前に `APP_ENV` を `testing` に setdefault する**（または `--app-env` オプションを追加）を **P2 のコード変更タスク** として起票する（本計画ではコード変更しない）。
3. **short 版的 gate（P1、コード変更不要）**: テスト側に「仕様書に `/api/easy-mode` が含まれるなら `settings.APP_ENV == "development"` であることを確認し、development である場合に `xfail`/警告する 1 テストを追加する。→ **drift sto 不整合 habilita な ら「生成侧误用了 .env」を検出できる。**

**追加すべき drift 検査（P1）**:
- `security` 宣言検査: `docs/openapi.json` の認証保護されたパスに `security`（または operation レベル `security`）が宣言されていること。`/api/auth/refresh` のような**公開パスは `security: []`（意図的に公開）と明示**されていること。「黙って認証 Stevie が落到してない」ことを可視化。
- パス単位の `security` 検査により「bulk で `security` を付ける」「付かない」の両方の事故を検出。

---

## 4. CI 統合方針

| ゲート | 実行段階 | 理由 |
|---|---|---|
| `test_no_undefined_names.py`（F821） | **pre-commit（left）+ PR CI の最速段** | ファイル 1 つの typo で CI 数分を待たすべきでない。pre-commit で `python -m ruff check src --select F821` を走らせれば commit 時に即検知。pre-commit 未導入なら PR CI の job 1 番（`lint` job）に分離し、テスト job と並列実行 |
| `test_subprocess_encoding_gate.py` | **pre-commit** | 1 ファイル完結・高速・機械的。pre-commit でOK |
| `test_test_dependencies_declared.py`（クラス7） | **PR CI（`lint` job 内、並列）** | pyproject を読むだけなので高速。CI の clean 環境で意味を持つ |
| `test_regression_collects_cleanly.py`（クラス7 の silent-ERROR 版） | **PR CI（テスト job の前段）** | 他の回帰ゲートの実行可否自体を保証するため、**最も先に回す** |
| `test_repository_method_contract.py`（クラス2） | **PR CI**（fast なので） | app 全体を import する可能性があるため、`lint` より後の専用 job。却在時は `ruff`/mypy では出ないため**必ず独立 job として存置させる** |
| `test_await_awaitable_contract.py` + usage ゲート（クラス3） | **PR CI** | 依存最小。既存 unit の年检 |
| `test_auth_bypass_contract.py`（クラス4） | **PR CI**（常に） | xfail が常態化しても「追跡されている既知リスク」として CI に可視。XPASS（誰かが conftest を修正した）が検出される |
| `test_docs_router_count_matches_reality.py`（クラス8） | **main ブランチ push 時のみ**（PR では任意） | `docs/openapi.json` の再生成は「コードを全部 написа終わってから一度」。PR ごとに回すとノイズが大きい。ただし `version` チェックと `security` 宣言チェックは軽量なので PR でも可 |
| 全回帰スイート | **main / リリース前**（`pytest -m integration`） | 遅いが確実 |

**推奨 job 構成（概念図）**:

```
[lint job]        ruff check src --select F821 → test_no_undefined_names (部分)
                  test_test_dependencies_declared
[collect-guard]   test_regression_collects_cleanly   ← 最初に回す
[fast tests]      unit tests
[contract tests]  test_repository_method_contract / test_await_awaitable_contract /
                  test_auth_bypass_contract / test_stale_expectations
[integration]     pytest -m integration
[docs-drift]      test_docs_router_count_matches_reality  ← main のみ
```

**Fail 時の扱い**: 静的ゲートの失敗は**テスト失敗と同じ扱い**（赤）で merge block。ただし「ゲート自体の誤検出（false positive）」だと判断された場合は、`# gate: known-false-positive <URL>` コメントで明示的に skip し、issue を紐付ける（黙って skip しない）。

---

## 5. 実行順序と優先度

| 優先度 | ゲート | 理由 |
|--------|--------|------|
| **P0** | ① `test_regression_collects_cleanly.py` | 他のすべてのリグレッションゲートの「実行可否」を保証する土台。クラス5・7 の「黙って無効化」を直接検出。他のゲートを作る前にこれがないと意味がない |
| **P0** | ② `test_test_dependencies_declared.py` | P0 ゲート 1 と対になる。「モジュールが見つからない→ゲートが無効」を防ぐクラス7。未宣言依存は一度発生すると**クリーン環境で gate が丸ごと死ぬ** |
| **P0** | ③ `test_repository_method_contract.py` | クラス2 は**実際に EPUB の SSE エンドポイント（stream_writing）を完全に殺していた**高azzo度 bug。F821 でも mypy（緩い設定）でも出ないため、専用ゲートが必須 |
| **P0** | ④ `test_await_awaitable_contract.py` + usage ゲート | クラス3 は commit がサイレントに失敗する可能性があり（警告ログだけ出て**反映されない**）、**サイレントなデータ破損**につながる。契約＋静的の両方必要 |
| **P1** | ⑤ `test_stale_expectations.py`（クラス6） | 実害は既に顕在化しており、CI の赤で 드러かるため**緊急性は P0 より低い**。ただし原則の明文化（本文 §3.3）はすぐに行う |
| **P1** | ⑥ `/api/easy-mode` の development 依存検出 + `security` 宣言検査（クラス8） | ステップ8 の drift の真因。**コード変更なしで短期内に対応できる**（1 テスト追加） |
| **P2** | ⑦ `generate_openapi.py` の `--app-env` オプション化 | 根本解決だがコード変更が必要。P1 の検出テストを足せば「少なくとも気付けられる」状態になるため後回し可 |
| **P2** | ⑧ `BookRepository` 重複定義の検出ゲート | クラス2 の**根因**への言及。ゲート化しなくても P0-③ の実行時に気付けられる |
| **P0** | クラス1・4・5（既存ゲート） | **既に充足**。追加実装不要。pre-commit/CI への組み込みのみ |

---

## 6. 既知の残存リスク（現在、検出手段が無い／限界的のもの）

| # | リスク | 現状 | 真の解決に必要な作業 | 影響度 |
|---|--------|------|---------------------|--------|
| R1 | **`AUTH_DISABLED=true` による認証テストの無効化**（クラス4） | `test_auth_bypass_contract.py::test_conftest_default_is_auth_enabled` が **xfail** で可視化済み。「誰かが conftest を false に直したら XPASS」となるが、**認証検証テスト自体はまだ無効なまま**（約 55 件のテストが `AUTH_DISABLED=true` を暗黙前提で。） | **約 55 件のテストの移行が必要**: ① `conftest.py` の既定を `false` に変更 ② 影響テストに `AUTH_DISABLED=true` への明示的 override（autouse fixture 等）を追加 ③ 段階的に移行。**単独では完了できない・本計画は「xfail で追跡可能」を目標とする** | 高（認証の回帰が CI 緑でも検出できない） |
| R2 | **`BookRepository` の重複定義**（クラス2 の根因） | P0-③ のゲートは「UnitOfWork が使う側との整合」を守るが、「2 つあること自体」は検出しない（誤検出の可能性が高いため） | `src/infrastructure/repositories/book` と `src/backend/database/repository` のマージ・片方のリネーム。破壊的 | 中（再発P0-③が防ぐが、設計上の混乱が残る） |
| R3 | **`generate_openapi.py` の `.env` 依存**（クラス8） | P1 の検出テストで「気付ける」レベルまで。**根本解決（P2-⑦）は未着手** | `generate_openapi.py` に `APP_ENV` の明示的 setdefault / `--app-env` オプションを追加 | 中（drift 发生时、手動で `./scripts/generate_openapi.py` を叩くと再発する） |
| R4 | **動的ディスパッチの静的解析不能** | クラス2 のゲートは `uow.<prop>.<method>` の**静的パターン**のみを検出。`getattr(uow, name)(...)` の**動的解決**は検出対象外（保守的に false positive を避けるため） | 動的ディスパッチ箇所はコードレビューで担保、または実行時トレーシング | 低（該当箇所は限定的） |
| R5 | **`mypy` の緩さ** | クラス2 の未定義メソッドは、**厳格な型チェックなら mypy でも検出可能**だが、現状の mypy 設定は `uow` を `Any` 扱いしており通過する | mypy 設定の厳格化（`UnitOfWork` の型注釈を routers まで伝播させる）。P0-③ の専用ゲートの代替にはならないが、相補的に有用 | 中 |
| R6 | **`_await_awaitable` の誤用（逆方向）** | §3.2 のゲートは「未正規化の awaitable を `create_task`/`run` に渡す」ことを検出するが、「**同期関数の中で `await` を書こうとする**」等の逆方向は検出しない | 実装の점에서 `create_task`/`asyncio.run` の使用箇所を限定的に自己レビュー | 低 |

---

## 付録: 実行コマンド早見表

```bash
# 既存ゲート（すべて PR CI で実行）
python -m pytest tests/regression/test_no_undefined_names.py -q
python -m pytest tests/regression/test_auth_bypass_contract.py -q
python -m pytest tests/regression/test_subprocess_encoding_gate.py -q
python -m pytest tests/regression/test_docs_router_count_matches_reality.py -q

# 提案中（P0/P1）
python -m pytest tests/regression/test_regression_collects_cleanly.py -q
python -m pytest tests/regression/test_test_dependencies_declared.py -q
python -m pytest tests/regression/test_repository_method_contract.py -q
python -m pytest tests/regression/test_await_awaitable_contract.py -q
python -m pytest tests/regression/test_await_helper_usage.py -q
python -m pytest tests/regression/test_stale_expectations.py -q

# OpenAPI 再生成（APP_ENV を検証と一致させる）
# PowerShell:
$env:APP_ENV="testing"; py scripts/generate_openapi.py; Remove-Item Env:APP_ENV

# 回帰スイート全体
python -m pytest tests/regression -q
python -m pytest -m integration -q
```