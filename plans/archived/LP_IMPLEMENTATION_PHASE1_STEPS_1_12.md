# AutoNovel 商業ランディングページ 実装計画書（フェーズ１：ステップ1〜12）

**フェーズ名**: 基盤・デザインシステム・コアコンポーネント構築  
**対象ステップ**: 1〜12（全36ステップのうち第1フェーズ）  
**目的**: 商業的に最高品質なLPの土台を築く。デザイントークン、レイアウト、ヘッダー/フッター、ヒーロー、3入口セクションまでを完成させる。  
**前提条件**: AutoNovelフロントエンド（React 18 + Vite + Tailwind CSS + TypeScript）が既に稼働していること。

---

## ステップ1: LP専用ディレクトリ構造とGitブランチ作成

### 目的
LP開発を既存アプリ（認証必須ダッシュボード）から分離し、衝突を防ぐ。

### 詳細実装内容
1. `frontend/src/components/lp/` ディレクトリを作成する。
2. `frontend/src/pages/lp/` ディレクトリを作成する。
3. `frontend/src/lib/lp/` ディレクトリを作成する（モーションプリセット、ユーティリティ）。
4. `plans/` ディレクトリに本計画書の3ファイルを配置する。
5. Gitブランチ `feature/commercial-lp-phase1` を作成し、すべての変更はこのブランチで行う。
6. `frontend/vite.config.ts` にLP専用エントリポイントを追加しない（既存Vite設定を共用し、ページルーティングで分岐する）。

### 納品物
- `frontend/src/components/lp/`（空ディレクトリ）
- `frontend/src/pages/lp/`（空ディレクトリ）
- `frontend/src/lib/lp/`（空ディレクトリ）
- Gitブランチ `feature/commercial-lp-phase1`

### 品質基準（チェックポイント）
- 既存の `src/pages/`、`src/components/` と命名の衝突がないこと。
- `git status` で新規ディレクトリが追跡対象になっていること。

---

## ステップ2: Tailwind CSS 設定の拡張（商業LP用カラー・フォント・アニメーション）

### 目的
既存のダークテーマ（slate-900系）をベースに、商業LPとしての信頼感と視覚的インパクトを強化する。

### 詳細実装内容
`frontend/tailwind.config.js` の `theme.extend.colors` に以下を追加：

```js
colors: {
  brand: {
    dark: '#020617',      // slate-950 ベース背景
    surface: '#0f172a',   // カード・パネル背景
    surfaceHover: '#1e293b',
    text: '#f8fafc',      // プライマリテキスト
    textMuted: '#94a3b8', // セカンダリテキスト
    accent: '#22d3ee',    // プライマリアクセント（シアン）
    accentHover: '#06b6d4',
    accentSecondary: '#a855f7', // セカンダリアクセント（紫）
    accentSecondaryHover: '#9333ea',
    success: '#34d399',
    warning: '#fbbf24',
    error: '#f87171',
    border: '#334155',    // パネル境界
  },
}
```

`theme.extend.fontFamily` に日本語フォントスタックを追加：

```js
fontFamily: {
  sans: [
    'system-ui', '-apple-system', 'BlinkMacSystemFont',
    '"Segoe UI"', 'Roboto', '"Hiragino Kaku Gothic ProN"',
    '"Hiragino Sans"', 'Meiryo', 'sans-serif',
  ],
}
```

`theme.extend.animation` と `theme.extend.keyframes` に以下を追加：

- `fade-in-up`: 0.6s ease-out、translateY(20px) → 0、opacity 0 → 1
- `fade-in`: 0.5s ease-in-out、opacity 0 → 1
- `slide-up`: 0.4s ease-out
- `scale-in`: 0.3s ease-out、scale(0.95) → 1
- `pulse-glow`: 3s infinite、box-shadow の拡大縮小

### 納品物
- `frontend/tailwind.config.js` の `colors`、`fontFamily`、`animation`、`keyframes` を更新

### 品質基準
- カラーコントラスト比：テキスト対背景で 4.5:1 以上（WCAG AA）。
- アクセントカラーはボタン・リンク・強調テキストにのみ使用し、過度な装飾を避ける。

---

## ステップ3: CSS変数・デザイントークンの定義（index.css）

### 目的
TailwindユーティリティクラスとCSS変数を両立させ、JSからも参照可能なデザイントークンを一元管理する。

