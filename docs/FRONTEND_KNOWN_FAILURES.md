# フロントエンドの既知テスト失敗（実測記録）

- **文書ID**: `FRONTEND_KNOWN_FAILURES`
- **作成日**: 2026-10-02
- **出典計画**: [`PLAN_H1R_POST_REVIEW_REMEDIATION_10STEPS.md`](../plans/PLAN_H1R_POST_REVIEW_REMEDIATION_10STEPS.md) H1R-4
- **測定コマンド**: `cd frontend && npm run test:ci`

## 0. この文書の存在的理由

`npm run test:ci` は **6 files / 9 tests 失敗**（2026-10-02 実測）であり、
**coverage レポートが生成されない**ため閾値 gate（50%）には到達しない。

**推測で書かない**ため、失敗メッセージは実際に観測したものをそのまま載せる。
なお本計画作成時点では **9 件のうち 2 件が H1 自身の原因**であり
（`tests/api/graph.test.ts`）、H1R-2 で修正済み。残る **7 件は H1 原因ではない**。

## 1. 基準値（2026-10-02 実測）

```
Test Files  6 failed | 62 passed (68)
Tests       9 failed | 350 passed (359)
Duration    約 300s
```

| 状態 | files | tests |
|:---|:---|:---|
| H1 完了時点 | 6 failed | **9 failed** |
| H1R-2 完了時点（2026-10-02 実測） | **5 failed** | **7 failed** |

```
# H1R-2 完了時点の実測出力
Test Files  5 failed | 64 passed (69)
Tests       7 failed | 357 passed (364)
```

残る 7 件は §3 の FE-1〜FE-5 に対応し、すべて H1 原因ではない。

## 2. H1 原因（修正済み）

| ファイル | 件数 | 原因 | 対応 |
|:---|:---|:---|:---|
| `tests/api/graph.test.ts` | 2 | H1 Step H8 が `graph.ts` の生 `fetch(` を `apiFetch(` に移行したが、テストが `toHaveBeenCalledWith(url)`（第 1 引数のみ）で検査していた。`apiFetch` は必ず第 2 引数を付ける | H1R-2 で `expect.objectContaining({ headers: expect.any(Headers) })` に修正。あわせて `Authorization: Bearer` 注入を検証。`frontend/tests/unit/apiFetchContract.guard.test.ts` で再発を防止 |

**実測した検証方法**: `git checkout 5b4c0563~1 -- frontend/src/api/graph.ts` にして
再実行すると **1 passed** に戻る（= H1 が原因であることの証明）。

## 3. 既存失敗（H1 原因ではない・未修正）

いずれも **UI 側が変わり、テストの期待値が古くなった** タイプ。
「テストが古い」のか「実装が壊れている」のかを 1 件ずつ実測する必要があるため、
本計画（H1R）の範囲外とする。

| # | ファイル | 件数 | 実測した失敗メッセージ | 推定原因（未検証） |
|:---|:---|:---|:---|:---|
| FE-1 | `tests/unit/uiux/persistFailureNotification.test.tsx` | 3 | `Unable to find an element with the text: Sample 2` / `expect(element).toHaveTextContent()` / `expect(element).not.toBeInTheDocument()` | ロールバック UI の DOM 構成が変わった |
| FE-2 | `tests/components/EditorRefinement.test.tsx` | 1 | `Unable to find an element with the text: 第1話 運命の剣` | 章タイトル表示の DOM が変わった |
| FE-3 | `src/components/generate/SimpleModePanel.test.tsx` | 1 | `Unable to find an element with the display value: hot_blooded` | `style_key` の選択肢一覧が変わった |
| FE-4 | `tests/unit/uiux/wizardStep3Editing.test.tsx` | 1 | `expect(window.localStorage.getItem("autonovel.wizard.draft.7")).toBe(...)` が `null` | 下書きの永続化キーまたはタイミングが変わった |
| FE-5 | `tests/unit/uiux/chapterPersistence.test.ts` | 1 | `expected "spy" to be called with arguments: [ '/api/episodes/chapters/1/3', …(1) ]` | H8 revert でも赤 = **H1 原因ではない**（API クライアントの呼び出し形状が変わった可能性） |

**合計 7 件**。

## 4. 次に何をすべきか（判断は保留）

FE-1〜FE-5 を直すには、**各テストが「古い期待値」なのか「実装の退行」なのかを
1 件ずつ実測**する必要がある。推測で Expect を書き換えると、
真の退行をテストで隠すことになる（本計画 §4「やらないこと」と同じ理由）。

推奨する順序（別計画で着手する場合）:
1. FE-1（3 件・最大）。ロールバック UI は本番要件に直結するため優先度が高い。
2. FE-5（1 件）。API クライアントの契約変更なので、
   `tests/regression/test_H1_fe_api_call_contract.py` 系の契約テストを先に作る。
3. FE-2 / FE-3 / FE-4（各 1 件）。

## 5. 参考: フェイクの archangel を足さないこと

FE-1〜FE-5 は「archangel で検出する」種類の問題ではない。
archangel は**공간的に連続する同じ間違いの再発**を防ぐもので、
**個々の期待値の陳腐化**は検出できない（PLAN_H1R §4 に記載）。