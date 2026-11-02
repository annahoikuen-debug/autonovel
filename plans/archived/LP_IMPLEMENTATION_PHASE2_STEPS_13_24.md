# AutoNovel 商業ランディングページ 実装計画書（フェーズ２：ステップ13〜24）

**フェーズ名**: セクション実装・コンテンツ・SEO／アクセシビリティ  
**対象ステップ**: 13〜24（全36ステップのうち第2フェーズ）  
**目的**: LPの本体セクション（機能・料金・事例・FAQ・最終CTA）を実装し、SEO・OGP・構造化データ・アクセシビリティを整備する。  
**前提条件**: フェーズ１（ステップ1〜12）が完了し、`LpLayout`、`HeroSection`、`EntryPointsSection` が動作していること。

---

## ステップ13: FeaturesSection 実装（機能グリッド）

### 目的
AutoNovelの主要機能を8つ紹介し、プロダクトの価値を視覚的・構造的に伝える。

### 詳細実装内容
`frontend/src/components/lp/FeaturesSection.tsx` を新規作成：

**セクション見出し**: `小説執筆を、企画から納品まで一貫してサポート`

**グリッドレイアウト**:
- デスクトップ: 3列（`grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3`）
- タブレット: 2列
- モバイル: 1列
- カード間隔: `gap-6 sm:gap-8`

**8つの機能カード（各カード: アイコン・タイトル・説明）**：

| # | アイコン | タイトル | 説明 |
|---|---------|---------|------|
| 1 | ✍️ | AI 本文生成 | ジャンル・主人公・冒頭プロンプトから本文を自動生成。リアルタイム速筆（SSE）対応。 |
| 2 | 🔍 | 8 専門オーディター監査 | 矛盾・感情・続き・構成など8視点で自動診断し、作品クオリティを保証。 |
| 3 | ⚡ | リアルタイム速筆 | テキストがストリーミングで流れ込む。書き進めながら内容を確認。 |
| 4 | 📦 | 納品パッケージ（ZIP） | 本文・設定集・プロット・データを1つのZIPでダウンロード。 |
| 5 | 📚 | EPUB / なろう形式出力 | 投稿サイト向けに自動整形。なろう・カクヨム形式に対応。 |
| 6 | 🕸️ | 相関図ビジュアル化 | キャラクター関係をグラフで可視化し、設定の整合性を一目で把握。 |
| 7 | 📢 | マーケティング支援 | タイトル・キャッチコピー生成（カクヨム35文字最適化）。 |
| 8 | 🌓 | テーマ切替 | ダーク／ライト／セピア。執筆環境を好みに合わせて選択。 |

**カードスタイル**:
- 背景: `bg-brand-surface`、ボーダー: `border border-brand-border`、ボーダーラジオ: `rounded-xl`
- ホバー時: `border-brand-accent/50`、`shadow-lg`、`-translate-y-1`
- アイコン: 32px×32px、アクセントカラー
- タイトル: `text-base font-semibold text-brand-text`
- 説明: `text-sm text-brand-text-muted leading-relaxed`

**アニメーション**:
- Framer Motion の `staggerContainer` と `fadeInUp` で、カードを順次フェードイン表示

**data-testid**:
- `lp-features-section`
- `lp-feature-card-1` 〜 `lp-feature-card-8`
- `lp-feature-icon-1` 〜 `lp-feature-icon-8`

### 納品物
- `frontend/src/components/lp/FeaturesSection.tsx`（新規作成）

### 品質基準
- 8機能すべてがデスクトップで3列、モバイルで1列に正しく配置されること。
- カードの高さが揃い、説明文の長さ違いでレイアウトが崩れないこと（`h-full` 適用）。

---

## ステップ14: FeatureCard コンポーネント実装（再利用可能な機能カード単体）

### 目的
`FeaturesSection` で使用する機能カードを再利用可能コンポーネントとして分離し、メンテナンス性を高める。

### 詳細実装内容
`frontend/src/components/lp/FeatureCard.tsx` を新規作成：

**Props**:
```tsx
interface FeatureCardProps {
  index: number;          // アニメーション遅延用
  icon: React.ReactNode;
  title: string;
  description: string;
}
```

**実装**:
- `framer-motion` の `motion.div` を使用
- `variants={fadeInUp}` と `custom={index * 0.1}` で遅延アニメーション
- `whileHover={{ scale: 1.02 }}`、`whileTap={{ scale: 0.98 }}`
- `className` でカードのベーススタイルを適用