### 詳細実装内容
`frontend/src/index.css`（または新規 `frontend/src/assets/lp-tokens.css`）に以下を定義：

```css
:root {
  --lp-bg-base: #020617;
  --lp-bg-surface: #0f172a;
  --lp-bg-surface-hover: #1e293b;
  --lp-text-primary: #f8fafc;
  --lp-text-secondary: #94a3b8;
  --lp-accent-primary: #22d3ee;
  --lp-accent-primary-hover: #06b6d4;
  --lp-accent-secondary: #a855f7;
  --lp-accent-secondary-hover: #9333ea;
  --lp-border: #334155;
  --lp-shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
  --lp-shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1);
  --lp-shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1);
  --lp-radius-sm: 4px;
  --lp-radius-md: 8px;
  --lp-radius-lg: 12px;
  --lp-radius-full: 9999px;
  --lp-space-1: 0.25rem;
  --lp-space-2: 0.5rem;
  --lp-space-4: 1rem;
  --lp-space-6: 1.5rem;
  --lp-space-8: 2rem;
  --lp-space-16: 4rem;
  --lp-transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
  --lp-transition-base: 300ms cubic-bezier(0.4, 0, 0.2, 1);
  --lp-transition-slow: 500ms cubic-bezier(0.4, 0, 0.2, 1);
}
```

Tailwindの `arbitrary values` で `var(--lp-*)` を参照できるようにコメントで残す。

### 納品物
- `frontend/src/assets/lp-tokens.css`（新規作成）
- `frontend/src/index.css` に `@import './assets/lp-tokens.css';` を追記

### 品質基準
- すべてのスペーシングは8pxグリッド（4px, 8px, 16px, 24px, 32px, 64px）に準拠。
- ボーダーラジオは `sm/md/lg/full` の4段階のみ。

---

## ステップ4: Framer Motion モーションプリセットの定義（lib/lp/motion.ts）

### 目的
LP全体で一貫したアニメーション挙動を実現し、過剰な動きを避けつつ商業的な滑らかさを出す。

### 詳細実装内容
`frontend/src/lib/lp/motion.ts` を新規作成し、以下をエクスポート：

```ts
import { Variants } from 'framer-motion';

export const fadeInUp: Variants = {
  hidden: { opacity: 0, y: 24 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: 'easeOut' } },
};

export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.5, ease: 'easeInOut' } },
};

export const staggerContainer: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.1, delayChildren: 0.1 },
  },
};

export const hoverScale = {
  whileHover: { scale: 1.02 },
  whileTap: { scale: 0.98 },
};

export const reducedMotion = {
  // prefers-reduced-motion 時はすべてのアニメーションを無効化
  hidden: { opacity: 1 },
  visible: { opacity: 1, transition: { duration: 0 } },
};

export const pageTransition = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
  transition: { duration: 0.3 },
};
```

`framer-motion` を `package.json` の dependencies に追加（未導入の場合）。

### 納品物
- `frontend/src/lib/lp/motion.ts`（新規作成）
- `frontend/package.json` に `framer-motion` を追加し `npm install`

### 品質基準
- `prefers-reduced-motion: reduce` に対応し、アニメーションを無効化できること。
- すべての遷移は `easeOut` または `easeInOut` を使用し、直線的な補間を避ける。

---

## ステップ5: レスポンシブブレークポイントとコンテナ定義

### 目的
LPの幅とセクション間の余白を統一し、モバイル・タブレット・デスクトップで崩れないレイアウトを確保する。

### 詳細実装内容
`frontend/tailwind.config.js` の `theme.screens` を確認し、以下を明記：

- `sm`: 640px
- `md`: 768px
- `lg`: 1024px
- `xl`: 1280px

LP用コンテナの最大幅を `max-w-7xl` (800px) または `max-w-[1200px]` とし、セクション間の縦パディングを統一：

- ヒーロー: `py-24 px-4 sm:py-32 sm:px-6 lg:py-40 lg:px-8`
- その他セクション: `py-16 px-4 sm:py-24 sm:px-6 lg:py-32 lg:px-8`

### 納品物
- `frontend/tailwind.config.js` の `screens` を明記（既定値と同一でもコメントで残す）
- LP用コンテナクラスの命名規則を `plans/` にメモとして残す

