/**
 * AutoNovel 商業LP - 料金セクション
 *
 * ファイル: frontend/src/components/lp/PricingSection.tsx
 *
 * 役割: シンプルで透明な料金体系を提示し、有料プランへのコンバージョンを促す。
 * 料金は仮設定。実際の課金体系と連携して差し替えること。
 */

import React from 'react';
import { PricingCard } from './PricingCard';

export const PricingSection: React.FC = () => {
  const plans = [
    {
      plan: 'free' as const,
      price: '¥0',
      pricePeriod: '/ 月',
      title: 'フリー',
      description: '試し利用。基本機能を体験できます。',
      features: [
        'かんたん執筆 月 5 本まで',
        '基本機能（AI 本文生成）',
        'コミュニティサポート',
      ],
      ctaLabel: 'はじめる',
      onCtaClick: () => {
        // eslint-disable-next-line no-console
        console.log('Free plan CTA clicked');
      },
    },
    {
      plan: 'standard' as const,
      price: '¥980',
      pricePeriod: '/ 月',
      title: 'スタンダード',
      description: '本格利用。無制限執筆と監査機能を利用。',
      features: [
        '無制限執筆',
        '8 専門オーディター監査',
        'ZIP 納品パッケージ',
        'メールサポート',
      ],
      isPopular: true,
      ctaLabel: 'はじめる',
      onCtaClick: () => {
        // eslint-disable-next-line no-console
        console.log('Standard plan CTA clicked');
      },
    },
    {
      plan: 'pro' as const,
      price: '¥2,980',
      pricePeriod: '/ 月',
      title: 'プロ',
      description: 'プロ・上級者。Studio 全機能と優先サポート。',
      features: [
        'Studio 全機能',
        'EPUB / なろう形式出力',
        '優先サポート',
        'マーケティング支援',
      ],
      ctaLabel: 'はじめる',
      onCtaClick: () => {
        // eslint-disable-next-line no-console
        console.log('Pro plan CTA clicked');
      },
    },
  ];

  return (
    <section
      id="lp-pricing-section"
      className="py-16 px-4 sm:py-24 sm:px-6 lg:py-32 lg:px-8 bg-brand-dark"
      data-testid="lp-pricing-section"
    >
      <div className="max-w-7xl mx-auto">
        {/* セクション見出し */}
        <div className="text-center mb-16" data-testid="lp-pricing-header">
          <h2
            className="text-3xl sm:text-4xl font-bold text-brand-text mb-4"
            data-testid="lp-pricing-title"
          >
            シンプルで透明な料金体系
          </h2>
          <p
            className="text-lg text-brand-textMuted max-w-2xl mx-auto leading-relaxed"
            data-testid="lp-pricing-desc"
          >
            クレジットカード不要。いつでも解約可能です。
          </p>
        </div>

        {/* 料金プラングリッド */}
        <div
          className="grid grid-cols-1 md:grid-cols-3 gap-6 sm:gap-8 lg:gap-12"
          data-testid="lp-pricing-grid"
        >
          {plans.map((plan) => (
            <PricingCard
              key={plan.plan}
              {...plan}
            />
          ))}
        </div>
      </div>
    </section>
  );
};

export default PricingSection;