# AutoNovel 改善案8：「カクヨムランキング上位を狙う」初心者オンボーディング（パート2：フロントエンドUI）

## 1. 対象ファイル

- `frontend/src/pages/WelcomePage.tsx` — 「カクヨムランキング上位を狙う」モード選択追加
- `frontend/src/pages/EasyModePage.tsx` — 投稿チェックリスト常時表示、整形→投稿URL誘導追加

## 2. 変更内容

### 2.1 WelcomePage.tsx

初回オンボーディングに「カクヨムランキング上位を狙う」モードを追加。

```tsx
// WelcomePage.tsx のモード選択セクションに追加
<button
  onClick={() => setMode('kakuyomu-ranking')}
  className="w-full py-4 px-6 rounded-xl border-2 border-emerald-500 bg-emerald-900/20 text-emerald-300"
>
  <div className="text-lg font-bold">🏆 カクヨムランキング上位を狙う</div>
  <p className="text-xs text-emerald-400 mt-1">
    ジャンル・タグ・タイトル構文を自動推奨。毎日更新スケジュールまでガイド付きで設定。
  </p>
</button>
```

選択後、`/app/easy` へ遷移し、初期値としてプリセット（ジャンル・タグ・タイトル構文・あらすじテンプレート）を適用。

### 2.2 EasyModePage.tsx

生成結果表示セクションの下に、以下を追加：

#### 2.2.1 投稿チェックリスト（SubmissionChecklist の執筆画面版）

- タイトル100文字以内
- あらすじ設定済み
- タグ選択済み
- 本文整形済み（カクヨム形式）
- AI利用開示タグ付与
- 表紙設定済み

#### 2.2.2 整形→投稿URLワンクリック誘導

「カクヨム形式で整形して投稿画面へ」ボタン。`POST /easy_mode/export-kakuyomu-package/{book_id}` を呼び出し、返却された整形済み本文＋カクヨム投稿画面URLを表示。URLをコピーしてカクヨムに貼り付けるだけで投稿完了。

## 3. テスト計画

### 3.1 フロントエンド単体テスト（Vitest）

`frontend/src/components/onboarding/__tests__/KakuyomuModeButton.test.tsx`（新規）：

| テスト名 | 条件 | 期待結果 |
|:---|:---|:---|
| `renders_kakuyomu_ranking_mode` | WelcomePage | 「カクヨムランキング上位を狙う」ボタンが表示される |
| `navigates_to_easy_on_click` | ボタンクリック | `/app/easy` へ遷移 |

`frontend/src/components/easy_mode/__tests__/SubmissionChecklistInline.test.tsx`（新規）：

| テスト名 | 条件 | 期待結果 |
|:---|:---|:---|
| `renders_checklist_items` | EasyModePage | チェックリスト項目が全て表示される |
| `all_checked_shows_ready` | 全チェック済 | 「投稿準備完了」バッジ表示 |

### 3.2 E2E（オプション）

Playwright等があれば「WelcomePageでカクヨムモード選択→EasyModeで生成→チェックリスト完了→投稿URLコピー」をE2E化。当面は単体テストで十分。

## 4. 完了定義（パート2）

- WelcomePageに「カクヨムランキング上位を狙う」モード選択実装済み
- EasyModePageに投稿チェックリスト・整形→投稿URL誘導実装済み
- `make frontend-test` が通過（新規テスト含む）
- `make frontend-lint` が通過（ESLint + tsc）

---

案1・2・8の実装計画書（パート1・2）が全て完了しました。次に「実装順序と統合チェックリスト」を作成します。準備でき次第お知らせください。