### 品質基準
- ブレークポイント間でレイアウトが急変しないこと（段階的な変化）。
- モバイル（375px幅）でもヒーローCTAが画面上部に収まること。

---

## ステップ6: LpHeader コンポーネント実装（ロゴ・ナビゲーション・CTA）

### 目的
LPのヘッダーを実装し、ブランド認知と主要な導線（登録・機能・料金）を提供する。

### 詳細実装内容
`frontend/src/components/lp/LpHeader.tsx` を新規作成：

**Props**:
- `onRegisterClick?: () => void`
- `onFeaturesClick?: () => void`

**構成**:
- 左: AutoNovel ロゴ（テキストロゴ、フォントサイズ `text-xl font-bold tracking-tight`、ホバーでアクセントカラー）
- 中央: ナビゲーションリンク（機能 / 料金 / FAQ / ドキュメント）、各リンクは `text-sm font-medium text-slate-300 hover:text-white transition-colors`
- 右: CTAボタン2つ
  - プライマリ: 「無料で始める」（背景 `bg-accent-primary`、テキスト白、ホバー `hover:bg-accent-primary-hover`、padding `px-6 py-2.5 rounded-md font-semibold`）
  - セカンダリ: 「機能を見る」（背景透過、ボーダー `border border-accent-primary/30`、ホバー `bg-accent-primary/10`）
- モバイル: ハンバーガーメニューボタン（`md:hidden`）、メニューはモーダルまたはドロワーで展開

**アクセシビリティ**:
- 各リンクに `aria-label` または明確なリンクテキスト
- フォーカスリングを可視化（`:focus-visible` で `ring-2 ring-accent-primary`）
- タブ順序を論理的に配置

**data-testid**:
- `lp-header-logo`
- `lp-header-nav-features`, `lp-header-nav-pricing`, `lp-header-nav-faq`, `lp-header-nav-docs`
- `lp-header-cta-primary`, `lp-header-cta-secondary`

### 納品物
- `frontend/src/components/lp/LpHeader.tsx`（新規作成）

### 品質基準
- スクロール時にヘッダーが固定（`sticky top-0`）または消えない（LPなので固定推奨）。
- モバイル（375px）でヘッダーの高さが60px以内に収まること。

---

## ステップ7: LpFooter コンポーネント実装（法務リンク・著作権・ソーシャル）

### 目的
LPのフッターを実装し、信頼構築（法務情報）とブランド認知を強化する。

### 詳細実装内容
`frontend/src/components/lp/LpFooter.tsx` を新規作成：

**構成**:
- 上部: AutoNovel ロゴと1行のタグライン（「条件を入れたら、小説が届く」）
- 中央: 4列のリンクグループ
  - プロダクト: 機能、料金、FAQ、ドキュメント
  - リソース: ブログ、ヘルプセンター、API、コミュニティ
  - 会社: 企業情報、採用情報、プレスリリース、投資家関係
  - 法務: 利用規約、プライバシーポリシー、特定商取引法に基づく表記、Cookieポリシー
- 下部: 著作権表示（`© 2026 HerbMatsui-spec. All rights reserved.`）、ソーシャルリンク（X、GitHub、Discord）

**スタイル**:
- 背景: `bg-brand-dark`（slate-950）、境界線 `border-t border-brand-border`
- テキスト: `text-slate-400`、ホバーで `text-white`
- リンク: `text-sm`、行間 `leading-6`

**アクセシビリティ**:
- すべてのリンクに適切な `href`、外部リンクには `target="_blank" rel="noopener noreferrer"`
- 著作権表示は `aria-label="Copyright"` を付与

### 納品物
- `frontend/src/components/lp/LpFooter.tsx`（新規作成）

### 品質基準
- モバイルではリンクグループをスタック（1列）にする。
- 「特定商取引法に基づく表記」リンクは必須（日本の商業サイトとして法的要件）。

---

## ステップ8: LpLayout コンポーネント実装（LP専用レイアウトラッパー）

### 目的
LPページ全体の共通ラッパーを実装し、Header + main + Footer を統一する。

### 詳細実装内容
`frontend/src/components/lp/LpLayout.tsx` を新規作成：

**Props**: `children?: React.ReactNode`

**構成**:
```tsx
<>
  <LpHeader />
  <main>{children}</main>
  <LpFooter />
</>
```

**スタイル**:
- `min-h-screen flex flex-col` でフッターをページ最下部に固定（コンテンツが少ない場合でも）
- 背景色 `bg-brand-dark`
- テキスト色 `text-brand-text`

