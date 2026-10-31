/**
 * AutoNovel 商業LP - 料金カード（再利用可能）
 *
 * ファイル: frontend/src/components/lp/PricingCard.tsx
 *
 * 役割: 1 つの料金プランを価格・機能リスト・CTA で表現するカード。
 * PricingSection から 3 つのプランをレンダリングする際に使用する。
 */

import React from 'react';

type PlanKey = 'free' | 'standard' | 'pro';

interface PricingCardProps {
  plan: PlanKey;
  price: string;
  pricePeriod: string;
  title: string;
  description: string;
  features: string[];
  isPopular?: boolean;
  ctaLabel: string;
  onCtaClick: () => void;
}

export const PricingCard: React.FC<PricingCardProps> = ({
  plan,
  price,
  pricePeriod,
  title,
  description,
  features,
  isPopular = false,
  ctaLabel,
  onCtaClick,
}) => {
  const planConfigs: Record<PlanKey, { accent: string; bg?: string }> = {
    free: { accent: 'brand-textMuted' },
    standard: {
      accent: 'brand-accent',
      bg: 'bg-brand-surfaceHover',
    },
    pro: { accent: 'brand-accentSecondary' },
  };

  const config = planConfigs[plan];

  return (
    <div
      className={`
        p-6 sm:p-8
        bg-brand-surface
        border
        border-brand-border
        rounded-xl
        relative
        h-full
        flex flex-col
        ${isPopular ? 'border-brand-accent' : 'border-brand-border'}
        ${isPopular ? 'shadow-lg shadow-cyan-500/10' : ''}
        ${config.bg ? config.bg : ''}
      `}
      style={{
        zIndex: isPopular ? 10 : 1,
      }}
      data-testid={`lp-pricing-card-${plan}`}
    >
      {/* 人気プランバッジ */}
      {isPopular && (
        <span
          className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 text-xs font-bold text-white bg-brand-accent rounded-full"
          data-testid="lp-pricing-badge-popular"
        >
          Most Popular
        </span>
      )}

      {/* プラン名 */}
      <h3
        className="text-lg font-semibold text-brand-text mb-2"
        data-testid={`lp-pricing-title-${plan}`}
      >
        {title}
      </h3>

      {/* 価格 */}
      <div className="flex items-baseline gap-1 mb-6" data-testid={`lp-pricing-price-${plan}`}>
        <span className="text-3xl sm:text-4xl font-bold text-brand-text">
          {price}
        </span>
        <span className="text-sm text-brand-textMuted">{pricePeriod}</span>
      </div>

      {/* 説明 */}
      <p className="text-sm text-brand-textMuted mb-6 leading-relaxed">
        {description}
      </p>

      {/* 機能リスト */}
      <ul className="space-y-3 mb-8 flex-grow" data-testid={`lp-pricing-features-${plan}`}>
        {features.map((feature, idx) => (
          <li key={idx} className="flex items-start gap-2 text-sm text-brand-textMuted" data-testid={`lp-pricing-feature-${plan}-${idx}`}>
            <span className="w-5 h-5 flex-shrink-0 mt-0.5 text-brand-accent">
              ✓
            </span>
            {feature}
          </li>
        ))}
      </ul>

      {/* CTA ボタン */}
      <button
        type="button"
        onClick={onCtaClick}
        className={`
          w-full py-3 text-sm font-semibold rounded-lg transition-colors
          ${isPopular
            ? 'bg-brand-accent text-white hover:bg-brand-accent-hover shadow-lg shadow-cyan-500/25'
            : 'bg-brand-surface text-brand-text border border-brand-border hover:border-brand-accent/50'
          }
        `}
        data-testid={`lp-pricing-cta-${plan}`}
      >
        {ctaLabel}
      </button>
    </div>
  );
};

export default PricingCard;