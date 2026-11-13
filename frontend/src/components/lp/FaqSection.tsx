/**
 * AutoNovel 商業LP - FAQ セクション
 *
 * ファイル: frontend/src/components/lp/FaqSection.tsx
 *
 * 役割: ユーザーの不安を解消し、コンバージョンの障壁を取り除くための
 * アコーディオン形式 FAQ を実装する。
 */

import React from 'react';
import { FaqItem } from './FaqItem';
import { useNavigate } from 'react-router-dom';

const FAQS = [
  {
    question: 'AI で生成した小説の著作権は誰に帰属しますか？',
    answer:
      '利用者（あなた）に帰属します。AI は支援ツールとして機能し、生成物の権利を主張することはありません。',
  },
  {
    question: '無料プランと有料プランの違いは何ですか？',
    answer:
      '無料プランはかんたん執筆を月 5 本まで。有料プラン（スターター・プロ・エンタープライズ）は無制限執筆、二層ハイブリッド監査、ZIP 納品、優先サポートを利用できます。',
  },
  {
    question: 'なろう・カクヨムに直接投稿できますか？',
    answer:
      'EPUB 形式およびなろう・カクヨム形式への自動整形出力に対応しています。出力したファイルを各投稿サイトにアップロードしてご利用ください。',
  },
  {
    question: '解約はいつでもできますか？',
    answer:
      'はい、いつでも解約可能です。解約後も現在の課金期間終了まで有料機能をご利用いただけます。',
  },
];

export const FaqSection: React.FC = () => {
  const navigate = useNavigate();

  const handleViewAll = () => {
    navigate('/faq');
  };

  return (
    <section
      id="lp-faq-section"
      className="py-16 px-4 sm:py-24 sm:px-6 lg:py-32 lg:px-8 bg-brand-surface/30"
      data-testid="lp-faq-section"
    >
      <div className="max-w-3xl mx-auto">
        {/* セクション見出し */}
        <div className="text-center mb-12" data-testid="lp-faq-header">
          <h2
            className="text-3xl sm:text-4xl font-bold text-brand-text mb-4"
            data-testid="lp-faq-title"
          >
            よくある質問
          </h2>
          <p
            className="text-lg text-brand-textMuted leading-relaxed"
            data-testid="lp-faq-desc"
          >
            ご利用前に知っておきたいポイントをまとめました。
          </p>
        </div>

        {/* FAQ アコーディオンリスト（上位4項目、詳細は /faq へ） */}
        <div
          className="space-y-3"
          data-testid="lp-faq-list"
        >
          {FAQS.map((faq, index) => (
            <FaqItem
              key={index}
              index={index}
              question={faq.question}
              answer={faq.answer}
            />
          ))}
        </div>

        {/* 全項目導線 */}
        <div className="mt-10 pt-8 border-t border-brand-border text-center">
          <p className="text-brand-textMuted mb-4">
            全 7 項目の詳細な回答はドキュメントをご覧ください。
          </p>
          <button
            type="button"
            onClick={handleViewAll}
            className="inline-flex items-center gap-2 text-brand-accent font-medium hover:underline transition-colors"
            data-testid="lp-faq-view-all"
          >
            全 FAQ を見る →
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M13 19l-7-7 7-7"
              />
            </svg>
          </button>
        </div>
      </div>
    </section>
  );
};

export default FaqSection;