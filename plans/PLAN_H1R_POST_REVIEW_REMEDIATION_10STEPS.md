# PLAN_H1R — H1 レビュー後 是正実装計画書

- **文書ID**: `H1R_POST_REVIEW_REMEDIATION`
- **作成日**: 2026-10-02
- **前計画**: [`PLAN_H1_SECURITY_HYGIENE_36STEPS.md`](H1_SECURITY_HYGIENE_36STEPS.md)（36 ステップ完了）
- **前提**: H1 の 36 ステップは完了済み。レビューで **H1 自身が原因の欠陥** が 1 件（`check_database`）と、**H1 が原因の FE テスト破壊** が 1 件（`graph.test.ts` 2 件）発見された。
- **本計画の性格**: 計画本文に「数値を書いたら実測する」を厳守する（D11/D13）。判断が要る項目は**保留**として手順だけ残す。

---

## 0. 実測事実（2026-10-02）

計画を書く前に、現状を**機械で数えて**確定した。ここに無い数値は本計画に書かない。

### 0.1 H1 が原因の欠陥（新規発見）

| # | 事象 | 実測方法 | 結果 |
|:---|:---|:---|:---|
| **B-1** | `check_database()` が 2 世代連続で常に `"error"` | `py -c "from src.services.resilience import check_database; print(check_database())"` | 旧: `There is no current event loop` / H1中間案: `greenlet_spawn has not been called` → **両方とも `"error"`**。`get_system_status()["database"]` は恒久的に嘘をついていた。**H1 完了時点で未修正** → `49f32aaf` で修正済み |
| **B-2** | `tests/api/graph.test.ts` 2 件が H1 の `apiFetch` 移行で赤くなった | `git checkout 5b4c0563~1 -- frontend/src/api/graph.ts` して再実行 | revert すると **1 passed**。→ **H1 (H8 Step 11) が直接原因**。A8 の「既存不具合」判定は**誤り**だった |

### 0.2 既存（H1 原因でない）frontend 失敗

`npm run test:ci` の 9 件失敗のうち、**7 件は H1 原因ではない**（UI 側が変わりテスト期待値が古くなったもの）。

| ファイル | 件数 | 実測した失敗内容 |
|:---|:---|:---|
| `tests/unit/uiux/persistFailureNotification.test.tsx` | 3 | `Unable to find an element with the text: Sample 2` / `toHaveTextContent` / `not.toBeInTheDocument` |
| `tests/components/EditorRefinement.test.tsx` | 1 | `Unable to find ... 第1話 運命の剣` |
| `src/components/generate/SimpleModePanel.test.tsx` | 1 | `Unable to find an element with the display value: hot_blooded` |
| `tests/unit/uiux/wizardStep3Editing.test.tsx` | 1 | `localStorage.getItem("autonovel.wizard.draft.7")` が `null` |
| `tests/unit/uiux/chapterPersistence.test.ts` | 1 | `expected "spy" to be called with ['/api/episodes/chapters/1/3', …(1)]`（H8 revert でも赤 → **既存**） |
| `tests/api/graph.test.ts` | 2 | `expected "fetch" to be called with arguments: [Array(1)]`（**H1 原因**） |

### 0.3 `npm run test:ci` の現状値（2026-10-02 実測）

```
Test Files  6 failed | 62 passed (68)
Tests       9 failed | 350 passed (359)
Duration    約 300s
```
coverage レポートは **テスト失敗時に生成されない**ため閾値 gate（50%）には到達しない。

### 0.4 mypy の 1 件（`src/backend/server.py`）

```
src\backend\server.py:213: error: Name "health" already defined (by an import)  [no-redef]
Found 1198 errors in 272 files (checked 1053 source files)
```

実測した構造:
- `:37` `from src.backend.routers import (..., health, ...)` → `health` は**モジュール**
- `:204` `app.include_router(health.router)` → モジュール時刻（正しい）
- `:214` `async def health()` → `health` を**関数に再束縛**
- `:80` `health = check_huey_health()` は `lifespan` 内の**ローカル変数**（モジュールの場合には影響しない）— `:79-83` の try/except kubun のため実害はない

危険は **`:214` 以降のモジュールレベルコードが `health.router` を参照すると壊れる**点。
ただし**:213 の関数名を rename すると FastAPI の operationId が変わり** `frontend/src/types/api.generated.ts` に影響するため、**エイリアス import** で解く。

---

## 1. ファイル排他所有表（P1）

