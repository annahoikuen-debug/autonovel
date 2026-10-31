/**
 * AutoNovel 商業LP - HeroSection 単体テスト
 *
 * ファイル: frontend/src/components/lp/HeroSection.test.tsx
 */

import React from 'react';
import { describe, test, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { HeroSection } from './HeroSection';

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual =
    await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('HeroSection', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
  });

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
    render(
      <MemoryRouter initialEntries={['/']}>
        <HeroSection />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByTestId('lp-hero-cta-primary'));
    expect(mockNavigate).toHaveBeenCalledWith('/register');
  });

  test('セカンダリ CTA クリックで #features セクションへスクロールする', () => {
    const scrollIntoViewMock = vi.fn();
    const originalScrollIntoView = Element.prototype.scrollIntoView;
    // ハンドラは document.getElementById('lp-features-section') を参照するため
    // テスト用のターゲット要素を用意する
    const target = document.createElement('section');
    target.id = 'lp-features-section';

    try {
      Element.prototype.scrollIntoView = scrollIntoViewMock;
      document.body.appendChild(target);

      render(
        <MemoryRouter>
          <HeroSection />
        </MemoryRouter>
      );

      fireEvent.click(screen.getByTestId('lp-hero-cta-secondary'));
      expect(scrollIntoViewMock).toHaveBeenCalledWith({ behavior: 'smooth' });
    } finally {
      Element.prototype.scrollIntoView = originalScrollIntoView;
      target.remove();
    }
  });
});
