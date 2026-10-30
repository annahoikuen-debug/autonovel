/**
 * AutoNovel 商業LP - HeroSection 単体テスト
 *
 * ファイル: frontend/src/components/lp/HeroSection.test.tsx
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { HeroSection } from './HeroSection';

describe('HeroSection', () => {
  test('H1 メイン見出し、サブ見出し、CTA 2 つがレンダリングされる', () => {
    render(
      <MemoryRouter>
        <HeroSection />
      </MemoryRouter>
    );

    expect(screen.getByTestId('lp-hero-eyebrow')).toBeInTheDocument();
    expect(screen.getByTestId('lp-hero-headline')).toBeInTheDocument();
    expect(screen.getByTestId('lp-hero-subhead')).toBeInTheDocument();
    expect(screen.getByTestId('lp-hero-cta-primary')).toBeInTheDocument();
    expect(screen.getByTestId('lp-hero-cta-secondary')).toBeInTheDocument();
    expect(screen.getByTestId('lp-hero-badges')).toBeInTheDocument();
  });

  test('プライマリ CTA クリックで /register へ遷移する', () => {
    const { navigate } = render(
      <MemoryRouter initialEntries={['/']}>
        <HeroSection />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByTestId('lp-hero-cta-primary'));
    expect(navigate).toHaveBeenCalledWith('/register');
  });

  test('セカンダリ CTA クリックで #features セクションへスクロールする', () => {
    const scrollIntoViewMock = jest.fn();
    // eslint-disable-next-line @typescript-eslint/no-empty-function
    const originalScrollIntoView = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = scrollIntoViewMock as any;

    render(
      <MemoryRouter>
        <HeroSection />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByTestId('lp-hero-cta-secondary'));

    Element.prototype.scrollIntoView = originalScrollIntoView;
    expect(scrollIntoViewMock).toHaveBeenCalledWith({ behavior: 'smooth' });
  });
});
