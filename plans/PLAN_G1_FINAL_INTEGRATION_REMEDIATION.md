# AutoNovel 最終統合整改計画書【G1 / 5 ステップ】

## ── 「一応の完成形」を出すための最後の赤消除し ──

- **文書ID**: PLAN_G1_FINAL_INTEGRATION_REMEDIATION
- **作成日**: 2026-09-30
- **起点イベント**: F2 整改後の統合検証（全ゲート再実行）
- **前提文書**: [PLAN_F2_CODE_REVIEW_REMEDIATION_13STEPS.md](PLAN_F2_CODE_REVIEW_REMEDIATION_13STEPS.md)
- **対象バージョン**: AutoNovel v6.0.0（F2 整改済み・ブランチ `fix/f2-review-remediation`）
- **総合判定（レビュー時）**: **不可**。S1 相当 3 件（うち 1 件は本番ビルドを壊す欠陥）＋環境破損 1 件
- **構成**: G1〜G5 ＝ **計 5 ステップ**

---

## 0. 本計画書の位置づけ

F2 計画（13 ステップ）は R1〜R8 / F1〜F5 が全てコミット済み（`9ee8cfb3..23bd8bfc` の 14 コミット）。
しかし統合検証により、**残存する赤 3 件 + 環境問題 1 件**が判明した。

| # | 検出事象 | 実測 | 深刻度 |
|:---|:---|:---|:---:|
| G-A | `frontend/src/lib/storage/indexedDbClient.ts` が存在しない | `useIndexedDbAutosave.ts:3` と `useCrashRecovery.ts:3` が import → **vitest 11 スイート失敗・tsc TS2307×2・本番ビルド不可** | **S1** |
| G-B | `tests/contract/test_planning_options_endpoint.py::test_new_spine_keys_have_expected_types` が赤 | `cards` がリスト化（F1 の仕様変更）されたのに旧契約テストが `isinstance(result[key], dict)` を主張 | S2 |
| G-C | `tests/regression/test_status_md_counts_match_reality.py::test_status_md_test_counts_match_reality` が赤 | `docs/STATUS.md:261` の「4件」表記が実測 5 件と不一致 | S3 |
| G-D | msw 2.15.0 ↔ @mswjs/interceptors 0.41.9 の ESM 解決失敗 | `node_modules/@mswjs/interceptors/lib/node/index.mjs` 欠落 → 3 スイート失敗 | 環境 |
| G-E | `frontend/tsconfig.json` の `moduleResolution: "node"` | react-router-dom v7 / reactflow の ESM exports が解決不可（tsc 25 エラー） | S2 |

**共通根因**: G-A は「Step 9 実装時にクライアントが import だけ書いて実装を置かずにコミットした」こと。
G-B/G-C は「仕様変更（cards リスト化・テスト追加）後に**同じ文書・契約を更新しなかった**」こと。

---

## 1. 原則（F2 計画から継承）

| 原則 | 内容 |
|:---|:---|
| **P1 修正とテストは同一コミット** | テストのない修正を残さない |
| **P4 反証テストを 1 本ずつ** | 修正前にそのテストが**実際に赤くなる**ことを確認する |
| **P5 猜測禁止** | 対象ファイルの行番号・関数名を必ず grep で確認してから編集する |
| **P6 1 ステップ = 1 コミット** | 失敗したら `git reset --hard HEAD~1` して次へ |
| **P2 完了判定は 1 行** | 「緑か赤か」のみ |

---

## 2. ステップ一覧

### G1. `frontend/src/lib/storage/indexedDbClient.ts` の新規作成【最優先】
- **対象ファイル**: `frontend/src/lib/storage/indexedDbClient.ts`（新規）
- **依存**: なし（**全作業の起点。11 スイートがここで緑になる**）
- **推定所要**: 30 分

**背景**

Step 9（IndexedDB オートセーブ・クラッシュリカバリ）の実装コミット（`891a7924` と履歴上の Step 9 作業）で
`useIndexedDbAutosave.ts` と `useCrashRecovery.ts` が
`import { indexedDbClient } from "../lib/storage/indexedDbClient"` を書いたが、
**実体ファイルを作らずにコミットした**。

**実測（レビュー時）**
```
npx vitest run         →  11 failed | 36 passed（テスト 158 は全部 collection error 前の残滓）
npx tsc --noEmit       →  TS2307 × 2（Cannot find module '../lib/storage/indexedDbClient'）
```

