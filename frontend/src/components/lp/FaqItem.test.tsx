/**
 * AutoNovel 商業LP - FaqItem 単体テスト
 *
 * ファイル: frontend/src/components/lp/FaqItem.test.tsx
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { FaqItem } from './FaqItem';

describe('FaqItem', () => {
  test('質問と回答がレンダリングされ、初期状態では回答が非表示', () => {
    render(<FaqItem index={0} question="テスト質問" answer="テスト回答" />);

    expect(screen.getByTestId('lp-faq-question-0')).toHaveTextContent(
      'テスト質問'
    );
    expect(screen.queryByTestId('lp-faq-answer-0')).not.toBeInTheDocument();
  });

  test('質問クリックで回答が表示・非表示に切り替わる', () => {
    render(<FaqItem index={0} question="テスト質問" answer="テスト回答" />);

    fireEvent.click(screen.getByTestId('lp-faq-question-0'));
    expect(screen.getByTestId('lp-faq-answer-0')).toBeInTheDocument();
    expect(screen.getByTestId('lp-faq-answer-0')).toHaveTextContent(
      'テスト回答'
    );

    fireEvent.click(screen.getByTestId('lp-faq-question-0'));
    expect(screen.queryByTestId('lp-faq-answer-0')).not.toBeInTheDocument();
  });

  test('Enter キーでアコーディオンが開く', () => {
    render(<FaqItem index={0} question="テスト質問" answer="テスト回答" />);

    const button = screen.getByTestId('lp-faq-question-0');
    fireEvent.keyDown(button, { key: 'Enter' });
    expect(screen.getByTestId('lp-faq-answer-0')).toBeInTheDocument();
  });

  test('aria-expanded が状態に応じて変化する', () => {
    render(<FaqItem index={0} question="テスト質問" answer="テスト回答" />);

    const button = screen.getByTestId('lp-faq-question-0');
    expect(button.getAttribute('aria-expanded')).toBe('false');

    fireEvent.click(button);
    expect(button.getAttribute('aria-expanded')).toBe('true');
  });
});
