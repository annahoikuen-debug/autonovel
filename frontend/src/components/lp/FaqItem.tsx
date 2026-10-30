/**
 * AutoNovel 商業LP - FAQ アコーディオン単体
 *
 * ファイル: frontend/src/components/lp/FaqItem.tsx
 *
 * 役割: 1 つの質問・回答ペアをアコーディオン形式で表示。
 * キーボード操作（Enter/Space）と ARIA 属性に対応。
 */

import React, { useState } from 'react';

interface FaqItemProps {
  index: number;
  question: string;
  answer: string;
}

export const FaqItem: React.FC<FaqItemProps> = ({
  index,
  question,
  answer,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const buttonId = `lp-faq-button-${index}`;
  const panelId = `lp-faq-panel-${index}`;

  const handleClick = () => {
    setIsOpen((prev) => !prev);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      setIsOpen((prev) => !prev);
    }
  };

  return (
    <div
      className="border border-brand-border rounded-lg overflow-hidden"
      data-testid={`lp-faq-item-${index}`}
    >
      <button
        type="button"
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        className="w-full flex items-center justify-between px-5 py-4 text-left bg-brand-surface hover:bg-brand-surfaceHover transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 focus-visible:ring-offset-brand-dark"
        aria-expanded={isOpen}
        aria-controls={panelId}
        data-testid={`lp-faq-question-${index}`}
      >
        <span className="text-base font-medium text-brand-text">{question}</span>
        <svg
          className={`w-5 h-5 transition-transform duration-300 ${
            isOpen ? 'rotate-180' : ''
          }`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 9l-7 7-7-7"
          />
        </svg>
      </button>

      <div
        id={panelId}
        className="px-5 pb-4 border-t border-brand-border bg-brand-surface/50"
        hidden={!isOpen}
        data-testid={`lp-faq-answer-${index}`}
      >
        <p className="text-sm text-brand-textMuted leading-relaxed">
          {answer}
        </p>
      </div>
    </div>
  );
};

export default FaqItem;