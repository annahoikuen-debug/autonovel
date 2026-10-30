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

const FAQS = [
  {
    question: 'AI で生成した小説の著作権は誰に帰属しますか？',
    answer:
      'AutoNovel で生成されたコンテンツの著作権は、利用者（あなた）に帰属します。AI は支援ツールとして機能し、生成物の権利を主張することはありません。',
  },
  {
    question: '無料プランと有料プランの違いは何ですか？',
    answer:
      '無料プランはかんたん執筆を月 5 本まで、基本機能を体験できます。有料プラン（スタンダード・プロ）は無制限執筆、8 専門オーディター監査、ZIP 納品、優先サポートなどを利用できます。',
  },
  {
    question: 'なろう・カクヨムに直接投稿できますか？',
    answer:
      'EPUB 形式およびなろう・カクヨム形式への自動整形出力に対応しています。出力したファイルを各投稿サイトにアップロードしてご利用ください。',
  },
  {
    question: 'R18 表現は生成できますか？',
    answer:
      '年齢制限に応じたフィルタリング設定が可能です。R18 表現の生成は設定で制御でき、プラットフォームのガイドラインに準拠した利用をお願いします。',
  },
  {
    question: 'データはどこに保存されますか？',
    answer:
      'ユーザーデータは暗号化されたデータベースに保存されます。プライバシーポリシーに基づき、第三者に提供することはありません。',
  },
  {
    question: '解約はいつでもできますか？',
    answer:
      'はい、いつでも解約可能です。解約後も現在の課金期間終了まで有料機能をご利用いただけます。',
  },
  {
    question: 'サポートは受けられますか？',
    answer:
      'スタンダードプラン以上ではメールサポートを、プロプランでは優先サポートを提供しています。ドキュメントとヘルプセンターもご利用いただけます。',
  },
];

export const FaqSection: React.FC = () => {
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

        {/* FAQ アコーディオンリスト */}
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
      </div>
    </section>
  );
};

export default FaqSection;