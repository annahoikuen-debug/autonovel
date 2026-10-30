/**
 * AutoNovel 商業LP - 最終 CTA セクション
 *
 * ファイル: frontend/src/components/lp/FinalCtaSection.tsx
 *
 * 役割: ページ最後のコンバージョン集中エリア。登録を促す。
 */

import React from 'react';
import { useNavigate } from 'react-router-dom';

export const FinalCtaSection: React.FC = () => {
  const navigate = useNavigate();

  const handleRegister = () => {
    navigate('/register');
  };

  return (
    <section
      id="lp-final-cta-section"
      className="
        py-16 px-4 sm:py-24 sm:px-6 lg:py-32 lg:px-8
        bg-brand-accent/10
        border-t border-brand-border
        rounded-2xl
        overflow-hidden
      "
      data-testid="lp-final-cta-section"
    >
      <div className="max-w-4xl mx-auto text-center">
        {/* 見出し */}
        <h2
          className="text-3xl sm:text-4xl font-bold text-brand-text mb-4"
          data-testid="lp-final-cta-title"
        >
          今すぐ小説を書き始める
        </h2>

        {/* 説明 */}
        <p
          className="text-lg text-brand-textMuted mb-8 max-w-xl mx-auto leading-relaxed"
          data-testid="lp-final-cta-desc"
        >
          登録は 1 分。クレジットカード不要。AI と共に創作を始めましょう。
        </p>

        {/* CTA ボタン */}
        <button
          type="button"
          onClick={handleRegister}
          className="
            w-full sm:w-auto
            px-8 py-4
            text-lg font-semibold text-white
            bg-brand-accent rounded-xl
            hover:bg-brand-accent-hover
            hover:shadow-lg hover:shadow-cyan-500/30
            transition-all
            active:scale-95
          "
          data-testid="lp-final-cta-button"
        >
          無料アカウントを作成する
        </button>

        {/* 信頼文 */}
        <p
          className="mt-4 text-sm text-brand-textMuted"
          data-testid="lp-final-cta-trust"
        >
          30 日以内ならいつでも解約可能
        </p>
      </div>
    </section>
  );
};

export default FinalCtaSection;