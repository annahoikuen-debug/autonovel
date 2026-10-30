# 未コミット WIP Triage 表（PLAN_J1 W3）

> **目的**: 改善案1〜3 のコミット後も残っている **47 ファイルの未コミット WIP** を、
> 「改善案と関連するか」「機能として自立しているか」「削除すべきか」で分類し、
> 勝手に捨てないまま commit / revert / 継続の判断材料を作る。
> **本表は判断の記録であり、WIP をまだコミットも revert もしていない**（実行は W4/W5）。
> 作成日: 2026-10-30 / HEAD `7e4c6e1`（W2 完了時点）

---

## 0. サマリ

| 分類 | 件数 | 扱い（W4/W5 での処置案） |
|---|---:|---|
| **A. 改善案と関連** | 5 | 改善案5（静的解析ゲート）／改善案2（設定SSOT）の未コミット分。TRACK-A/S の基盤として commit 候補 |
| **B. 無関係の機能 WIP（自己完結）** | 38 | 個別の機能・セキュリティ改善。テストが緑のものを中心に commit 候補。連動ファイルはセットで扱う |
| **C. 削除予定** | 1 | `credit_guard.py` 削除。残存参照なしを確認済み。W5 で commit（削除の確定） |
| **うち W2 で処理済み** | 1 | `jwt.py`（W2 `e9e743d` でテスト側を新シグネチャへ統一済み。ソースは WIP のまま正しい） |
| **合計** | **47** | — |

### 分類の決め手（実測）
- 47 件すべての diff を確認し、`git status --short` の全件を下表に列挙（過不足なし）。
- 各テストファイルは **1 ファイルずつ実測**（`pytest --tb=no`）して緑/赤/環境起因を確定。

### 横断の重要発見（環境起因の欠落依存）
`skipped` となった 9 テストはいずれも **依存未インストール** が原因（W1 と同じ PEP 668 状況:
`--break-system-packages` なしでは pip 不可、かつ venv なし）。**宣言済みだが未導入** の依存が広範に存在する:

| 未導入モジュール | 宣言場所 | skipped になるテスト |
|---|---|---|
| `anthropic` | main deps | `test_core_zero_modules.py` |
| `google.genai` | main deps | `test_gemini_unified_client.py` |
| `sentry_sdk` | `observability` extra | `test_sentry.py` / `test_observability.py` / `test_monitoring_init.py` |
| `hypothesis` | 未宣言（テスト用） | `test_{grammar,dsp,compression}_properties.py` |
| `fakeredis` | dev extra | `test_emotional_residue_regression.py` |

> **提言（W1 の延長）**: W1 で asyncpg/psycopg を導入したのと同様、上記もユーザー領域へ導入すれば
> 9 skipped が実行され、隠れた赤が現れる可能性がある。TRACK-W の残タスクとして別ステップ化を推奨。

---

## 分類 A: 改善案と関連（5件）

改善案5（静的解析ゲート強化・TRACK-S）と改善案2（設定 SSOT）に対応する未コミット分。
CI を「記録のみ」から「ratchet hard gate」へ引き上げる一連の変更で、**3 ファイルはセット**。

| ファイル | 変更概要 | テスト状態 | 処置案 |
|---|---|---|---|
| `.github/workflows/ci.yml` | lint ratchet を hard gate 化（ruff / mypy / format の 3 段を追加） | — (CI設定) | commit（TRACK-S S4 と整合） |
| `scripts/ci_lint_ratchet.py` | `--tool mypy` / `--tool format` / `--update` 対応を拡張（+149） | — (スクリプト) | commit（上とセット） |
| `config/ci_lint_baseline.json` | ratchet ベースライン更新（ruff 163 等） | — (データ) | commit（上とセット） |
| `tests/unit/backend/test_env_example_loads.py` *(untracked)* | `.env.example` が `Settings` でロードできることの回帰（改善案2 SSOT 関連） | 🟢 1 passed | commit |
| `tests/regression/test_lint_budget.py` | lint 予算の上限固定（A/B 両義・改善案5 関連） | 🟢 7 passed | commit（A として扱う） |

> A の 3 ファイル（ci.yml / ratchet.py / baseline.json）は **不可分の1単位** としてコミットすること。
> 片方だけ入れると CI の ratchet が壊れる。

---

## 分類 B: 無関係の機能 WIP（自己完結・38件）