**data-testid**: `lp-feature-card-{index}`

### 納品物
- `frontend/src/components/lp/FeatureCard.tsx`（新規作成）

### 品質基準
- `FeaturesSection` から `FeatureCard` を使用して8つのカードをレンダリングすること。
- 各カードが独立してテスト可能であること。

---

## ステップ15: PricingSection 実装（料金プラン）

### 目的
料金プランを明確に提示し、有料プランへのコンバージョンを促す。

### 詳細実装内容
`frontend/src/components/lp/PricingSection.tsx` を新規作成：

**セクション見出し**: `シンプルで透明な料金体系`

**3つのプラン**:

| プラン | 価格 | 対象 | CTA |
|--------|------|------|-----|
| フリー | ¥0 / 月 | 試し利用 | はじめる |
| スタンダード | ¥980 / 月 | 本格利用 | はじめる（人気） |
| プロ | ¥2,980 / 月 | プロ・上級者 | はじめる |

**プラン別機能リスト（チェックマーク）**:

- フリー: かんたん執筆 月5本まで、基本機能、コミュニティサポート
- スタンダード: 無制限執筆、8オーディター監査、ZIP納品、メールサポート
- プロ: Studio全機能、EPUB出力、優先サポート、マーケティング支援

**スタイル**:
- 各プランはカード形式（`bg-brand-surface`、`border border-brand-border`、`rounded-xl`）
- 人気プラン（スタンダード）は上部にバッジ「Most Popular」、枠線を `border-brand-accent` にし、背景をわずかに明るく（`bg-brand-surface-hover`）
- 価格表示は大きく（`text-2xl font-bold`）、`/ 月` は小さく（`text-sm`）
- CTAボタンはプライマリカラー（人気プランはセカンダリカラーでも可）

**注記**: 料金は仮設定。実際の課金体系と連携して差し替えること。

**data-testid**:
- `lp-pricing-section`
- `lp-pricing-card-free`, `lp-pricing-card-standard`, `lp-pricing-card-pro`
- `lp-pricing-cta-free`, `lp-pricing-cta-standard`, `lp-pricing-cta-pro`

### 納品物
- `frontend/src/components/lp/PricingSection.tsx`（新規作成）

### 品質基準
- 3プランが横並び（デスクトップ）、スタック（モバイル）に表示されること。
- 「Most Popular」バッジがスタンダードプランにのみ付与されること。
- 価格が明確に読め、CTAボタンが各プランの下部に配置されること。

---

## ステップ16: PricingCard コンポーネント実装（料金カード単体）

### 目的
料金カードを再利用可能コンポーネントとして分離する。

### 詳細実装内容
`frontend/src/components/lp/PricingCard.tsx` を新規作成：

**Props**:
```tsx
interface PricingCardProps {
  plan: 'free' | 'standard' | 'pro';
  price: string;
  pricePeriod: string; // '/ 月'
  title: string;
  description: string;
  features: string[];
  isPopular?: boolean;
  ctaLabel: string;
  onCtaClick: () => void;
}
```

**実装**:
- `isPopular` 時はバッジ表示と枠線色変更
- 機能リストはチェックマーク（`✓` または `check-circle` アイコン）付きリスト
- CTAボタンは `onCtaClick` でイベント発行

**data-testid**: `lp-pricing-card-{plan}`

### 納品物
- `frontend/src/components/lp/PricingCard.tsx`（新規作成）

### 品質基準
- `PricingSection` から `PricingCard` を使用して3つのカードをレンダリングすること。
- 各カードの高さが揃い、人気プランが視覚的に強調されること。

---

## ステップ17: TestimonialsSection 実装（導入事例・ユーザーの声）

### 目的
実際のユーザー（または仮の事例）の声を掲載し、ソーシャルプルーフによる信頼構築を行う。

### 詳細実装内容
`frontend/src/components/lp/TestimonialsSection.tsx` を新規作成：

**セクション見出し**: `作家・クリエイターの声`

**事例カード3件（ダミー/仮）**:

| # | ユーザー | ジャンル | 評価 | 感想（抜粋） |
|---|---------|---------|------|-------------|
| 1 | 佐藤健太 | ファンタジー | ★★★★★ | 「プロット作成が劇的に楽になりました」 |
| 2 | 鈴木花子 | ラブコメ | ★★★★☆ | 「8オーディターの矛盾チェックが助かります」 |
| 3 | 田中次郎 | SF | ★★★★★ | 「EPUB出力ですぐにカクヨムに投稿できました」 |

