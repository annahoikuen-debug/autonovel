/**
 * AutoNovel 商業LP - ヘッダーコンポーネント
 *
 * ファイル: frontend/src/components/lp/LpHeader.tsx
 *
 * 役割: ロゴ・ナビゲーション・CTA ボタンを配置。
 * 認証不要の公開ページ専用。既存 AppLayout とは別系統。
 */

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

interface LpHeaderProps {
  onRegisterClick?: () => void;
  onFeaturesClick?: () => void;
}

export const LpHeader: React.FC<LpHeaderProps> = ({
  onRegisterClick,
  onFeaturesClick,
}) => {
  const navigate = useNavigate();
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  const handleRegister = () => {
    onRegisterClick?.();
    navigate('/register');
  };

  /**
   * ページ内スクロール（セクション id へ）。
   * セクションは lp-features-section / lp-pricing-section / lp-faq-section。
   * DOM がまだマウントされていない可能性があるため null チェックを行う。
   */
  const scrollToSection = (sectionId: string) => {
    const el = document.getElementById(sectionId);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' });
    }
  };

  const handleFeatures = () => {
    onFeaturesClick?.();
    scrollToSection('lp-features-section');
  };

  const handleMobileMenu = () => {
    setIsMenuOpen((prev) => !prev);
  };

  return (
    <header
      className="sticky top-0 z-50 bg-brand-dark/95 backdrop-blur-md border-b border-brand-border"
      data-testid="lp-header"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* ロゴ */}
          <button
            type="button"
            className="flex items-center gap-2 cursor-pointer"
            onClick={() => navigate('/')}
            aria-label="AutoNovel ホームへ"
            data-testid="lp-header-logo"
          >
            <span className="text-brand-accent font-bold text-xl tracking-tight">
              AutoNovel
            </span>
          </button>

          {/* デスクトップナビゲーション（ページ内スクロール） */}
          <nav className="hidden md:flex items-center gap-8" data-testid="lp-header-nav">
            <button
              type="button"
              onClick={handleFeatures}
              className="text-sm font-medium text-brand-textMuted hover:text-brand-text transition-colors"
              data-testid="lp-header-nav-features"
            >
              機能
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('lp-pricing-section')}
              className="text-sm font-medium text-brand-textMuted hover:text-brand-text transition-colors"
              data-testid="lp-header-nav-pricing"
            >
              料金
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('lp-faq-section')}
              className="text-sm font-medium text-brand-textMuted hover:text-brand-text transition-colors"
              data-testid="lp-header-nav-faq"
            >
              FAQ
            </button>
            <a
              href="https://github.com/herbmatsui-spec/autonovel"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm font-medium text-brand-textMuted hover:text-brand-text transition-colors"
              data-testid="lp-header-nav-docs"
            >
              ドキュメント
            </a>
          </nav>

          {/* CTA ボタン（デスクトップ） */}
          <div className="hidden md:flex items-center gap-4">
            <button
              type="button"
              onClick={handleFeatures}
              className="px-5 py-2.5 text-sm font-semibold text-brand-text border border-brand-accent/30 rounded-lg hover:bg-brand-accent/10 transition-colors"
              data-testid="lp-header-cta-secondary"
            >
              機能を見る
            </button>
            <button
              type="button"
              onClick={handleRegister}
              className="px-6 py-2.5 text-sm font-semibold text-white bg-brand-accent rounded-lg hover:bg-brand-accent-hover hover:shadow-lg hover:shadow-cyan-500/25 transition-colors"
              data-testid="lp-header-cta-primary"
            >
              無料で始める
            </button>
          </div>

          {/* モバイルメニューボタン */}
          <button
            type="button"
            onClick={handleMobileMenu}
            className="md:hidden p-2 text-brand-textMuted hover:text-brand-text"
            aria-label="メニューを開閉"
            aria-expanded={isMenuOpen}
            aria-controls="lp-mobile-menu"
            data-testid="lp-header-mobile-menu"
          >
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 6h16M4 12h16M4 18h16"
              />
            </svg>
          </button>
        </div>
      </div>

      {/* モバイルメニュードロワー */}
      {isMenuOpen && (
        <div className="md:hidden bg-brand-surface border-b border-brand-border" id="lp-mobile-menu">
          <div className="max-w-7xl mx-auto px-4 py-4 space-y-3">
            <button
              type="button"
              onClick={() => {
                handleFeatures();
                setIsMenuOpen(false);
              }}
              className="block w-full text-left px-4 py-3 text-sm font-medium text-brand-textMuted hover:text-brand-text hover:bg-brand-surfaceHover rounded-lg"
              data-testid="lp-mobile-nav-features"
            >
              機能
            </button>
            <button
              type="button"
              onClick={() => {
                scrollToSection('lp-pricing-section');
                setIsMenuOpen(false);
              }}
              className="block w-full text-left px-4 py-3 text-sm font-medium text-brand-textMuted hover:text-brand-text hover:bg-brand-surfaceHover rounded-lg"
              data-testid="lp-mobile-nav-pricing"
            >
              料金
            </button>
            <button
              type="button"
              onClick={() => {
                scrollToSection('lp-faq-section');
                setIsMenuOpen(false);
              }}
              className="block w-full text-left px-4 py-3 text-sm font-medium text-brand-textMuted hover:text-brand-text hover:bg-brand-surfaceHover rounded-lg"
              data-testid="lp-mobile-nav-faq"
            >
              FAQ
            </button>
            <div className="pt-4 border-t border-brand-border">
              <button
                type="button"
                onClick={handleRegister}
                className="w-full px-4 py-3 text-sm font-semibold text-white bg-brand-accent rounded-lg hover:bg-brand-accent-hover transition-colors"
                data-testid="lp-mobile-nav-register"
              >
                無料で始める
              </button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
};

export default LpHeader;