改善案1〜3 には無関係だが、**個別に自己完結した機能・セキュリティ改善**。テストが緑のものを中心に
commit 候補。連動ファイル（ソース＋対応テスト＋再生成成果物）はセットで扱う。

### B-1. セキュリティ / マルチテナント分離

| ファイル | 変更概要 | テスト状態 | 処置案 |
|---|---|---|---|
| `src/backend/security/owner_guard.py` | `_tenant_mismatch` を追加しテナント境界を検証（+27） | （対応テストへ影響・下記） | commit（機能） |
| `src/backend/database/models.py` | `Tenant`/`TenantMember` を import（テナント FK 解決） | — | commit（owner_guard とセット） |
| `src/backend/routers/billing.py` | `_safe_redirect_url` でオープンリダイレクト防止 | 🟢 (test_billing_redirect 7 passed) | commit |
| `tests/unit/test_billing_redirect.py` *(untracked)* | 上の allowlist テスト | 🟢 7 passed | commit（billing.py とセット） |
| `src/api/middleware/rate_limit.py` | 独自固定ウィンドウを `RateLimiter`（Redis 分散）へ委譲（+103） | （下記 stream_auth 等へ影響） | commit（機能） |
| `src/backend/database/core.py` | 初期作品の自動シードを廃止（NULL 所有者ゴースト行の回避） | ⚠️ 別途: sqlite `:memory:` エンコード実バグあり（W1 で確認・TRACK-A 対処） | commit（シード廃止のみ）／エンコードバグは別 |
| `src/backend/security/password.py` | 末尾改行のみ（cosmetic） | — | commit（微量） |
| `src/backend/security/jwt.py` | `user_id=` 新シグネチャ（**W2 `e9e743d` で処理済み**） | 🟢 (test_auth_real_session / 契約テスト 緑) | — （W2 で完了） |
| `tests/security/test_stream_auth.py` | JWT 新シグネチャへ追随 | 🟢 35 passed | commit |
| `tests/security/test_token_denylist.py` | 同上 | 🟢 15 passed | commit |
| `tests/unit/routers/test_auth_jwt_security.py` | 同上 | 🟢 5 passed | commit |

### B-2. API / 機能の個別改善

| ファイル | 変更概要 | テスト状態 | 処置案 |
|---|---|---|---|
| `src/backend/server.py` | `/api/easy-mode` を常時マウント（OpenAPI drift 防止） | （docs_router_count と連動・下記） | commit |
| `docs/openapi.json` | 上記に伴う OpenAPI 再生成（+486） | 🟢 (docs_router_count 7 passed) | commit（server.py とセット） |
| `src/backend/routers/graph.py` | Cypher 実行を 200→410 Gone に変更 | （H1_routing_drift と連動） | commit |
| `src/core/plugin_registry.py` | フラグを `os.getenv`だけでなく `Settings`（`.env`）からも解決 | 🟢 (plugin_conditional_routing 5 passed) | commit |
| `src/backend/multimedia_service.py` | テストフィクスチャ再エクスポートを廃止（本番/テスト分離） | 🟢 (test_multimedia_service 8 passed) | commit |
| `src/backend/routers/multimedia.py` | マルチメディアルーターの調整 | 🟢 (test_multimedia_service 8 passed) | commit（上とセット） |
| `tests/unit/test_multimedia_service.py` | 上記に伴うテスト更新 | 🟢 8 passed | commit（セット） |
| `src/core/llm/factory.py` | 末尾改行のみ（cosmetic） | — | commit（微量） |
| `src/services/billing/stripe_client.py` | 末尾改行のみ（cosmetic） | — | commit（微量） |
| `README.md` | 起動手順の更新 | — (文書) | commit（TRACK-R R1 と整合） |
| `tests/regression/test_H1_routing_drift.py` | ルーティング drift テスト更新 | 🟢 4 passed | commit |
| `tests/regression/test_docs_router_count_matches_reality.py` | ルーター数整合（server.py 常時マウントと整合） | 🟢 7 passed | commit（server.py と整合） |
| `tests/regression/test_v53_long_form_integrity.py` | 長編整合性リグレッション | 🟢 52 passed | commit |
| `tests/unit/api/test_plugin_conditional_routing.py` | プラグイン条件分岐ルーティング | 🟢 5 passed | commit（plugin_registry とセット） |
| `tests/unit/test_csp_models.py` | CSP モデルテスト更新 | 🟢 2 passed | commit |

