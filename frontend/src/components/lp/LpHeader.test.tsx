/**
 * AutoNovel 商業LP - LpHeader 単体テスト
 *
 * ファイル: frontend/src/components/lp/LpHeader.test.tsx
 */

import React from 'react';
import { describe, test, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LpHeader } from './LpHeader';

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual =
    await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('LpHeader', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
  });

  test('ロゴ、ナビゲーション、CTA ボタンがレンダリングされる', () => {
    render(
      <MemoryRouter>
        <LpHeader />
      </MemoryRouter>
    );

    expect(screen.getByTestId('lp-header-logo')).toBeInTheDocument();
    expect(screen.getByTestId('lp-header-nav-features')).toBeInTheDocument();
    expect(screen.getByTestId('lp-header-nav-pricing')).toBeInTheDocument();
    expect(screen.getByTestId('lp-header-nav-faq')).toBeInTheDocument();
    expect(screen.getByTestId('lp-header-nav-docs')).toBeInTheDocument();
    expect(screen.getByTestId('lp-header-cta-primary')).toBeInTheDocument();
    expect(screen.getByTestId('lp-header-cta-secondary')).toBeInTheDocument();
  });

  test('プライマリ CTA クリックで /register へ遷移する', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <LpHeader />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByTestId('lp-header-cta-primary'));
    expect(mockNavigate).toHaveBeenCalledWith('/register');
  });

  test('モバイルメニューボタンでドロワーが開閉する', () => {
    render(
      <MemoryRouter>
        <LpHeader />
      </MemoryRouter>
    );

    const menuBtn = screen.getByTestId('lp-header-mobile-menu');
    fireEvent.click(menuBtn);

    expect(screen.getByTestId('lp-mobile-nav-register')).toBeInTheDocument();
    fireEvent.click(menuBtn);
    expect(screen.queryByTestId('lp-mobile-nav-register')).not.toBeInTheDocument();
  });
});