| ファイル | 担当ステップ |
|:---|:---|
| `tests/integration/test_health_status_real_db.py`（新規） | H1R-1 |
| `frontend/tests/api/graph.test.ts` | H1R-2 |
| `frontend/tests/unit/apiFetchContract.guard.test.ts`（新規） | H1R-2 |
| `src/backend/server.py` | H1R-3 |
| `tests/regression/test_H1_fe_api_call_contract.py`（新規） | H1R-2 |
| `docs/H1_SECURITY_AUDIT.md` | H1R-5 |
| `docs/FRONTEND_KNOWN_FAILURES.md`（新規） | H1R-4 |
| `CONTRIBUTING.md` | H1R-6 |
| `docs/H1R_DECISIONS.md`（新規） | H1R-7 / H1R-8 |

---

## 2. 実装ステップ

### H1R-1. 実物 DB で叩く smoke（P0・最重要）

**なぜこれが最優先か**: H1 が 19 本の archangel を追加したが、`check_database` のバグを
**1 本も捕まえていない**。全 archangel が「形」（import・ガード・ファイル配置）だけを
検査し、「イベントループ／greenlet／DB 接続」という**境界をまたぐ実挙動**を
検査するものが存在しなかった。**archangel を増やすより 1 本の smoke が効く。**

**做法**: `tests/integration/test_health_status_real_db.py` を追加する。
**mock を 1 つも使わない**。`TestClient(app)` で実 app を起こし、実 DB に到達する経路を叩く。

検証する 4 点:
1. `GET /health` → 200
2. `GET /health/detail` → 200（`AUTH_DISABLED=true` 下）
3. `GET /api/system/status` → `database == "ok"`（← 2 世代壊れていた場所）
4. `GET /metrics` → 200

**検出力の自己検証（P4）**: `check_database` を壊した版へ一時差し替え、
本テストが赤くなることを**実測してから**確定する。

**受入**: 新テストが緑 + 壊した版で赤になる実測 + 既存 364 件が緑のまま。

---

### H1R-2. H1 が壊した FE テスト 2 件を修復 + stale 契約 archangel

**原因**: H1 Step H8 は `frontend/src/api/graph.ts` の生 `fetch(` を `apiFetch(` に
移行した（認証ヘッダ漏えい修正）。しかし `tests/api/graph.test.ts:22,52` は
`toHaveBeenCalledWith(url)`（**第 1 引数のみ**）を assert しており、
`apiFetch` は必ず `fetch(endpoint, { headers, signal })` と**第 2 引数を付ける**ため
1 引数一致しない。**テストが古い契約を固定していた。**

**做法**:
- `frontend/tests/api/graph.test.ts:22,52` を `apiFetch` の契約に合わせて修正する。
  第 1 引数は URL、第 2 引数は `expect.objectContaining({ headers: expect.any(Headers) })`。
  **リンク-token も 1 つ検証する**（移行の目的が認証ヘッダ注入なので、
  「URL が変わった」だけでは移行の効果を検証していない）。
- `frontend/tests/unit/apiFetchContract.guard.test.ts`（新規）を追加:
  実 FE テストが **`toHaveBeenCalledWith(<url>)` の 1 引数で `fetch` を検査**していない
  ことを検出する archangel。移行後に同じ stale 契約が再発するのを防ぐ。

**検出力の自己検証（P4）**: graph.ts を H1 直前の版へ差し戻す。
判定基準は当初「両方緑になること」を想定していたが、**実測の結果その基準は誤りと判明**。
`apiFetch` 移行を revert すると `graph.test.ts` は **赤になるのが正しい**
（認証ヘッダ注入という移行の目的を固定しているため、移行を失えば落ちるべき）。
archangel 本体は両状態で **緑**であることを判定基準とする（2026-10-02 実測で訂正）。

---

### H1R-3. `server.py` の `health` 名前衝突を解消（P2）

**做法**: `:37` の import を `health as health_router` にエイリアスし、
`:204` を `app.include_router(health_router.router)` に変更する。

**採らない做法**: `:214` の関数名 rename。FastAPI の `operationId` が変わり
`frontend/src/types/api.generated.ts` の型と不整合になる。

**受入**: `mypy src` の `server.py:213` no-redef が 1 件減る、
`include_router` parity テストが緑、`/health` と `/health/detail` が 200。

---

### H1R-4. 既存 FE 失敗 7 件の原因を実測して記録（P1・修正は別計画）

**やらないこと**: 7 件を今直すこと。UI の期待値が古くなっただけで、
**どのテストが古いのか**を 1 件ずつ実測する必要がある（H1R の範囲を超える）。

**做法**: `docs/FRONTEND_KNOWN_FAILURES.md` を新規作成し、§0.2 の表をそのまま
「実測済みの失敗内容」として記録する。**推測で書かない**。

**受入**: 7 件すべてに実測した失敗メッセージと原因区分（H1 原因 / 既存）が書いてある。

---

### H1R-5. `docs/H1_SECURITY_AUDIT.md` に H1R の結果を追記

