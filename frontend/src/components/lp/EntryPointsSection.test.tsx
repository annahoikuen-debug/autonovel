/**
 * AutoNovel 商業LP - EntryPointsSection 単体テスト
 *
 * ファイル: frontend/src/components/lp/EntryPointsSection.test.tsx
 */

import React from 'react';
import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { EntryPointsSection } from './EntryPointsSection';

describe('EntryPointsSection', () => {
  test('3 つの入口カードがレンダリングされる', () => {
    render(
      <MemoryRouter>
        <EntryPointsSection />
      </MemoryRouter>
    );

    expect(screen.getByTestId('lp-entry-easy-card')).toBeInTheDocument();
    expect(screen.getByTestId('lp-entry-wizard-card')).toBeInTheDocument();
    expect(screen.getByTestId('lp-entry-studio-card')).toBeInTheDocument();
  });

  test('各入口カードにタイトル・説明・CTA が表示される', () => {
    render(
      <MemoryRouter>
        <EntryPointsSection />
      </MemoryRouter>
    );

    expect(screen.getByTestId('lp-entry-easy-title')).toHaveTextContent(
      'かんたん執筆'
    );
    expect(screen.getByTestId('lp-entry-wizard-title')).toHaveTextContent(
      '共創ウィザード'
    );
    expect(screen.getByTestId('lp-entry-studio-title')).toHaveTextContent(
      'Studio'
    );

    expect(screen.getByTestId('lp-entry-easy-cta')).toBeInTheDocument();
    expect(screen.getByTestId('lp-entry-wizard-cta')).toBeInTheDocument();
    expect(screen.getByTestId('lp-entry-studio-cta')).toBeInTheDocument();
  });

  test('かんたん執筆 CTA は /welcome へのリンク', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <EntryPointsSection />
      </MemoryRouter>
    );

    // NavLink（a 要素）の遷移先を検証する
    const cta = screen.getByTestId('lp-entry-easy-cta');
    const link = cta.closest('a');
    expect(link).not.toBeNull();
    expect(link).toHaveAttribute('href', '/welcome');
  });

  test('Studio CTA は /app/studio へのリンク', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <EntryPointsSection />
      </MemoryRouter>
    );

    const cta = screen.getByTestId('lp-entry-studio-cta');
    const link = cta.closest('a');
    expect(link).not.toBeNull();
    expect(link).toHaveAttribute('href', '/app/studio');
  });
});