**ページ遷移制御**:
- React Router の `useLocation` でスクロール位置をトップにリセット（`window.scrollTo(0, 0)`）

**注意**: 既存の `AppLayout` は認証必須アプリ用のため、LP用に `LpLayout` を別に作成し、認証ガードをかけない。

### 納品物
- `frontend/src/components/lp/LpLayout.tsx`（新規作成）

### 品質基準
- `LpLayout` を使用するページはすべて認証不要（公開ページ）。
- フッターがコンテンツの下に自然に配置され、画面中途で浮かないこと。

---

## ステップ9: HeroSection コピーライティング構成案策定

### 目的
ファーストビュー（Hero）のコピーを確定し、3秒以内に「何のサービスか」「何ができるか」「次に何をすべきか」を伝える。

### 詳細実装内容
`frontend/src/components/lp/HeroSection.tsx` のコピー案を以下で策定（実装はステップ10-11）：

**Eyebrow（スタブ）**: `AI 小説執筆プラットフォーム`

**H1（メイン見出し）**: `条件を入れたら、小説が届く。`

**サブ見出し**: `企画から執筆、矛盾診断、納品まで。AI と共に創作する小説制作プラットフォーム。8 専門オーディター監査で作品クオリティを保証します。`

**プライマリCTA**: `無料で始める` → `/register` または `/welcome`

**セカンダリCTA**: `機能を見る` → ページ内スクロール（#features）

**信頼バッジ（3つ）**:
- `8 専門オーディター監査`
- `EPUB / なろう・カクヨム形式対応`
- `クレジットカード不要`

**ビジュアル方向性**: 既存 `docs/images/hero.svg` をLP用に最適化し、ファーストビュー左側または背景に配置。

### 納品物
- `plans/` に `HERO_COPY.md` としてコピー案を保存（あるいは本ファイル内に記載済み）

### 品質基準
- H1はページに1つのみ。
- CTAはファーストビュー内にスクロール不要で2つ配置。
- モバイルではH1フォントサイズを `text-3xl`（約48px → 32pxに縮小）に調整。

---

## ステップ10: HeroSection ビジュアル実装（SVGアニメーション・LCP対策）

### 目的
HeroSectionのビジュアルを実装し、ファーストビューの描画速度（LCP）を最適化する。

### 詳細実装内容
`frontend/src/components/lp/HeroSection.tsx` を新規作成：

**画像処理**:
- 既存 `docs/images/hero.svg` をSVGOで最適化し、`frontend/public/images/hero-optimized.svg` として配置
- フォールバック用にWebP版も用意（`hero-optimized.webp`）
- `loading="eager"`、`decoding="async"` を `` タグに設定
- `width`、`height` 属性を明記しCLSを防止

**アニメーション**:
- Framer Motion の `fadeInUp` バリアントを適用し、セクション表示時に徐々に浮かび上がる
- ペン先の軌跡や光のエフェクトはSVGアニメーション（CSS `stroke-dasharray`）またはFramer Motionの `animate` で実装
- 過度な動きは避け、3秒以内に静止状態にする

**レイアウト**:
- デスクトップ: 左側にコピー・CTA、右側にビジュアル（または逆）
- モバイル: 上にコピー・CTA、下にビジュアル（スタック）

**data-testid**:
- `lp-hero-eyebrow`
- `lp-hero-headline`
- `lp-hero-subhead`
- `lp-hero-cta-primary`
- `lp-hero-cta-secondary`
- `lp-hero-badge-1/2/3`
- `lp-hero-visual`

### 納品物
- `frontend/src/components/lp/HeroSection.tsx`（新規作成）
- `frontend/public/images/hero-optimized.svg`（最適化済みSVG）
- `frontend/public/images/hero-optimized.webp`（フォールバック用WebP）

### 品質基準
- LCP（最大コンテンツ描画）が2.5秒以内に達成されること（Hero画像が優先読み込み）。
- ビジュアルはデスクトップで最大幅600px、モバイルで画面幅90%以内。

---

## ステップ11: HeroSection CTAボタン実装（プライマリ・セカンダリ・分析イベント）

### 目的
HeroSectionのCTAボタンを実装し、クリック計測と遷移を正しく行う。

### 詳細実装内容
ステップ10のHeroSection内にCTAボタンを実装：

