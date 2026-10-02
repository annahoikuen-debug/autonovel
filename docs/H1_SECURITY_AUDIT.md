# H1 セキュリティ・テスト信頼性 精査結果

- **文書ID**: `H1_SECURITY_AUDIT`
- **作成日**: 2026-10-01（最終更新 2026-10-02）
- **対象**: AutoNovel v6.0.0
- **計画書**: [`plans/PLAN_H1_SECURITY_HYGIENE_36STEPS.md`](../plans/PLAN_H1_SECURITY_HYGIENE_36STEPS.md)
- **総合判定（レビュー時）**: **条件付き不可**

本書は H1 精査レビュー（セキュリティ / 静的解析 / テスト信頼性 評価 D〜D+）の
起点となる所見と、その整改 36 ステップの**実施結果**を記録する。
新機能を 1 行も足さず、「悪化する未来」を CI が検出できるようにすることだけが目的だった。

---

## 1. レビューで指摘された構造欠陥（整改前）

| # | 系統 | 所見 |
|:---|:---|:---|
| S | 認証境界 | `branches.py` が `book_id` の所有者は検証するが、操作対象の `branch_id` がその book に属するかを検証していない（cross-tenant） |
| S | 認証境界 | `structure.py` / `prompt_versions.py` / `prompt_compare.py` に認証も所有者検証も無い |
| S | 認証境界 | tenant の `user_id` に外部キー制約が無い（0027 は `sa.Column` のみ追加） |
| S | 到達性 | `orchestrated.py` が `server.py` にマウントされておらず、FE が呼ぶ API が常に 404 |
| Q | 空振りテスト | 恒真 assert（`assert x is not None or x is None`）とソース文字列 grep が複数存在し、緑が何も保証していない |
| Q | 収集 | `tests/config/test_flaky_detection.py` に `Path` の import 欠落で collection error |
| H | CI ゲート | `static-analysis` が `continue-on-error: true` で記録のみ。`release-consistency` はバージョン比較 1 本のみ |
| H | CI ゲート | pytest マーカーと `--timeout` の実効性が担保されていない |
| H | ドリフト | vite dev proxy と FastAPI の mount point が手動同期 |
| H | 認証漏えい | 生 `fetch(` が認証ヘッダを素通り |
| R | 衛生 | `tmp/` 43 件のスクラッチが git 追跡下 |
| R | 衛生 | import 元ゼロのシムが 3 ファイル残存 |
| R | 出力 | `PdfExporter` が Markdown を返している（`EpubExporter` と同型） |
| M | 実行時 | 同期関数からの無防備な `asyncio.run` / `run_until_complete` |
| M | 実行時 | `audit_agent.py`（1389 行）が無カバレッジ |

---

## 2. 整改で**否認された**指摘（実測して撤回した）

本計画の指示は H1 レビューに基づくが、実測の結果次の 4 件は成立しなかった。
そのまま実装すると**誤った変更**になっていたため、実測値を記録し実装していない。

| # | 指摘 | 実測 | 判断 |
|:---|:---|:---|:---|
| M2 | `src/backend/database/repository.py:174,194` の `asyncio.run` を撤去する | 両箇所は既に `try: get_running_loop() → create_task / except RuntimeError: asyncio.run()` の正しいガード構造。撤去すると既存 3 テストが壊れる | **D12 で取り消し**。安全性をテストで固定するのみ |
| M3 | `executor_manager` の module-level 生成が import 時に 40 スレッドを作る | **0 本**。`ThreadPoolExecutor` は `submit()` までスレッドを作らない | **遅延生成化を実装せず**。import 時のスレッド起動を検出する archangel を追加 |
| M3 | `AppContainer` にプロセスシングルトン機構が無く `providers.Singleton` が機能しない | `AppContainer.db()` は 2 回呼んでも同一インスタンスを返し、`db` は `providers.Singleton` | **app.py は変更せず**。singleton 性をサブプロセスで実測固定 |
| M2/R3 | `PdfExporter` を `NotImplementedError` に置換する | 既存 10 テストが「PDF が Markdown を出す」ことを assert しており、R3 のファイル所有表を超える | **出力は変えず** `TODO(H1-9)` として明示固定（共通テンプレート化のみ実施） |

---

## 3. 整改で**新たに発見した**欠陥（レビューには無いもの）