**カードスタイル**:
- アバター: プレースホルダー画像（40px×40px、ボーダーラジオ `rounded-full`）
- ユーザー名: `text-sm font-semibold text-brand-text`
- ジャンル: `text-xs text-brand-text-muted`
- 評価: 星5つ（黄色 `text-yellow-400`）
- 感想文: `text-sm text-brand-text-muted leading-relaxed`, 引用符 `「 」` で囲む

**ソーシャルプルーフ表示**:
- `累計生成小説数: 10,000 件以上`（仮）
- `登録ユーザー数: 5,000 名以上`（仮）

**アニメーション**:
- カードを横スライドまたは順次フェードイン

**data-testid**:
- `lp-testimonials-section`
- `lp-testimonial-card-1/2/3`
- `lp-social-proof-count`

### 納品物
- `frontend/src/components/lp/TestimonialsSection.tsx`（新規作成）

### 品質基準
- 事例はダミーであることを明記（`※事例は仮の内容です`など）。
- アバター画像はプレースホルダーでも適切な `alt` 属性を設定。

---

## ステップ18: FaqSection 実装（アコーディオンFAQ）

### 目的
ユーザーの不安を解消し、コンバージョンの障壁を取り除くためのFAQを実装する。

### 詳細実装内容
`frontend/src/components/lp/FaqSection.tsx` を新規作成：

**セクション見出し**: `よくある質問`

**5〜7問のFAQ（アコーディオン形式）**:

| # | 質問（例） |
|---|-----------|
| 1 | AI で生成した小説の著作権は誰に帰属しますか？ |
| 2 | 無料プランと有料プランの違いは何ですか？ |
| 3 | なろう・カクヨムに直接投稿できますか？ |
| 4 | R18 表現は生成できますか？ |
| 5 | データはどこに保存されますか？ |
| 6 | 解約はいつでもできますか？ |
| 7 | サポートは受けられますか？ |

**アコーディオン実装**:
- 開閉状態を `useState` で管理（`openIndex: number | null`）
- Framer Motion で高さアニメーション（`animateHeight` または `maxHeight` アニメーション）
- 開閉アイコン（`+` / `−` または `chevron-down` / `chevron-up`）

**アクセシビリティ**:
- 各項目に `aria-expanded`、`aria-controls` を設定
- キーボード操作（Enter/Space）で開閉可能
- フォーカスリングを可視化

**data-testid**:
- `lp-faq-section`
- `lp-faq-item-1` 〜 `lp-faq-item-7`
- `lp-faq-question-1` 〜 `lp-faq-question-7`

### 納品物
- `frontend/src/components/lp/FaqSection.tsx`（新規作成）
- `frontend/src/components/lp/FaqItem.tsx`（新規作成、アコーディオン単体）

### 品質基準
- デフォルトではすべて閉じた状態。
- 1つ開いているときに別の項目を開くと、前の項目は閉じる（アコーディオン挙動）または複数開放を許可（仕様による）。

---

## ステップ19: FinalCtaSection 実装（最終CTAセクション）

### 目的
ページ最後のコンバージョン集中エリアを実装し、登録を促す。

### 詳細実装内容
`frontend/src/components/lp/FinalCtaSection.tsx` を新規作成：

**構成**:
- 背景: `bg-brand-accent/10` または `bg-brand-surface` で他セクションと区別
- 見出し: `今すぐ小説を書き始める`
- 説明: `登録は1分。クレジットカード不要。AIと共に創作を始めましょう。`
- CTAボタン: `無料アカウントを作成する`（プライマリカラー、大きめ）
- 信頼文: `30日以内ならいつでも解約可能`（小さく、CTAの下）

**スタイル**:
- セクション全体に `rounded-2xl`、`p-8 sm:p-12`
- ボーダー: `border border-brand-border`
- CTAボタンは `w-full sm:w-auto`、パディング `px-8 py-4`

**data-testid**:
- `lp-final-cta-section`
- `lp-final-cta-button`

### 納品物
- `frontend/src/components/lp/FinalCtaSection.tsx`（新規作成）

