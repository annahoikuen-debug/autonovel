# AutoNovel 商業ランディングページ 実装計画書（フェーズ３：ステップ25〜36）

**フェーズ名**: パフォーマンス・テスト・デプロイ・運用  
**対象ステップ**: 25〜36（全36ステップのうち第3フェーズ）  
**目的**: LPのパフォーマンスを最適化し、テスト・品質ゲートを通過させ、本番デプロイ・モニタリングまで完了させる。  
**前提条件**: フェーズ２（ステップ13〜24）が完了し、LPのすべてのセクション・SEO・アクセシビリティが実装済みであること。

---

## ステップ25: 画像最適化（WebP変換・遅延読み込み・preload）

### 目的
ページの総サイズを削減し、LCP（最大コンテンツ描画）を2.5秒以内に抑える。

### 詳細実装内容
**画像フォーマット変換**:
- すべての画像をWebP形式に変換（SVGはSVGOで最適化）
- フォールバック用に元の形式も保持（`<picture>` タグまたは `srcSet` でWebP優先読み込み）
- `frontend/public/images/` に最適化済み画像を配置

**遅延読み込み（Lazy Loading）**:
- ファーストビュー（Hero）以外の画像に `loading="lazy"` を設定
- Intersection Observer でビューポート進入時に読み込み

**プリロード（Preload）**:
- Heroビジュアル画像に `<link rel="preload" as="image">` を設定
- 重要なWebフォント（もし使用する場合）にも `rel="preload"`

**幅・高さ属性**:
- すべての `` に `width` と `height` を明記し、CLS（累積レイアウトシフト）を防止
- アスペクト比ボックス（`aspect-video` または `aspect-square`）を併用

**データテストID**:
- `lp-image-hero`, `lp-image-ogp`, `lp-image-avatar-1/2/3` など

### 納品物
- `frontend/public/images/` に最適化済み画像（WebP / SVG）
- `frontend/src/components/lp/` の各コンポーネントで `loading`、`width`、`height` を設定

### 品質基準
- 合計ページサイズ（gzip後）が1.5MB以下。
- LCP < 2.5秒（PageSpeed Insights / Lighthouse 測定）。
- CLS < 0.1。

---

## ステップ26: フォント最適化（システムフォントスタック・FOIT/FOUT対策）

### 目的
Webフォントの読み込みブロックを避け、テキストの早期描画を実現する。

### 詳細実装内容
**システムフォントスタックの徹底**:
- Webフォントは使用せず、ステップ2で定義したシステムフォントスタックを使用
- `font-display: swap` をCSSで明示（フォント読み込み中は代替フォントを表示）

**FOIT/FOUT対策**:
- `@font-face` を使用する場合は `font-display: optional` または `swap`
- `font-loading` プロパティでブロック時間を制御

**日本語フォントフォールバック**:
- `system-ui` → `-apple-system` → `BlinkMacSystemFont` → `Segoe UI` → `Roboto` → `Hiragino Kaku Gothic ProN` → `Hiragino Sans` → `Meiryo` → `sans-serif`
- 文字化けや豆腐文字（□）が出ないフォント順序を維持

### 納品物
- `frontend/src/assets/lp-tokens.css` に `font-display: swap` を追記
- `frontend/tailwind.config.js` の `fontFamily.sans` をシステムフォントスタックに固定

### 品質基準
- Webフォント読み込みによるテキストの非表示時間（FOIT）が0秒。
- ページ初期描画時にテキストが即座に表示されること。

---

## ステップ27: アニメーション実装（フェードイン・スライド・ホバー）

### 目的
LP全体に商業的な滑らかさを与えつつ、過剰な動きを避け、読みやすさを優先する。

### 詳細実装内容
**ページロードアニメーション**:
- `staggerContainer` と `fadeInUp` でセクションを順次フェードイン
- HeroSection → EntryPointsSection → FeaturesSection → PricingSection → TestimonialsSection → FaqSection → FinalCtaSection の順に0.1秒ずつ遅延

**スクロール連動アニメーション**:
- `whileInView` または Intersection Observer で、ビューポートに入ったセクションをフェードイン
- `viewport: { once: true }` で1回のみアニメーション（スクロール戻しでも繰り返さない）

