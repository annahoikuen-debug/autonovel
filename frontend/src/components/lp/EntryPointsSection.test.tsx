/**
 * AutoNovel 商業LP - EntryPointsSection 単体テスト
 *
 * ファイル: frontend/src/components/lp/EntryPointsSection.test.tsx
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
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

  test('かんたん執筆 CTA クリックで /welcome へ遷移する', () => {
    const { navigate } = render(
      <MemoryRouter initialEntries={['/']}>
        <EntryPointsSection />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByTestId('lp-entry-easy-cta'));
    expect(navigate).toHaveBeenCalledWith('/welcome');
  });

  test('Studio CTA クリックで /studio へ遷移する', () => {
    const { navigate } = render(
      <MemoryRouter initialEntries={['/']}>
        <EntryPointsSection />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByTestId('lp-entry-studio-cta'));
    expect(navigate).toHaveBeenCalledWith('/studio');
  });
});
