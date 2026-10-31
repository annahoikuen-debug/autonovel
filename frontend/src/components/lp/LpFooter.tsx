/**
 * AutoNovel 商業LP - フッターコンポーネント
 *
 * ファイル: frontend/src/components/lp/LpFooter.tsx
 *
 * 役割: ロゴ・タグライン・サイトリンク・法務リンク・著作権・ソーシャルリンクを配置。
 * 日本の商業サイトとして「特定商取引法に基づく表記」を含める。
 */

import React from 'react';

export const LpFooter: React.FC = () => {
  return (
    <footer
      className="bg-brand-dark border-t border-brand-border mt-auto"
      data-testid="lp-footer"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* 上部: ロゴ + タグライン + ソーシャル */}
        <div className="pt-10 pb-8 md:pt-16 md:pb-12 flex flex-col md:flex-row md:items-center md:justify-between gap-6">
          <div className="flex items-center gap-2">
            <span className="text-brand-accent font-bold text-xl tracking-tight">
              AutoNovel
            </span>
          </div>
          <p className="text-sm text-brand-textMuted">
            条件を入れたら、小説が届く。
          </p>
          <div className="flex items-center gap-4">
            <a
              href="https://x.com"
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand-textMuted hover:text-brand-text transition-colors"
              aria-label="X (Twitter)"
              data-testid="lp-footer-social-x"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8.29 20.251c7.547 0 11.675-6.253 11.675-11.675 0-.178 0-.355-.012-.53A8.348 8.348 0 0022 5.92a8.19 8.19 0 01-2.357.646 4.118 4.118 0 001.804-2.27 8.224 8.224 0 01-2.605.996 4.107 4.107 0 00-6.993 3.743 11.65 11.65 0 01-8.457-4.287 4.106 4.106 0 001.27 5.477A4.072 4.072 0 012.8 9.713v.052a4.105 4.105 0 003.292 4.022 4.095 4.095 0 01-1.853-.07 4.108 4.108 0 003.834 2.85A8.233 8.233 0 012 18.407a11.616 11.616 0 006.29 1.84" />
              </svg>
            </a>
            <a
              href="https://github.com/herbmatsui-spec/autonovel"
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand-textMuted hover:text-brand-text transition-colors"
              aria-label="GitHub"
              data-testid="lp-footer-social-github"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.301 3.495.998.108-.776.417-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
              </svg>
            </a>
          </div>
        </div>

        {/* リンクグループ */}
        <div className="mt-10 md:mt-16 grid grid-cols-2 md:grid-cols-4 gap-8 md:gap-12 border-t border-brand-border pt-8">
          <div>
            <h3 className="text-xs font-semibold text-brand-text uppercase tracking-wider mb-6">
              プロダクト
            </h3>
            <ul className="space-y-3">
              <li>
                <a
                  href="#lp-features-section"
                  className="text-sm text-brand-textMuted hover:text-brand-text transition-colors"
                >
                  機能
                </a>
              </li>
              <li>
                <a
                  href="#lp-pricing-section"
                  className="text-sm text-brand-textMuted hover:text-brand-text transition-colors"
                >
                  料金
                </a>
              </li>
              <li>
                <a
                  href="#lp-faq-section"
                  className="text-sm text-brand-textMuted hover:text-brand-text transition-colors"
                >
                  FAQ
                </a>
              </li>
              <li>
                <a
                  href="/welcome"
                  className="text-sm text-brand-textMuted hover:text-brand-text transition-colors"
                >
                  入口選択
                </a>
              </li>
            </ul>
          </div>
          <div>
            <h3 className="text-xs font-semibold text-brand-text uppercase tracking-wider mb-6">
              リソース
            </h3>
            <ul className="space-y-3">
              <li>
                <a
                  href="https://github.com/herbmatsui-spec/autonovel/tree/main/docs"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-brand-textMuted hover:text-brand-text transition-colors"
                >
                  ドキュメント
                </a>
              </li>
              <li>
                <a
                  href="#"
                  className="text-sm text-brand-textMuted hover:text-brand-text transition-colors"
                >
                  ヘルプセンター
                </a>
              </li>
              <li>
                <a
                  href="#"
                  className="text-sm text-brand-textMuted hover:text-brand-text transition-colors"
                >
                  ブログ
                </a>
              </li>
              <li>
                <a
                  href="#"
                  className="text-sm text-brand-textMuted hover:text-brand-text transition-colors"
                >
                  コミュニティ
                </a>
              </li>
            </ul>
          </div>
          <div>
            <h3 className="text-xs font-semibold text-brand-text uppercase tracking-wider mb-6">
              会社
            </h3>
            <ul className="space-y-3">
              <li>
                <a
                  href="#"
                  className="text-sm text-brand-textMuted hover:text-brand-text transition-colors"
                >
                  企業情報
                </a>
              </li>
              <li>
                <a
                  href="#"
                  className="text-sm text-brand-textMuted hover:text-brand-text transition-colors"
                >
                  採用情報
                </a>
              </li>
              <li>
                <a
                  href="#"
                  className="text-sm text-brand-textMuted hover:text-brand-text transition-colors"
                >
                  プレスリリース
                </a>
              </li>
              <li>
                <a
                  href="#"
                  className="text-sm text-brand-textMuted hover:text-brand-text transition-colors"
                >
                  投資家関係
                </a>
              </li>
            </ul>
          </div>
          <div>
            <h3 className="text-xs font-semibold text-brand-text uppercase tracking-wider mb-6">
              法務
            </h3>
            <ul className="space-y-3">
              <li>
                <a
                  href="#"
                  className="text-sm text-brand-textMuted hover:text-brand-text transition-colors"
                >
                  利用規約
                </a>
              </li>
              <li>
                <a
                  href="#"
                  className="text-sm text-brand-textMuted hover:text-brand-text transition-colors"
                >
                  プライバシーポリシー
                </a>
              </li>
              <li>
                <a
                  href="#"
                  className="text-sm text-brand-textMuted hover:text-brand-text transition-colors"
                >
                  特定商取引法に基づく表記
                </a>
              </li>
              <li>
                <a
                  href="#"
                  className="text-sm text-brand-textMuted hover:text-brand-text transition-colors"
                >
                  Cookie ポリシー
                </a>
              </li>
            </ul>
          </div>
        </div>

        {/* 下部: 著作権 */}
        <div className="mt-12 md:mt-16 pt-8 border-t border-brand-border flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <p className="text-xs text-brand-textMuted">
            © 2026 HerbMatsui-spec. All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  );
};

export default LpFooter;