### 品質基準
- フッターの直前に配置。
- CTAボタンが視覚的に最も目立つ（セクション内で最大の色面積）。

---

## ステップ20: LpPage 統合・ルーティング設定

### 目的
すべてのセクションを統合したLPトップページを作成し、ルーティングを設定する。

### 詳細実装内容
`frontend/src/pages/lp/LpPage.tsx` を新規作成：

**構成**:
```tsx
<LpLayout>
  <HeroSection />
  <EntryPointsSection />
  <FeaturesSection />
  <PricingSection />
  <TestimonialsSection />
  <FaqSection />
  <FinalCtaSection />
</LpLayout>
```

**ルーティング設定** (`frontend/src/routes.tsx`):
```tsx
{ path: "/", element: <LpPage />, errorElement: <RouteErrorView /> },
{ path: "/lp", element: <Navigate to="/" replace /> },
```

**既存アプリの移行**:
- 既存の `/`（Easy Mode / 認証必須）は `/app/easy` または `/dashboard/easy` に移動
- `routes.tsx` に `/app/*` のルートを追加
- `OnboardingGate` のパス判定を `/app` 配下に更新

**ページ遷移制御**:
- ページロード時に `window.scrollTo(0, 0)` でトップに戻る

### 納品物
- `frontend/src/pages/lp/LpPage.tsx`（新規作成）
- `frontend/src/routes.tsx` の更新
- `frontend/src/App.tsx` または `OnboardingGate` のパス判定更新（必要に応じて）

### 品質基準
- `/` にアクセスするとLPが表示され、認証不要。
- `/lp` にアクセスすると `/` にリダイレクト。
- 既存アプリ（`/wizard`, `/studio` 等）は引き続き動作すること。

---

## ステップ21: メタデータ・SEO実装（title, description, OGP）

### 目的
検索エンジンとSNSシェア時に最適なタイトル・説明・画像を表示する。

### 詳細実装内容
`frontend/src/pages/lp/LpPage.tsx` または `frontend/src/components/lp/LpHead.tsx` で `<head>` を管理：

**HTMLタイトル**:
```html
<title>AutoNovel | 条件を入れたら、小説が届く AI 小説執筆プラットフォーム</title>
```

**メタディスクリプション**:
```html
<meta name="description" content="企画から執筆、矛盾診断、納品まで。AI と共に創作する小説制作プラットフォーム。8 専門オーディター監査。無料で始められます。">
```

**キーワード**:
```html
<meta name="keywords" content="AI小説, 小説執筆, なろう, カクヨム, AI ライトノベル, 物語生成, 小説支援ツール">
```

**OGP（Open Graph Protocol）**:
```html
<meta property="og:type" content="website">
<meta property="og:title" content="AutoNovel | 条件を入れたら、小説が届く">
<meta property="og:description" content="企画から執筆、矛盾診断、納品まで。AI と共に創作する小説制作プラットフォーム。">
<meta property="og:image" content="https://autonovel.example.com/ogp.png">
<meta property="og:url" content="https://autonovel.example.com/">
<meta property="og:site_name" content="AutoNovel">
<meta property="og:locale" content="ja_JP">
```

**Twitter Card**:
```html
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="https://autonovel.example.com/ogp.png">
```

**canonical URL**:
```html
<link rel="canonical" href="https://autonovel.example.com/">
```

**OGP画像**: `frontend/public/ogp.png`（1200×630px、PNGまたはWebP）

### 納品物
- `frontend/src/components/lp/LpHead.tsx` または `LpPage.tsx` にhead要素を実装
- `frontend/public/ogp.png`（OGP画像、デザインは別途またはプレースホルダー）

### 品質基準
- タイトルは60文字以内、ディスクリプションは160文字以内。
- OGP画像は1200×630px、ファイルサイズは1MB以下。
- `og:image` に絶対URLを使用。

---

## ステップ22: 構造化データJSON-LD実装

### 目的
Googleなどの検索エンジンにサイトの構造を正しく伝え、リッチリザルトを狙う。

### 詳細実装内容
`frontend/src/components/lp/LpHead.tsx` または `LpPage.tsx` に `<script type="application/ld+json">` を追加：

