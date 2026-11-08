# テストゲート運用ポリシー

本ドキュメントは AutoNovel のテストゲート（CI 上の必須チェック）の
状態定義と語彙を統一するものである。

## ゲートの状態（3値のみ）

| 状態 | 意味 | 条件 |
|---|---|---|
| `green` | ゲート有効。ブランチ保護の必須条件。 | failed 数 = 0 |
| `red` | 未修正の欠陥がある。修正が必要。 | failed 数 > 0 |
| `未達` | ゲート化が未完了。「観測」ではない。 | `continue-on-error: true` かつ failed 数 > 0 |

**重要**: `未達` は「観測（observe）」「許容範囲」「known failure」などの
緩和語で呼び換えてはならない。`未達` は未達と書く。

## 禁止語

以下の語はゲート状態の説明に使用してはならない。
- 「観測」「observing」「observe モード」
- 「既知失敗」「known failure」
- 「許容範囲」「acceptable range」
- 「一時的な赤」「暫定的な green」
- 「未達だが進行可」

## 解除条件（未達 → green）

次のすべてを満たすこと。

1. `tests/integration` の failed 数が 0 であること（CI 上で実測）。
2. 収集エラー（SyntaxError 等）が 0 件であること。
3. `.github/workflows/ci.yml` の統合テストジョブが
   `continue-on-error: false` になっていること。
4. そのジョブ名に `observe`（観測）という語が含まれていないこと。

## 失敗数ラケット

`config/integration_failure_baseline.json` に
- `max_failed`: 許容する最大 failed 数（ゲート化後は 0）
- `known_failures`: 既知失敗のリスト（ゲート化後は空配列 `[]`）

が定義されている。`known_failures` が空でない状態は「未達」を意味する。
`max_failed` を増やすことは絶対に許可しない。どうしても緑にできない場合は
`continue-on-error: true` に戻し、本ドキュメントの状態を `未達` と明記する。

## 関連ファイル

- `plans/PLAN_GATE_INTEGRATION_24STEPS.md`: 統合テスト緑化とゲート化の24ステップ計画
- `.github/workflows/ci.yml`: CI 設定（統合テストジョブ）
- `config/integration_failure_baseline.json`: 失敗数ラケットの基準
- `tests/regression/test_gate_policy_docs.py`: 本ポリシーの文言遵守テスト
