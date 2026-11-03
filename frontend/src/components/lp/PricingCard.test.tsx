/**
 * AutoNovel 商業LP - PricingCard 単体テスト
 *
 * ファイル: frontend/src/components/lp/PricingCard.test.tsx
 */

import React from 'react';
import { describe, test, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PricingCard } from './PricingCard';

describe('PricingCard', () => {
  test('プラン名・価格・クレジット・機能リスト・CTA がレンダリングされる（free）', () => {
    const onCtaClick = vi.fn();

    render(
      <PricingCard
        plan="free"
        price="¥0"
        pricePeriod="/ 月"
        title="フリー"
        credits="50クレジット/月"
        description="試し利用。"
        features={['機能A', '機能B']}
        ctaLabel="はじめる"
        onCtaClick={onCtaClick}
      />
    );

    expect(screen.getByTestId('lp-pricing-card-free')).toBeInTheDocument();
    expect(screen.getByTestId('lp-pricing-title-free')).toHaveTextContent(
      'フリー'
    );
    expect(screen.getByTestId('lp-pricing-price-free')).toHaveTextContent(
      '¥0'
    );
    expect(screen.getByTestId('lp-pricing-credits-free')).toHaveTextContent(
      '50クレジット/月'
    );
    expect(screen.getByTestId('lp-pricing-cta-free')).toHaveTextContent(
      'はじめる'
    );
  });

  test('人気プランバッジが表示される（starter）', () => {
    render(
      <PricingCard
        plan="starter"
        price="¥980"
        pricePeriod="/ 月"
        title="スターター"
        credits="300クレジット/月"
        description="本格利用。"
        features={['機能A']}
        isPopular
        ctaLabel="はじめる"
        onCtaClick={() => {}}
      />
    );

    expect(screen.getByTestId('lp-pricing-badge-popular')).toHaveTextContent(
      'Most Popular'
    );
    expect(screen.getByTestId('lp-pricing-card-starter')).toBeInTheDocument();
  });

  test('CTA クリックで onCtaClick が発火する（pro）', () => {
    const onCtaClick = vi.fn();

    render(
      <PricingCard
        plan="pro"
        price="¥2,980"
        pricePeriod="/ 月"
        title="プロ"
        credits="1,200クレジット/月"
        description="上級者。"
        features={['機能A']}
        ctaLabel="はじめる"
        onCtaClick={onCtaClick}
      />
    );

    fireEvent.click(screen.getByTestId('lp-pricing-cta-pro'));
    expect(onCtaClick).toHaveBeenCalledTimes(1);
  });

  test('enterprise プランがレンダリングされる', () => {
    const onCtaClick = vi.fn();

    render(
      <PricingCard
        plan="enterprise"
        price="¥9,800"
        pricePeriod="/ 月"
        title="エンタープライズ"
        credits="5,000クレジット/月"
        description="法人向け。"
        features={['機能A']}
        ctaLabel="お問い合わせ"
        onCtaClick={onCtaClick}
      />
    );

    expect(screen.getByTestId('lp-pricing-card-enterprise')).toBeInTheDocument();
    expect(screen.getByTestId('lp-pricing-title-enterprise')).toHaveTextContent(
      'エンタープライズ'
    );
    expect(screen.getByTestId('lp-pricing-price-enterprise')).toHaveTextContent(
      '¥9,800'
    );
    expect(screen.getByTestId('lp-pricing-credits-enterprise')).toHaveTextContent(
      '5,000クレジット/月'
    );
    expect(screen.getByTestId('lp-pricing-cta-enterprise')).toHaveTextContent(
      'お問い合わせ'
    );
    fireEvent.click(screen.getByTestId('lp-pricing-cta-enterprise'));
    expect(onCtaClick).toHaveBeenCalledTimes(1);
  });
});
