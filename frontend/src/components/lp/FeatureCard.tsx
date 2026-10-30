/**
 * AutoNovel 商業LP - 機能カード（再利用可能）
 *
 * ファイル: frontend/src/components/lp/FeatureCard.tsx
 *
 * 役割: 1 つの機能をアイコン・タイトル・説明で表現するカード。
 * FeaturesSection から 8 つのカードをレンダリングする際に使用する。
 */

import React from 'react';

interface FeatureCardProps {
  index: number; // アニメーション遅延用
  icon: React.ReactNode;
  title: string;
  description: string;
}

export const FeatureCard: React.FC<FeatureCardProps> = ({
  index,
  icon,
  title,
  description,
}) => {
  return (
    <div
      className="
        p-6 sm:p-8
        bg-brand-surface
        border border-brand-border
        rounded-xl
        hover:border-brand-accent/50
        hover:-translate-y-1
        hover:shadow-lg
        transition-all duration-300
        h-full
      "
      style={{
        transitionDelay: `${index * 0.1}s`,
      }}
      data-testid={`lp-feature-card-${index}`}
    >
      {/* アイコン */}
      <div
        className="
          w-12 h-12
          rounded-lg
          bg-brand-accent/10
          flex items-center justify-center
          text-brand-accent
          mb-5
        "
        data-testid={`lp-feature-icon-${index}`}
      >
        {icon}
      </div>

      {/* タイトル */}
      <h3
        className="text-base font-semibold text-brand-text mb-3"
        data-testid={`lp-feature-title-${index}`}
      >
        {title}
      </h3>

      {/* 説明 */}
      <p
        className="text-sm text-brand-textMuted leading-relaxed"
        data-testid={`lp-feature-desc-${index}`}
      >
        {description}
      </p>
    </div>
  );
};

export default FeatureCard;