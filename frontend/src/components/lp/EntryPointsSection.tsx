/**
 * AutoNovel 商業LP - 3 つの入口セクション
 *
 * ファイル: frontend/src/components/lp/EntryPointsSection.tsx
 *
 * 役割: かんたん執筆・共創ウィザード・Studio の 3 つの入口をカード形式で紹介し、
 * ユーザーを適切な入口へ誘導する。
 */

import React from 'react';
import { NavLink } from 'react-router-dom';

interface EntryPoint {
  id: 'easy' | 'wizard' | 'studio';
  emoji: string;
  title: string;
  description: string;
  ctaLabel: string;
  path: string;
  testId: string;
}

const ENTRY_POINTS: EntryPoint[] = [
  {
    id: 'easy',
    emoji: '⚡',
    title: 'かんたん執筆',
    description: '書きたい内容を入れるだけ。約 1 分で小説が生成されます。',
    ctaLabel: '今すぐ試す',
    path: '/welcome',
    testId: 'lp-entry-easy',
  },
  {
    id: 'wizard',
    emoji: '✨',
    title: '共創ウィザード',
    description: '骨組みから決めてから書く。方針 → 構成 → 執筆の 3 ステップ。',
    ctaLabel: 'ウィザードを始める',
    path: '/app/wizard',
    testId: 'lp-entry-wizard',
  },
  {
    id: 'studio',
    emoji: '🚀',
    title: 'Studio',
    description: '仕上げと詳細設定。既存作品からすぐ編集できます。',
    ctaLabel: 'Studio を開始',
    path: '/app/studio',
    testId: 'lp-entry-studio',
  },
];

export const EntryPointsSection: React.FC = () => {
  return (
    <section
      id="lp-entry-points-section"
      className="py-16 px-4 sm:py-24 sm:px-6 lg:py-32 lg:px-8 bg-brand-surface/30"
      data-testid="lp-entry-points-section"
    >
      <div className="max-w-7xl mx-auto">
        {/* セクション見出し */}
        <div className="text-center mb-16" data-testid="lp-entry-header">
          <h2
            className="text-3xl sm:text-4xl font-bold text-brand-text mb-4"
            data-testid="lp-entry-title"
          >
            3 つの入口 ─ どれから始めても同じ作品に書き足せます
          </h2>
          <p
            className="text-lg text-brand-textMuted max-w-2xl mx-auto leading-relaxed"
            data-testid="lp-entry-desc"
          >
            プログラミングや AI の専門知識がなくても、ブラウザのフォームに条件を入れただけで<br />
            小説が生成され、そのまま納品用 ZIP としてダウンロードできます。
          </p>
        </div>

        {/* 3 つのカードグリッド */}
        <div
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 sm:gap-8 lg:gap-12"
          data-testid="lp-entry-grid"
        >
          {ENTRY_POINTS.map((entry) => (
            <NavLink
              key={entry.id}
              to={entry.path}
              className={`
                group block p-6 sm:p-8 bg-brand-surface border border-brand-border rounded-xl
                hover:border-brand-accent/50 hover:-translate-y-1 hover:shadow-lg
                transition-all duration-300
              `}
              data-testid={entry.testId + '-card'}
            >
              {/* アイコン */}
              <div className="w-12 h-12 rounded-lg bg-brand-accent/10 flex items-center justify-center text-2xl mb-4 group-hover:bg-brand-accent/20 transition-colors" aria-hidden>
                {entry.emoji}
              </div>

              {/* タイトル */}
              <h3
                className="text-lg font-semibold text-brand-text mb-2 group-hover:text-brand-accent transition-colors"
                data-testid={entry.testId + '-title'}
              >
                {entry.title}
              </h3>

              {/* 説明 */}
              <p className="text-sm text-brand-textMuted leading-relaxed mb-6" data-testid={entry.testId + '-desc'}>
                {entry.description}
              </p>

              {/* CTA ボタン */}
              <button
                type="button"
                className="inline-flex items-center gap-2 px-4 py-2.5 text-xs font-semibold text-white bg-brand-accent rounded-lg hover:bg-brand-accent-hover transition-colors"
                data-testid={entry.testId + '-cta'}
              >
                {entry.ctaLabel}
                <svg
                  className="w-4 h-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M14 5l7 7m0 0l-7 7m7-7H3"
                  />
                </svg>
              </button>
            </NavLink>
          ))}
        </div>
      </div>
    </section>
  );
};

export default EntryPointsSection;