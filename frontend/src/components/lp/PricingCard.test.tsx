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
  test('プラン名・価格・機能リスト・CTA がレンダリングされる', () => {
    const onCtaClick = vi.fn();

    render(
      <PricingCard
        plan="free"
        price="¥0"
        pricePeriod="/ 月"
        title="フリー"
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
    expect(screen.getByTestId('lp-pricing-cta-free')).toHaveTextContent(
      'はじめる'
    );
  });

  test('人気プランバッジが表示される', () => {
    render(
      <PricingCard
        plan="standard"
        price="¥980"
        pricePeriod="/ 月"
        title="スタンダード"
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
  });

  test('CTA クリックで onCtaClick が発火する', () => {
    const onCtaClick = vi.fn();

    render(
      <PricingCard
        plan="pro"
        price="¥2,980"
        pricePeriod="/ 月"
        title="プロ"
        description="上級者。"
        features={['機能A']}
        ctaLabel="はじめる"
        onCtaClick={onCtaClick}
      />
    );

    fireEvent.click(screen.getByTestId('lp-pricing-cta-pro'));
    expect(onCtaClick).toHaveBeenCalledTimes(1);
  });
});
