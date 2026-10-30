/**
 * AutoNovel 商業LP - ヒーローセクション（ファーストビュー）
 *
 * ファイル: frontend/src/components/lp/HeroSection.tsx
 *
 * 役割: 3 秒以内に「何のサービスか」「何ができるか」「次に何をすべきか」を伝える。
 * コピー・ビジュアル・CTA ボタンを統合。
 */

import React from 'react';
import { useNavigate } from 'react-router-dom';

export const HeroSection: React.FC = () => {
  const navigate = useNavigate();

  const handlePrimaryCta = () => {
    navigate('/register');
  };

  const handleSecondaryCta = () => {
    // LP は単一ページなので、同じページ内の #features セクションへスクロール
    const el = document.getElementById('lp-features-section');
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' });
    }
  };

  return (
    <section
      id="lp-hero-section"
      className="relative py-16 px-4 sm:py-32 sm:px-6 lg:py-48 lg:px-8 overflow-hidden"
      data-testid="lp-hero-section"
    >
      {/* 背景装飾（サブトリアルな光のグラデーション） */}
      <div className="absolute top-0 left-0 w-full h-full -z-10">
        <div
          className="w-[600px] h-[600px] bg-brand-accent/10 rounded-full blur-[120px] -top-[200px] -left-[100px]"
          aria-hidden="true"
        />
        <div
          className="w-[500px] h-[500px] bg-brand-accentSecondary/10 rounded-full blur-[100px] -bottom-[150px] -right-[100px]"
          aria-hidden="true"
        />
      </div>

      <div className="max-w-7xl mx-auto">
        {/* デスクトップ: 2 カラム / モバイル: スタック */}
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">

          {/* 左: コピー・CTA */}
          <div className="space-y-8" data-testid="lp-hero-content">
            {/* Eyebrow */}
            <div
              className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-brand-accent/10 text-brand-accent text-xs font-semibold border border-brand-accent/20"
              data-testid="lp-hero-eyebrow"
            >
              AI 小説執筆プラットフォーム
            </div>

            {/* H1 メイン見出し */}
            <h1
              className="text-4xl sm:text-5xl lg:text-6xl font-bold text-brand-text leading-tight tracking-tight"
              data-testid="lp-hero-headline"
            >
              条件を入れたら、<br />
              <span className="text-brand-accent">小説が届く。</span>
            </h1>

            {/* サブ見出し */}
            <p
              className="text-lg sm:text-xl text-brand-textMuted leading-relaxed max-w-lg"
              data-testid="lp-hero-subhead"
            >
              企画から執筆、矛盾診断、納品まで。AI と共に創作する小説制作プラットフォーム。<br className="hidden sm:block" />
              8 専門オーディター監査で作品クオリティを保証します。
            </p>

            {/* 信頼バッジ */}
            <div className="flex flex-wrap gap-3" data-testid="lp-hero-badges">
              <span className="px-3 py-1.5 text-xs font-medium text-brand-textMuted bg-brand-surface border border-brand-border rounded-full">
                8 専門オーディター監査
              </span>
              <span className="px-3 py-1.5 text-xs font-medium text-brand-textMuted bg-brand-surface border border-brand-border rounded-full">
                EPUB / なろう・カクヨム対応
              </span>
              <span className="px-3 py-1.5 text-xs font-medium text-brand-textMuted bg-brand-surface border border-brand-border rounded-full">
                クレジットカード不要
              </span>
            </div>

            {/* CTA ボタン */}
            <div className="flex flex-col sm:flex-row gap-4" data-testid="lp-hero-cta-group">
              <button
                type="button"
                onClick={handlePrimaryCta}
                className="w-full sm:w-auto px-8 py-4 text-lg font-semibold text-white bg-brand-accent rounded-xl hover:bg-brand-accent-hover hover:shadow-lg hover:shadow-cyan-500/25 transition-all active:scale-95"
                data-testid="lp-hero-cta-primary"
              >
                無料で始める
              </button>
              <button
                type="button"
                onClick={handleSecondaryCta}
                className="w-full sm:w-auto px-8 py-4 text-lg font-semibold text-brand-text border border-brand-accent/30 rounded-xl hover:bg-brand-accent/10 transition-colors active:scale-95"
                data-testid="lp-hero-cta-secondary"
              >
                機能を見る
              </button>
            </div>
          </div>

          {/* 右: ビジュアル（SVG インライン） */}
          <div
            className="relative h-64 sm:h-80 lg:h-96 flex items-center justify-center"
            data-testid="lp-hero-visual-container"
          >
            <svg
              className="w-full h-full max-w-md sm:max-w-lg"
              viewBox="0 0 800 600"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
              data-testid="lp-hero-visual"
            >
              {/* ペン先の軌跡をモチーフにした抽象図形 */}
              <defs>
                <linearGradient id="heroGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#22d3ee" />
                  <stop offset="100%" stopColor="#a855f7" />
                </linearGradient>
                <filter id="heroGlow" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="15" result="blur" />
                  <feComposite in="SourceGraphic" in2="blur" operator="over" />
                </filter>
              </defs>

              {/* 背景の流線形 */}
              <path
                d="M100 100 Q 400 50 700 100 T 100 100"
                stroke="url(#heroGradient)"
                strokeWidth="3"
                opacity="0.3"
              />
              <path
                d="M100 500 Q 300 100 500 500 T 100 500"
                stroke="url(#heroGradient)"
                strokeWidth="3"
                opacity="0.2"
              />

              {/* ペン先アイコン風 */}
              <path
                d="M400 200 L 450 250 L 400 300 L 350 250 Z"
                fill="url(#heroGradient)"
                filter="url(#heroGlow)"
              />
              <path
                d="M400 200 L 420 220 L 400 240 L 380 220 Z"
                fill="#020617"
              />

              {/* 装飾ドット */}
              <circle cx="150" cy="150" r="4" fill="#22d3ee" opacity="0.6" />
              <circle cx="650" cy="450" r="4" fill="#a855f7" opacity="0.6" />
              <circle cx="200" cy="400" r="3" fill="#22d3ee" opacity="0.4" />
              <circle cx="600" cy="200" r="3" fill="#a855f7" opacity="0.4" />
            </svg>
          </div>
        </div>
      </div>
    </section>
  );
};

export default HeroSection;