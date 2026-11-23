# AutoNovel 改善案1：序盤フックエンジン配線（パート2：フロントエンドUI）

## 1. 対象ファイル

- `frontend/src/pages/EasyModePage.tsx` — フックメトリクス表示セクション追加

## 2. 変更内容

### 2.1 既存 `EasyModePage.tsx` の構造確認

生成完了後、本文・次話提案・ZIPダウンロードを表示するページ。`GenerationResponse` の `output` / `suggestions` / `task_id` を利用。

### 2.2 新規追加 UI コンポーネント `HookMetricsPanel`

生成されたエピソードが1-3話かつフック採点結果がある場合に表示。

表示項目：
- **冒頭フック判定**: `crisis / shocking_truth / triumph_trigger / peaceful`
- **スコア**: 0-100点（数値ゲージ or バッジ）
- **章末引き**: `requires_rewrite` に応じて「引き OK」/「引き要改善」を表示
- **改善指令**: `requires_rewrite=true` 時、「章末を危機/衝撃/反撃で締める」旨を赤色テキストで表示

### 2.3 実装イメージ

```tsx
// EasyModePage.tsx の生成結果表示セクションに追加
{book.epNum <= 3 && hookMetrics && (
  <section className="mt-6 p-4 rounded-xl border border-slate-700 bg-slate-900">
    <h3 className="text-sm font-bold text-slate-300 mb-2">🪝 序盤フック・章末引き診断</h3>
    <div className="flex gap-3 text-xs mb-2">
      <span className={`px-2 py-1 rounded bg-${scoreColor} text-white`}>
        {hookMetrics.hookTypeLabel}（{hookMetrics.score}点）
      </span>
      {hookMetrics.requiresRewrite ? (
        <span className="px-2 py-1 rounded bg-amber-600 text-white">引き要改善</span>
      ) : (
        <span className="px-2 py-1 rounded bg-emerald-600 text-white">引き OK</span>
      )}
    </div>
    {hookMetrics.requiresRewrite && (
      <p className="text-xs text-slate-400 italic">
        {hookMetrics.reason}
      </p>
    )}
  </section>
)}
```

### 2.4 API 連携変更

`apiFetch` 等で `GenerationResponse` を取得する箇所に `hook_metrics` フィールドを読み出し、状態管理（`useState`）に保持。

## 3. テスト計画

### 3.1 フロントエンド単体テスト（Vitest）

`frontend/src/components/easy_mode/__tests__/HookMetricsPanel.test.tsx`（新規）：

| テスト名 | 条件 | 期待結果 |
|:---|:---|:---|
| `renders_hook_metrics_when_available` | `hookMetrics` あり、epNum=1 | スコア・判定テキストが表示される |
| `hides_when_ep_4_or_above` | `hookMetrics` あり、epNum=4 | パネルが非表示 |
| `shows_rewrite_warning` | `requires_rewrite=true` | 「引き要改善」バッジ + 指令テキスト |
| `shows_ok_when_no_rewrite` | `requires_rewrite=false` | 「引き OK」バッジのみ |

### 3.2 E2E（オプション）

Playwright等があれば「かんたん執筆で1話生成→フックパネル表示」をE2E化。当面は単体テストで十分。

## 4. 完了定義（パート2）

- `HookMetricsPanel` コンポーネント実装済み
- `EasyModePage.tsx` に統合済み
- `make frontend-test` が通過（新規テスト含む）
- `make frontend-lint` が通過（ESLint + tsc）

---

案2（CTR最適化配線）パート1へ進みます。準備でき次第お知らせください。