**ホバーアニメーション**:
- ボタン: `whileHover={{ scale: 1.02 }}`、`whileTap={{ scale: 0.98 }}`
- カード: `whileHover={{ y: -4 }}`、`whileHover={{ boxShadow: '0 20px 25px -5px rgb(0 0 0 / 0.1)' }}`
- リンク: `whileHover={{ x: 4 }}`（微細な右スライド）

**過剰動きの回避**:
- 3秒以上続くループアニメーションは避ける
- 自動再生のカルーセルは使用しない（ユーザー操作のみ）

### 納品物
- `frontend/src/components/lp/` の各セクションにFramer Motionアニメーションを適用（既存ファイルを編集）

### 品質基準
- アニメーション総時間は1.5秒以内で完了。
- ユーザー操作を妨げない（ボタン押下中のアニメーションは即座に反応）。

---

## ステップ28: 減動設定対応（prefers-reduced-motion）

### 目的
vestibular障害や動きに敏感なユーザーに配慮し、アニメーションを無効化する。

### 詳細実装内容
**CSSメディアクエリ**:
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

**Framer Motion 対応**:
- `useReducedMotion` フックを使用し、減動設定時はアニメーションを無効化
- `motion` コンポーネントの `animate` を条件付きで適用

### 納品物
- `frontend/src/assets/lp-tokens.css` に `prefers-reduced-motion` 設定を追記
- `frontend/src/lib/lp/motion.ts` の `reducedMotion` バリアントを各コンポーネントで適用

### 品質基準
- OSの「動きを減らす」設定時に、すべてのアニメーションが即座に完了（または無効化）。
- コンテンツの可読性・操作性に影響しないこと。

---

## ステップ29: アクセシビリティ詳細対応（ARIA・フォーカス・コントラスト）

### 目的
WCAG 2.1 AAレベルのアクセシビリティをすべてのLPコンポーネントで満たす。

### 詳細実装内容
**すべてのコンポーネントに以下を適用**:

**ARIAラベル**:
- ボタン: テキストがない場合は `aria-label`（例:ハンバーガーメニュー）
- リンク: 文脈だけで分かるリンクテキスト、または `aria-label`
- 画像: 情報画像は説明的な `alt`、装飾画像は `alt=""`
- アコーディオン（FAQ）: `aria-expanded`、`aria-controls`、`role="button"`

**フォーカス管理**:
- `:focus-visible` で `ring-2 ring-brand-accent ring-offset-2 ring-offset-brand-dark`
- モーダル・ドロワーがある場合はフォーカストラップ

**見出し階層**:
- `h1`（Hero） → `h2`（セクション見出し） → `h3`（カードタイトル等）の順序を厳守

**色コントラスト検証**:
- テキスト対背景: 4.5:1 以上
- 大文字: 3:1 以上
- UIコンポーネント: 3:1 以上

### 納品物
- `frontend/src/components/lp/` の各コンポーネントにARIA属性・フォーカススタイルを追加（既存ファイルを編集）

### 品質基準
- axe-core または Lighthouse アクセシビリティ監査で違反 0 件。
- スクリーンリーダー（NVDA / VoiceOver）で主要操作（CTAクリック、FAQ開閉、ナビゲーション）が可能。

---

## ステップ30: キーボードナビゲーション・タブ順序最適化

### 目的
マウスを使わないユーザーもすべての操作をキーボードだけで完結できるようにする。

### 詳細実装内容
**タブ順序の論理的配置**:
- ヘッダー（ロゴ → ナビゲーション → CTA）→ メインコンテンツ（セクション順）→ フッター
- `tabindex` は原則として `0` または省略（自然なDOM順序を尊重）
- 不要な `tabindex={-1}` や `tabindex={1,2,3...}` は避ける

**フォーカス表示**:
- すべてのフォーカス可能要素にフォーカスリングを可視化

**スキップリンク**（オプション）:
- ページ先頭に「コンテンツへスキップ」リンクを設置し、キーボードユーザーが繰り返しのナビゲーションをスキップ可能にする

### 納品物
- `frontend/src/components/lp/LpHeader.tsx` 等にキーボード操作対応を実装（既存ファイルを編集）
- 必要に応じてスキップリンクコンポーネントを新規作成

### 品質基準
- Tabキーでページ上のすべてのインタラクティブ要素に順次フォーカスが移動すること。
- フォーカスがコンテンツ外に逸脱しないこと。

---

## ステップ31: 単体テスト実装（Vitest + React Testing Library）

### 目的
各コンポーネントの動作を自動検証し、リグレッションを防ぐ。