```json
{
  "@context": "https://schema.org",
  "@type": "WebSite",
  "name": "AutoNovel",
  "url": "https://autonovel.example.com/",
  "description": "AI 小説執筆プラットフォーム。条件を入れたら、小説が届く。",
  "potentialAction": {
    "@type": "SearchAction",
    "target": "https://autonovel.example.com/search?q={search_string}",
    "query-input": "required name=search_string"
  },
  "publisher": {
    "@type": "Organization",
    "name": "HerbMatsui-spec",
    "url": "https://github.com/herbmatsui-spec/autonovel"
  }
}
```

**Organization 構造化データ**:
```json
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "HerbMatsui-spec",
  "url": "https://github.com/herbmatsui-spec/autonovel",
  "logo": "https://autonovel.example.com/logo.png"
}
```

### 納品物
- `frontend/src/components/lp/LpHead.tsx` にJSON-LDスクリプトを追加

### 品質基準
- JSON-LDの構文が正しく、Google Rich Results Testでエラーが出ないこと。
- `@type` は `WebSite` と `Organization` を正しく使用。

---

## ステップ23: サイトマップ・robots.txt実装

### 目的
検索エンジンのクロールを最適化し、インデックス登録を促進する。

### 詳細実装内容
**sitemap.xml** (`frontend/public/sitemap.xml`):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://autonovel.example.com/</loc>
    <lastmod>2026-10-31</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
```

**robots.txt** (`frontend/public/robots.txt`):
```
User-agent: *
Allow: /

Sitemap: https://autonovel.example.com/sitemap.xml
```

**Vite設定**: `frontend/vite.config.ts` で `public` ディレクトリがビルド出力に含まれることを確認（デフォルトで含まれる）。

### 納品物
- `frontend/public/sitemap.xml`（新規作成）
- `frontend/public/robots.txt`（新規作成）

### 品質基準
- `sitemap.xml` がXMLとして正しくパース可能。
- `robots.txt` でクロール拒否されていないこと。

---

## ステップ24: アクセシビリティ基盤整備（WCAG 2.1 AA準拠）

### 目的
LPのすべてのコンポーネントがWCAG 2.1 AAレベルのアクセシビリティを満たすよう基盤を整備する。

### 詳細実装内容
以下をすべてのLPコンポーネントに適用：

**色コントラスト**:
- テキスト対背景: 4.5:1 以上（通常テキスト）
- 大文字（18pt以上または14pt bold以上）: 3:1 以上
- UIコンポーネント（ボーダー、ボタン背景）: 3:1 以上

**フォーカス可視化**:
- すべてのインタラクティブ要素に `:focus-visible` で `ring-2 ring-brand-accent ring-offset-2 ring-offset-brand-dark`
- フォーカスリングがコンテンツに隠れないこと

**ARIA属性**:
- ボタン: 明確なテキストまたは `aria-label`
- リンク: `href` を持ち、外部リンクは `target="_blank" rel="noopener noreferrer"`
- 画像: 情報画像は説明的な `alt`、装飾画像は `alt=""`
- フォーム: `aria-label` または `<label>` との関連付け

**見出し階層**:
- `h1` → `h2` → `h3` の順序を厳守（飛ばさない）
- `h1` はページに1つのみ（HeroSectionのメイン見出し）

**スクリーンリーダー対応**:
- 視覚専用情報には `.sr-only` クラス（またはTailwindの `sr-only`）を適用
- 例: 「現在地」や装飾的なアイコンの説明

**キーボードナビゲーション**:
- Tabキーですべてのインタラクティブ要素にフォーカス移動可能
- タブ順序が論理的（ヘッダー → コンテンツ → フッター）

**データテストID**:
- すべての主要インタラクティブ要素に `data-testid` を付与（テスト自動化のため）

### 納品物
- `frontend/src/components/lp/` の各コンポーネントにアクセシビリティ属性を追加（既存ファイルを編集）

### 品質基準
- axe-core または Lighthouse アクセシビリティ監査で違反 0 件。
- スクリーンリーダー（NVDA / VoiceOver）で手動確認し、主要操作が可能であること。

---

**フェーズ２完了条件**:
- ステップ13〜24のすべてのセクション・コンポーネントが実装済み。
- LPトップページにすべてのセクションが順次表示される。
- SEO・OGP・構造化データ・サイトマップ・robots.txt が設定済み。
- アクセシビリティ基準（WCAG 2.1 AA）を満たす。
- Lighthouse SEOスコア 90 点以上、アクセシビリティスコア 90 点以上。

次はフェーズ３（ステップ25〜36：パフォーマンス・テスト・デプロイ・運用）です。