- §3「整改中に新規に発見した欠陥」に **B-1 / B-2** を追加。
- **A8 の判定を訂正**する。旧記述「既存不具合・H1 範囲外」→
  9 件のうち **2 件が H1 原因**（`graph.test.ts`）、7 件が既存。
- 教訓として **「archangel は形しか見ない」** を明記。

---

### H1R-6. `CONTRIBUTING.md` に 1 規約追加

> **関数を書き換えたら、素の呼び出しで 1 回実行する。**
> mock が入ったテストは「mock が正しく動いている」ことしか保証しない。
> H1 では archangel 19 本が緑のまま `check_database()` が 2 世代壊れていた。

---

### H1R-7. N1（mypy 1198 → 0）を**実施しない**判断の文書化

**判断**: 実施しない。1198 件の大半は型注釈の未整備で、
0 化しても**バグは 1 件も減らない**。現在も `ci_lint_ratchet.py` で凍結済み。
工数 대비 効果零零。

**ただし**: H1R-3 の 1 件（`server.py:213`）は**実害ubitがある**ため直す。
残 1197 件は凍結継続。

**做法**: `docs/H1R_DECISIONS.md` に判断と根拠を書く。

---

### H1R-8. `TODO(H1-9)` PdfExporter は保留（Product 判断待ち）

**現状**: `PdfExporter` は Markdown を返す（バグは実在）。
ただし**直すか壊れたままにするかは Product 判断**。

**手順書だけ残す**:
1. `GET /export/books/{id}?platform=pdf` の利用実績を access log / 呼び出し元コードで確認
2. 使われていない → `NotImplementedError` に置換し、`tests/unit/services/exporters/` の
   既存 10 件を**同時に**更新（30 分）
3. 使われている → PDF ライブラリ導入は別計画

**本計画では判断しない。** `docs/H1R_DECISIONS.md` に上記 3 ステップを記録する。

---

### H1R-9. 未追跡 `plans/PLAN_Q1_QUERY_TOOLING_PHASE1_2_72STEPS.md`

`plans/` は追跡対象だが、このファイルは未追跡のまま。
**私のファイルではない**ため commit も削除もしない。
`docs/H1R_DECISIONS.md` に「所有者に commit / .gitignore どちらにするか判断を委ねる」と記録。

---

### H1R-10. 受入基準の実測

| # | 判定 | 実測方法 |
|:---|:---|:---|
| A1 | ✅/❌ | `py -m pytest tests/integration/test_health_status_real_db.py -q` |
| A2 | ✅/❌ | 壊した `check_database` で本テストが赤になる実測 |
| A3 | ✅/❌ | `npx vitest run tests/api/graph.test.ts tests/unit/apiFetchContract.guard.test.ts` |
| A4 | ✅/❌ | `git checkout 5b4c0563~1 -- frontend/src/api/graph.ts`（apiFetch 移行を revert）した状態で **archangel 本体（apiFetchContract.guard.test.ts）が緑**であること。<br>**`graph.test.ts` は赤になることが正しい**（認証ヘッダ契約の固定であり、移行を失えば落ちるべき） |
| A5 | ✅/❌ | `npm run test:ci` の failed 件数が **9 → 7** に減ること（2 件は直る。7 件は H1R-4 で記録した既存分） |
| A6 | ✅/❌ | `mypy src` の `server.py` no-redef が消えていること |
| A7 | ✅/❌ | `npm run typecheck` / `npm run lint` |
| A8 | ✅/❌ | `py -m pytest tests/regression tests/security -q` |
| A9 | ✅/❌ | `python scripts/ci_lint_ratchet.py` の exit code 0 |

---

## 3. 期待される効果（測定できる形で書く）

| 指標 | 計画前（2026-10-02 実測） | 計画後（目標） |
|:---|:---|:---|
| `npm run test:ci` の failed | 6 files / 9 tests | **6 files / 7 tests** |
| H1 起因の FE 失敗 | 2 件 | **0 件** |
| 実 DB で status を叩くテスト | 0 件 | **1 件** |
| `mypy src` の `server.py` no-redef | 1 件 | **0 件** |
| `tests/regression` + `tests/security` | 364 passed | **364 passed 以上**（壊さない） |

---

## 4. 範囲外（やらないこと）

| 項目 | 理由 |
|:---|:---|
| mypy 1198 → 0 | H1R-7 で判断 |
| FE 既存 7 件の修正 | H1R-4 で記録のみ。UI 側の調査が必要で範囲外 |
| `PdfExporter` の修正 | H1R-8 で保留（Product 判断） |
| archangel の追加 | **増やさない**。19 本で 1 件も捕まらなかった。smoke を 1 本足す方が効く |