### 詳細実装内容
**テストファイル作成**（`frontend/src/components/lp/*.test.tsx`）:

| コンポーネント | テスト内容 |
|--------------|-----------|
| `LpHeader` | ロゴ・ナビリンク・CTAボタンがレンダリングされ、クリックでハンドラが発火 |
| `HeroSection` | H1・サブ見出し・CTA2つが表示され、CTAクリックでナビゲーションイベント |
| `EntryPointsSection` | 3つの入口カードが表示され、各CTAクリックで対応パスへ遷移 |
| `FeatureCard` | アイコン・タイトル・説明が正しく表示 |
| `PricingCard` | 価格・機能リスト・CTAが正しく表示 |
| `FaqItem` | アコーディオンの開閉状態切替 |
| `LpFooter` | 著作権・法務リンク・ソーシャルリンクが表示 |

**テスト実行**:
```
npm run test -- --reporter=verbose
```

**カバレッジ目標**: LPコンポーネント 80% 以上

### 納品物
- `frontend/src/components/lp/*.test.tsx`（各コンポーネントのテストファイル）

### 品質基準
- すべての単体テストが合格（`vitest run` でエラーなし）。
- `data-testid` を使用した要素取得でテストを堅牢にする（クラス名変更に影響されない）。

---

## ステップ32: E2Eテスト実装（Playwright）

### 目的
ブラウザレベルで主要ユーザーフローを自動検証する。

### 詳細実装内容
`frontend/tests/e2e/lp.spec.ts` を新規作成：

**テストシナリオ**:

| シナリオ | 手順 | 期待結果 |
|---------|------|---------|
| LP表示 | `/` にアクセス | ヒーローH1が表示される |
| CTAクリック→登録 | ヒーローのプライマリCTAクリック | `/register` または `/welcome` に遷移 |
| 入口カードクリック | 3つの入口カードを順にクリック | 各対応ページ（`/`, `/wizard`, `/studio` または `/welcome`）に遷移 |
| FAQ開閉 | FAQアイテムクリック | 回答が表示/非表示に切替 |
| モバイル表示 | ビューポート375pxでアクセス | レイアウト崩れなし、CTAボタンタップ可能 |
| キーボードナビ | Tabキーでフォーカス移動 | すべてのインタラクティブ要素に順次フォーカス |

**実行**:
```
npm run test:e2e
```

### 納品物
- `frontend/tests/e2e/lp.spec.ts`（新規作成）

### 品質基準
- すべてのE2Eシナリオが合格。
- モバイル・デスクトップ両方でテストが通ること。

---

## ステップ33: パフォーマンス監査（Lighthouse / PageSpeed Insights）

### 目的
Core Web Vitalsを測定し、目標値を達成する。

### 詳細実装内容
**測定項目**:
- LCP（最大コンテンツ描画）: < 2.5秒
- CLS（累積レイアウトシフト）: < 0.1
- INP（インタラクション・トゥ・ネクストペイント）: < 200ms
- TTFB（最初のバイトまでの時間）: < 600ms
- 合計ページサイズ: < 1.5MB（gzip後）
- リクエスト数: < 50件

**測定ツール**:
- Lighthouse（Chrome DevTools または CLI）
- PageSpeed Insights（公開URL後）
- WebPageTest（オプション）

**改善対応**:
- 未使用CSSの削除（TailwindのPurgeCSS）
- JavaScriptのコード分割（セクションごとに動的インポート）
- 画像のWebP化・遅延読み込み（ステップ25）

### 納品物
- Lighthouseレポート（PDFまたはJSON、`plans/` または `reports/` に保存）
- パフォーマンス改善メモ

### 品質基準
- Lighthouse スコア: 性能 90 以上、アクセシビリティ 95 以上、SEO 90 以上、ベストプラクティス 90 以上。
- Core Web Vitals すべて目標値達成。

---

## ステップ34: ビジュアルリグレッション・クロスブラウザ確認

### 目的
主要ブラウザ・デバイスでレイアウト崩れがないことを確認する。

### 詳細実装内容
**確認ブラウザ**:
- Chrome（最新）、Safari（最新）、Firefox（最新）、Edge（最新）

**確認デバイス**:
- iPhone Safari（iOS最新）
- Android Chrome（最新）
- iPad Safari（タブレット）

