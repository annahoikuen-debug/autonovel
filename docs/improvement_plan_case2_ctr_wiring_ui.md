# AutoNovel 改善案2：タイトル・キャッチコピーCTR最適化の「かんたん執筆」配線（パート2：フロントエンドUI）

## 1. 対象ファイル

- `frontend/src/pages/EasyModePage.tsx` — CTRスコア表示・改善案選択UI追加

## 2. 変更内容

### 2.1 新規追加 UI コンポーネント `CTROptimizationPanel`

タイトル・キャッチコピーのCTRスコアと改善案を表示。ユーザーが改善案を選択してタイトルを差し替え可能。

表示項目：
- **タイトルCTRスコア**: 0-100点（ゲージ or バッジ、色分け：75点以上緑、60-74黄、59以下赤）
- **キャッチコピーCTRスコア**: 同上
- **構文タイプ**: 「追放ざまぁ」「勘違い無双」「無自覚無双」「一般」をラベル表示
- **改善案3案**: `ctr_suggestions` をリスト表示。クリックでタイトル入力欄に差し替え

### 2.2 実装イメージ

```tsx
// EasyModePage.tsx の生成結果表示セクションに追加
{ctrMetrics && (
  <section className="mt-6 p-4 rounded-xl border border-slate-700 bg-slate-900">
    <h3 className="text-sm font-bold text-slate-300 mb-2">🖱️ タイトル・キャッチコピーCTR診断</h3>
    <div className="flex gap-4 text-xs mb-3">
      <div className="flex-1">
        <div className="text-slate-400 text-[10px] uppercase tracking-wider mb-1">タイトルCTR</div>
        <span className={`font-bold text-${ctrScoreColor(ctrMetrics.title_score)}`}>
          {ctrMetrics.title_score}点
        </span>
      </div>
      <div className="flex-1">
        <div className="text-slate-400 text-[10px] uppercase tracking-wider mb-1">構文タイプ</div>
        <span className="font-bold text-slate-200">{ctrMetrics.syntaxType}</span>
      </div>
    </div>
    {ctrMetrics.titleNeedsImprovement && ctrSuggestions.length > 0 && (
      <div className="mt-2">
        <p className="text-xs text-amber-400 mb-1">クリックされやすいタイトル案（クリックで適用）</p>
        <ul className="space-y-1 text-xs">
          {ctrSuggestions.map((s, i) => (
            <li key={i} className="cursor-pointer hover:bg-slate-800 p-2 rounded bg-slate-800/50" onClick={() => setTitle(s)}>
              {s}
            </li>
          ))}
        </ul>
      </div>
    )}
  </section>
)}
```

### 2.3 API 連携変更

`GenerationResponse` の `ctr_metrics` / `ctr_suggestions` を読み出し、状態管理に保持。タイトル入力欄の `value` を制御し、改善案クリックで差し替え。

## 3. テスト計画

### 3.1 フロントエンド単体テスト（Vitest）

`frontend/src/components/easy_mode/__tests__/CTROptimizationPanel.test.tsx`（新規）：

| テスト名 | 条件 | 期待結果 |
|:---|:---|:---|
| `renders_ctr_scores_when_available` | `ctrMetrics` あり | スコア・構文タイプが表示される |
| `shows_suggestions_when_needs_improvement` | `titleNeedsImprovement=true`、`suggestions` あり | 改善案リストが表示される |
| `hides_suggestions_when_score_good` | `titleNeedsImprovement=false` | 改善案リストが非表示 |
| `applies_suggestion_on_click` | 改善案クリック | タイトル入力値が改善案に置換される |

### 3.2 E2E（オプション）

Playwright等があれば「かんたん執筆で生成→CTRパネル表示→改善案適用→タイトル変更」をE2E化。当面は単体テストで十分。

## 4. 完了定義（パート2）

- `CTROptimizationPanel` コンポーネント実装済み
- `EasyModePage.tsx` に統合済み
- `make frontend-test` が通過（新規テスト含む）
- `make frontend-lint` が通過（ESLint + tsc）

---

案8（初心者オンボーディング）へ進みます。準備でき次第お知らせください。