失敗する 11 スイート:
- `src/tests/workflow_promotion.test.tsx`
- `src/__tests__/routes.test.tsx`
- `tests/components/EditorRefinement.test.tsx`
- `tests/components/ExportPanel.test.tsx`
- `tests/components/StudioWorkspace.test.tsx`
- `tests/integration/entryPoints.test.tsx`
- `tests/integration/studioModeFlow.test.tsx`
- `src/components/editor/__tests__/ZenModeAndEditor.test.tsx`
- `tests/components/GeneratePanel.test.tsx`（msw 併発）
- `tests/api/easyMode.test.ts`（msw 併発）
- `tests/api/reversePlot.test.ts`（msw 併発）

**呼び出し側が要求するインターフェース（実測・grep 結果）**

| メンバー | 呼び出し側 | 型 |
|:---|:---|:---|
| `makeKey(bookId, episodeId)` | `useIndexedDbAutosave.ts:20` | `(string \| number, string \| number) => string` |
| `saveSnapshot(snapshot)` | `useIndexedDbAutosave.ts:27` | `(EditorSnapshot) => Promise<void>` |
| `getSnapshot(bookId, episodeId)` | `useCrashRecovery.ts:17` | `(string \| number, string \| number) => Promise<EditorSnapshot \| null>` |

**作業内容**

1. `frontend/src/lib/storage/indexedDbClient.ts` を新規作成する。
   - IndexedDB の DB 名: `autonovel-editor`、ストア名: `snapshots`、キー: `makeKey()` で生成
   - `EditorSnapshot` 型（`src/types/editorSnapshot.ts`）を使う
   - SSR / テスト環境（IndexedDB 未定義）では安全に reject する（console.warn 後 reject）
   - 失敗時は呼び出し側が catch して `setStatus("unsaved")` する設計のため、**投げっぱなしでよい**

2. **リグレッションテスト（先に作る）**: `frontend/tests/unit/lib/storage/indexedDbClient.test.ts`（新規）
   - `makeKey` が `bookId:episodeId` 形式のキーを返す
   - `saveSnapshot` → `getSnapshot` の往復が一致する（fake-indexeddb を使う）
   - IndexedDB 未定義環境で `getSnapshot` が `null` を返す（クラッシュしない）
   - `EditorSnapshot` の型が `src/types/editorSnapshot.ts` と一致していること（静的 import の成功自体が検証）

**検証コマンド**
```powershell
cd frontend; npx vitest run
```

**完了判定**: vitest が **failed 0**（msw 3 スイートを除く）。かつ `npx tsc --noEmit` で TS2307 × 2 が消える。

---

### G2. `tsconfig.json` の `moduleResolution` を `"bundler"` に変更
- **対象ファイル**: `frontend/tsconfig.json`（`:6`）
- **依存**: なし（G1 と並列可）
- **推定所要**: 10 分

**背景**

`moduleResolution: "node"`（Node10 流・`package.json` の `main` のみ見る）では、
react-router-dom v7 / reactflow が `exports` フィールドで公開する ESM エントリが解決できない。

**実測（レビュー時）**
```
npx tsc --noEmit  →  25 errors
  src/App.tsx(2,10): TS2305: Module '"react-router-dom"' has no exported member 'BrowserRouter'.
  src/components/branches/BranchEdge.tsx(2,10): TS2614: Module '"reactflow"' has no exported member 'EdgeProps'.
  ...
```
全て `moduleResolution: "node"` が原因の「型だけ見えていない」エラーである。

**作業内容**

1. `frontend/tsconfig.json:6` の `"moduleResolution": "node"` を `"bundler"` に変更する。

2. **リグレッションテスト（先に作る）**: CI に型チェックを組み込む（G5 で実施）。
   本ステップの検証は `npx tsc --noEmit` のエラー数そのもので判定する。

**検証コマンド**
```powershell
cd frontend; npx tsc --noEmit
```

**完了判定**: `npx tsc --noEmit` が **0 errors**（G1 の TS2307 × 2 も消えていること）。
ただし `src/components/wizard/Step1PlotInput.test.tsx` の TS2732（resolveJsonModule）が残る場合は
併せて `"resolveJsonModule": true` を追加する。

---

### G3. `tests/contract/test_planning_options_endpoint.py` の旧契約主張を現形状に追従
- **対象ファイル**: `tests/contract/test_planning_options_endpoint.py`（`:31-38`）
- **依存**: なし
- **推定所要**: 15 分

**背景**

F1 コミット（`7de64451`）で `misc.py` の `cards` は **dict → リスト** に変更された
（`card_id` を各カードに付与するため。`test_planning_options_contract.py:34` が
`isinstance(cards, list)` を主張）。

しかし旧契約テスト `test_planning_options_endpoint.py:31-38` は
`isinstance(result[key], dict)` のままで、**仕様変更に追従していない**。

**実測（レビュー時）**
```
FAILED tests/contract/test_planning_options_endpoint.py::test_new_spine_keys_have_expected_types
E   AssertionError: 'cards' は dict であるべき
E   assert False
```