**確認項目**:
- レイアウト崩れ（はみ出し、重なり、文字化け）
- 画像表示（WebP対応ブラウザ・未対応ブラウザ）
- アニメーション動作
- フォント表示（システムフォントフォールバック）

**ツール**:
- Playwright スクリーンショット比較（オプション）
- BrowserStack または実機での手動確認

### 納品物
- クロスブラウザ確認チェックリスト（`plans/` または `reports/` に保存）
- スクリーンショット証拠（必要に応じて）

### 品質基準
- すべてのブラウザ・デバイスでレイアウト崩れがないこと。
- 主要機能（CTAクリック、FAQ開閉、ナビゲーション）がすべての環境で動作すること。

---

## ステップ35: 品質ゲート・受入基準確認

### 目的
本番リリース前にすべての品質基準をクリアしているか最終確認する。

### 詳細実装内容
**チェックリスト**:

| カテゴリ | 基準 | 判定ツール |
|---------|------|-----------|
| 機能 | すべてのCTAリンクが正しく遷移 | 手動 + E2E |
| パフォーマンス | LCP < 2.5s / CLS < 0.1 / INP < 200ms | Lighthouse |
| アクセシビリティ | axe-core 違反 0 件、WCAG 2.1 AA | axe-core / Lighthouse |
| SEO | メタタイトル・description・OGP 設定済み | 手動確認 |
| 構造化データ | JSON-LD 構文エラーなし | Google Rich Results Test |
| 型チェック | `tsc --noEmit` でエラー 0 | TypeScript |
| リント | ESLint エラー 0 | ESLint |
| フォーマット | Prettier 準拠 | Prettier |
| 単体テスト | 全テスト合格、カバレッジ 80% 以上 | Vitest |
| E2Eテスト | 主要シナリオ全合格 | Playwright |

**ステークホルダーレビュー**:
- プロダクトオーナー、デザイナー、エンジニアによる最終レビュー
- 修正項目の洗い出しと修正

### 納品物
- 品質ゲートチェックリスト（`plans/` または `reports/` に保存）
- レビュー記録・修正履歴

### 品質基準
- すべてのチェックリスト項目が「合格」。
- ステークホルダーによる承認を得ること。

---

## ステップ36: 本番デプロイ・モニタリング設定・リリース後サイクル策定

### 目的
LPを本番環境にデプロイし、モニタリング・改善サイクルを開始する。

### 詳細実装内容
**デプロイ**:
- Vercel または Netlify にデプロイ（静的サイトホスティング、CI連携）
- または Docker コンテナで自社サーバーにデプロイ

**環境変数**:
| 変数名 | 内容 | 環境 |
|--------|------|------|
| `VITE_API_BASE_URL` | バックエンドAPIエンドポイント | すべて |
| `VITE_GA4_MEASUREMENT_ID` | GA4測定ID | 本番 |
| `VITE_SENTRY_DSN` | エラー監視DSN | 本番 |

**モニタリング設定**:
- GA4: ページビュー、コンバージョン（CTAクリック、登録完了）
- Sentry: フロントエンドエラー監視
- Google Search Console: 検索流入、インデックス状況

**リリース後KPIモニタリング（月次）**:
| KPI | 目標 | 確認頻度 |
|-----|------|---------|
| LP訪問者数 | 前月比 +10% | 月次 |
| 登録コンバージョン率 | > 12% | 月次 |
| 直帰率 | < 40% | 月次 |
| 平均滞在時間 | > 90秒 | 月次 |

**A/Bテスト計画（フェーズ4以降）**:
- ヒーローH1コピー: A「条件を入れたら、小説が届く」 / B「AIで小説を1分で執筆」
- CTAボタン色: シアン vs 紫
- 入口カード順序: かんたん→ウィザード→Studio など

### 納品物
- 本番デプロイ完了（本番URL公開）
- GA4 / Sentry / Search Console 設定完了
- KPIダッシュボード（GA4 または別ツール）

### 品質基準
- 本番URLにアクセスしてLPが正常に表示されること。
- GA4でページビューが計測されていること。
- エラー監視（Sentry）で致命的なJSエラーが発生していないこと。

---

**フェーズ３完了＝プロジェクト完了条件**:
- ステップ25〜36のすべてが完了。
- LPが本番環境で公開され、モニタリングが稼働している。
- すべての品質ゲートを通過し、ステークホルダー承認を得ている。

これで全36ステップの実装計画書（フェーズ1〜3）が完了です。