**プライマリCTA（「無料で始める」）**:
- 背景: `bg-brand-accent`（シアン）、テキスト: 白
- ホバー: `bg-brand-accent-hover`、シャドウ: `shadow-lg shadow-cyan-500/25`
- アクティブ: `scale-95`
- クリックイベント: `onClick={() => { gtag('event', 'click', { event_category: 'hero_cta', event_label: 'primary_register' }); navigate('/register'); }}`
- `data-testid="lp-hero-cta-primary"`

**セカンダリCTA（「機能を見る」）**:
- 背景: 透過、ボーダー: `border border-brand-accent/30`
- ホバー: `bg-brand-accent/10`、テキスト色変化
- クリックイベント: ページ内スクロール（#features へ）`navigate('#features')` または `scrollIntoView`
- `data-testid="lp-hero-cta-secondary"`

**共通**:
- パディング: `px-6 py-3`、フォント: `font-semibold text-sm`
- タッチターゲット最小44px×44px（モバイル操作性）
- フォーカスリング: `focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 focus-visible:ring-offset-brand-dark`

### 納品物
- `frontend/src/components/lp/HeroSection.tsx` にCTA実装を追加（ステップ10と同ファイル）

### 品質基準
- プライマリCTAは視覚的に最も目立つ（背景色付き、サイズ大きめ）。
- クリック時にGA4または独自アナリティクスイベントが送信されること。

---

## ステップ12: EntryPointsSection 実装（3つの入口カード）

### 目的
AutoNovelの3つの入口（かんたん執筆／共創ウィザード／Studio）をLP用に再設計し、ユーザーを適切な入口へ誘導する。

### 詳細実装内容
`frontend/src/components/lp/EntryPointsSection.tsx` を新規作成：

**構成**:
- セクション見出し: `3 つの入口 ─ どれから始めても同じ作品に書き足せます`
- 説明文: `プログラミングやAIの専門知識がなくても、ブラウザのフォームに条件を入れただけで小説が生成されます。`

**3つのカード（グリッド：デスクトップ3列、タブレット2列、モバイル1列）**：

| 入口 | タイトル | 説明 | CTA |
|------|---------|------|-----|
| ⚡ かんたん執筆 | かんたん執筆 | 書きたい内容を入れるだけ。約1分で小説生成。 | 今すぐ試す |
| ✨ 共創ウィザード | 共創ウィザード | 骨組みから決めてから書く。3ステップ。 | ウィザードを始める |
| 🚀 Studio | Studio | 仕上げと詳細設定。既存作品からすぐ。 | Studioを開始 |

**各カードのスタイル**:
- 背景: `bg-brand-surface`、ボーダー: `border border-brand-border`、ボーダーラジオ: `rounded-xl`
- ホバー時: ボーダー色 `border-brand-accent/50`、シャドウ `shadow-lg`、`-translate-y-1`
- アイコン: 24px×24px、カラーはアクセントカラー
- タイトル: `text-lg font-semibold text-brand-text`
- 説明: `text-sm text-brand-text-muted`
- CTAボタン: アクセントカラー背景、テキスト白、`px-4 py-2 text-xs font-semibold rounded`

**アクセシビリティ**:
- 各カードは `<a>` または `<button role="link">` でキーボード操作可能
- `aria-label="かんたん執筆 - 今すぐ試す"` など

**data-testid**:
- `lp-entry-easy-card`, `lp-entry-wizard-card`, `lp-entry-studio-card`
- `lp-entry-easy-cta`, `lp-entry-wizard-cta`, `lp-entry-studio-cta`

### 納品物
- `frontend/src/components/lp/EntryPointsSection.tsx`（新規作成）

### 品質基準
- 3つのカードが等幅で並び、モバイルではスタック表示。
- 各CTAクリックで対応ページ（`/`, `/wizard`, `/studio` または `/welcome`）へ遷移。

---

**フェーズ１完了条件**:
- ステップ1〜12のすべてのコンポーネントが実装済み。
- `LpLayout` に `HeroSection` と `EntryPointsSection` を組み込んだLPトップページが表示される。
- モバイル・デスクトップでレイアウト崩れがない。
- Lighthouse アクセシビリティスコア 80 点以上。

次はフェーズ２（ステップ13〜24：機能・料金・事例・FAQ・SEO・アクセシビリティ）です。