### B-3. フロントエンド（認証 UI feature・一連）

未ログイン時の `/login` `/register` 誘導と認証ガードを追加する一連の feature。

| ファイル | 変更概要 | テスト状態 | 処置案 |
|---|---|---|---|
| `frontend/src/App.tsx` | 認証必須ルートのガード追加 | — (フロント) | commit（B-3 はセット） |
| `frontend/src/components/layout/AppLayout.tsx` | ログアウト導線を追加 | — (フロント) | commit（セット） |
| `frontend/src/context/AuthContext.tsx` | バックエンド `detail` を優先したエラー表示 | — (フロント) | commit（セット） |
| `frontend/src/routes.tsx` | `/login` `/register` ルート追加 | — (フロント) | commit（セット） |
| `frontend/src/pages/AuthPage.tsx` *(untracked)* | ログイン/登録ページ | — (フロント) | commit（セット） |

> B-3 はフロントのみの変更で、バックエンドの JWT 新シグネチャ（W2）と整合する。**5 ファイルを 1 単位** でコミット。

### B-4. 環境起因 skipped（依存未導入・9件）

いずれも**依存未インストール**で skip（実バグではなく環境未整備）。W1 延長で依存を導入すれば実行可能に。

| ファイル | skip 理由（実測） | 処置案 |
|---|---|---|
| `tests/unit/core/test_core_zero_modules.py` | `anthropic` 未導入 | 依存導入後に再評価 |
| `tests/unit/test_gemini_unified_client.py` | `google.genai` 未導入 | 依存導入後に再評価 |
| `tests/monitoring/test_sentry.py` | `sentry_sdk` 未導入 | 依存導入後に再評価 |
| `tests/monitoring/test_observability.py` | `sentry_sdk` 未導入 | 依存導入後に再評価 |
| `tests/infrastructure/test_monitoring_init.py` | `sentry_sdk` 未導入 | 依存導入後に再評価 |
| `tests/property/test_grammar_properties.py` | `hypothesis` 未導入 | 依存導入後に再評価 |
| `tests/property/test_dsp_properties.py` | `hypothesis` 未導入 | 依存導入後に再評価 |
| `tests/property/test_compression_invariants.py` | `hypothesis` 未導入 | 依存導入後に再評価 |
| `tests/regression/test_emotional_residue_regression.py` | `fakeredis` 未導入 | 依存導入後に再評価 |

### B-5. 実バグ（修正が必要・1件）

| ファイル | 状態 | 内容 | 処置案 |
|---|---|---|---|
| `tests/config/test_phase1_coverage.py` | 🔴 1 failed（**実バグ**） | `pyproject.toml` の `[tool.coverage.report]` に `fail_under` キーが存在しないのに、テストが `fail_under >= 55` を要求 → `KeyError: 'fail_under'` | TRACK-Q（coverage gate）で対処。現状 WIP のままでは緑にならない |

---

## 分類 C: 削除予定（1件）

| ファイル | 状態 | 内容 | 処置案 |
|---|---|---|---|
| `src/backend/security/credit_guard.py` | D（削除済み） | クレジットガードの削除。`grep -rn "credit_guard" src tests config` で**残存参照ゼロ**を確認済み | W5 で commit（削除の確定）。リグレッションテスト `test_no_dead_references.py` を追加 |

---

## 処理方針（W4/W5 への引き継ぎ）

1. **W4（commit）**: 分類 A の 5 件（改善案連動）→ B-1〜B-3 の緑テスト群（ソース＋対応テスト＋再生成物をセット）を、機能単位で個別コミット。フロント B-3 は 1 単位。
2. **W5（revert/確定）**: 分類 C（credit_guard 削除）を残存参照確認のうえ commit。実バグ B-5 は TRACK-Q へ。
3. **環境依存（B-4）**: 9 skipped は依存導入（W1 延長）後に再評価。導入するまで「緑だが未実行」として扱う。
4. **本表は WIP を捨てない**。全 47 件をカテゴリに割り当て、処置案を明記するにとどめた。

> 各行の「テスト状態」は 2026-10-30 実測（`pytest --tb=no -q`・1ファイルずつ）。🟢=passed / 🔴=failed（実バグ）/ ⚠️=ソースに別バグあり / skip=環境起因。