**作業内容**

1. `test_new_spine_keys_have_expected_types` を修正する:
   - `cards` は **list** であるべき（F1 の契約）と主張する
   - その他のキー（`lengths` / `markets` / `patterns` / `genres` / `beat_vocabulary`）は dict
   - **cards の中身が `card_id` を持つこと**まで検証する（`test_planning_options_contract.py` との二重確認）

2. **反証テストの確認**: 修正前に現状で赤であることを既に実測済み（上記）。

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\contract\test_planning_options_endpoint.py -q
```

**完了判定**: `tests/contract/test_planning_options_endpoint.py` が **7 passed / 0 failed**。

---

### G4. `docs/STATUS.md` の自己申告件数を実測に合わせる
- **対象ファイル**: `docs/STATUS.md`（`:261`）
- **依存**: なし
- **推定所要**: 5 分

**背景**

R8 コミット（`5155bef9`）で `test_resolver_no_llm.py` に
`test_no_llm_fixture_is_not_vacuous` を追加し、テスト数が 4 → 5 になった。
しかし `docs/STATUS.md:261` の「**4件**緑」表記が更新されていない。

**実測（レビュー時）**
```
FAILED tests/regression/test_status_md_counts_match_reality.py::test_status_md_test_counts_match_reality
E   tests/unit/story_spine/test_resolver_no_llm.py: 記載 4 件 / 実測 5 件
```

**メタテストが正しく機能している証拠**。文書の陳腐化を detect できている。

**作業内容**

1. `docs/STATUS.md:261` の「**4件**緑」を「**5件**緑」に修正する。

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\regression\test_status_md_counts_match_reality.py -q
```

**完了判定**: `tests/regression` が **888 passed / 0 failed**（メタテスト込み）。

---

### G5. 統合検証（最終ゲート）
- **対象**: 全ゲートの再実行
- **依存**: G1〜G4
- **推定所要**: 15 分

**検証コマンド**
```powershell
# H0〜H2 相当
C:\Python314\python.exe -m pytest tests/regression tests/unit/story_spine tests/unit/story_spine_wiring -q
C:\Python314\python.exe -m pytest tests/contract tests/e2e/test_spine_end_to_end.py tests/unit/scripts -q

# H3 相当
cd frontend; npx vitest run

# 型チェック
cd frontend; npx tsc --noEmit
```

**完了判定**: 全ゲートが緑。

---

## 3. リグレッション防止テスト計画

| テスト | ステップ | 防止する回帰 |
|:---|:---:|:---|
| `frontend/tests/unit/lib/storage/indexedDbClient.test.ts`（新規） | G1 | 「import だけ書いて実装を置かない」状態の再発。**実体ファイルの削除・欠落を collection error ではなく意味論で検出する** |
| CI への `tsc --noEmit` 組み込み | G2/G5 | 「型が解決しないモジュール」が本番ビルドを壊すことの事前検出 |
| `test_new_spine_keys_have_expected_types` の強化（card_id 検証追加） | G3 | 契約テスト同士の矛盾（dict vs list）の再発 |
| `tests/regression/test_status_md_counts_match_reality.py`（既存） | G4 | 文書の自己申告数値の陳腐化 |

---

## 4. 実行順序

```
  ┌─────────────────────────────────────────────────────┐
  │ G1 indexedDbClient.ts 新規作成【最優先】            │ ← ここが本番を壊す欠陥
  │ G2 tsconfig moduleResolution 変更（並列可）          │
  └───────────────────────┬─────────────────────────────┘
                          │ Gate: vitest failed 0 / tsc 0 errors
                          ▼
  ┌─────────────────────────────────────────────────────┐
  │ G3 契約テスト追従                                  │
  │ G4 STATUS.md 件数修正                               │
  └───────────────────────┬─────────────────────────────┘
                          ▼
  ┌─────────────────────────────────────────────────────┐
  │ G5 統合検証（全ゲート再実行）→「完成形」判定        │
  └─────────────────────────────────────────────────────┘
```

---

## 5. 前提文書との差分

F2 計画は「13 ステップで S1 8 件を消除する」計画だった。**実装は完了した**。
本計画は「その後の統合検証で見つかった**最後の赤 3 件 + 環境問題 1 件**」を消除する。

F2 計画に無かった視点:
1. **フロントエンドの型チェック（tsc）がゲートに無かった** → G2/G5 で追加
2. **リグレッションテストが collection error でしか検出できない** → G1 の新規テストで意味論検出に
3. **契約テスト同士が矛盾している可能性**（旧 endpoint テスト vs 新 contract テスト）→ G3 で統一