| # | 発見 | 対応 |
|:---|:---|:---|
| N-1 | **S9 は「マウント済み」と報告したが**、`orchestrated.py:35` に prefix が無く FE が叩く `/orchestrated/*` は依然 404 のままだった | router に `prefix="/orchestrated"` を付与し、FE 契約パスを検証するテストを追加 |
| N-2 | `/images/{book_id}/{scene_name}` は backend が持つが vite proxy に無く、dev で 404 | proxy に `/images` を追加 |
| N-3 | vite proxy に 13 件の死んだ設定（backend に存在しない prefix） | 削除（サービス API は `/api` 配下へ移行済み） |
| N-4 | `docs/openapi.json` が **version 5.0.3 / 213 paths** のまま 6.0.0 より古く、`docs/api.md` が「CI が drift を検知する」と主張していた | APP_ENV=testing で再生成（240 paths）し、drift 検出テストを実装 |
| N-5 | `docs/STATUS.md` の CI コマンドが ci.yml のマーカー式と不一致 | 実測値へ修正し、乖離を検出するテストを追加 |
| N-6 | Makefile の `black-check` が H6 で中身だけ `ruff format` に変わったまま `format-check` と二重化 | target 撤去（D06） |
| N-7 | H8 の `test_H1_http_error_discipline.py` に未使用 import があり、**H1 で導入した ratchet を赤くしていた**（actual 968 > baseline 967） | 除去し ratchet を緑に復帰 |

---

## 4. 整改後の検出能力（19 ファイル → 22 ファイル）

| テストファイル | 検出する将来の退行 |
|---|---|
| `tests/security/test_branch_cross_tenant.py` | branches の branch_id 越境 |
| `tests/security/test_branch_guard_shared.py` | ガードロジックの重複再発生 |
| `tests/security/test_router_ownership_matrix.py` | structure/prompt_* の認証・所有権削除 |
| `tests/regression/test_tenant_fk_integrity.py` | FK 削除・Alembic 分岐 |
| `tests/security/test_server_route_mount_parity.py` | マウント漏れ（orchestrated 型） |
| `tests/security/test_idor_regression.py` | 新規 router の所有者検証漏れ |
| `tests/regression/test_H1_tautology_guard.py` | 恒真 assert の再導入 |
| `tests/regression/test_H1_gitignore_tightness.py` | スクラッチの再追跡 |
| `frontend/tests/unit/tautology.guard.test.ts` | フロントの空振りテスト再導入 |
| `tests/regression/test_H1_lint_ratchet.py` | ruff 劣化 |
| `tests/security/test_H1_ci_workflow_contract.py` | CI の gate 無効化・マーカー未反映 |
| `tests/regression/test_H1_routing_drift.py` | proxy / mount ドリフト（双方向） |
| `tests/regression/test_H1_http_error_discipline.py` | 生 fetch の認証ヘッダ漏えい |
| `tests/unit/services/test_exporters_stream_contract.py` | 形式 cross-contamination（PDF→Markdown 等） |
| `tests/regression/test_H1_async_boundary.py` | 無防備 `asyncio.run` の再導入 |
| `tests/regression/test_H1_import_purity.py` | import 時スレッド生成・Singleton 崩壊 |
| `tests/regression/test_H1_audit_agent_smoke.py` | 1389 行モジュールが import 不能・ゲート判定が壊れる |
| `tests/regression/test_H1_no_orphan_shims.py` | 死んだシムの再増加 |
| `tests/regression/test_docs_router_count_matches_reality.py` | 文書と実装の不一致（README 数値 / CI マーカー式 / OpenAPI drift） |

**検出器の自己検証**: `test_H1_import_purity` と `test_H1_no_orphan_shims` は
合成的な悪化した入力を作り、検出器が実際に検出力を持つことを検証する
（検出器が常に空を返す実装になっていたら这两テストが赤になる）。

---

## 5. 残課題（TODO 番号で追跡）

| TODO | 内容 | 担当 |
|:---|:---|:---|
| `TODO(H1-2)` | `test_idor_regression.py` の `NO_OWNERSHIP_NEEDED` allowlist 残存分 | PLAN-H2 |
| `TODO(H1-4)` | 生 `fetch(` 28 箇所の `apiFetch` 移行 | PLAN-H2 |
| `TODO(H1-5)` | Huey immediate モード時の `asyncio.run` 経路、依存する 6 ファイル | PLAN-H2 |
| `TODO(H1-8)` | import 元ゼロ残存 2 ファイル（`ncs_calibration.py` / `data_loader.py`） | PLAN-H2 |
| `TODO(H1-9)` | **`PdfExporter` / `EpubExporter` が Markdown を返す**（PDF ライブラリ導入 or `NotImplementedError` 化 + 既存 10 テストの同時更新） | PLAN-H2 |
| N1（§9） | ruff / mypy のベースライン 0 化 | PLAN_H1-R |
| — | `npm run test:ci` の 6 ファイル / 9 テスト失敗（FE 側の既存不具合） | PLAN-H3 |