/**
 * AutoNovel 商業LP - FAQ ページ
 *
 * ファイル: frontend/src/pages/lp/FaqPage.tsx
 *
 * 役割: よくある質問を SPA として表示。LP の FAQ セクションからの詳細導線先。
 */

import React from 'react';

interface FaqItem {
  question: string;
  answer: string;
}

const FAQS: FaqItem[] = [
  {
    question: 'AI で生成した小説の著作権は誰に帰属しますか？',
    answer:
      'AutoNovel で生成されたコンテンツの著作権は、利用者（あなた）に帰属します。AI は支援ツールとして機能し、生成物の権利を主張することはありません。',
  },
  {
    question: '無料プランと有料プランの違いは何ですか？',
    answer:
      '無料プランはかんたん執筆を月 5 本まで、基本機能を体験できます。有料プラン（スターター・プロ・エンタープライズ）は無制限執筆（クレジット範囲内）、8 専門オーディター監査、ZIP 納品、優先サポートなどを利用できます。料金詳細は [料金プラン](#) を参照してください。',
  },
  {
    question: 'なろう・カクヨムに直接投稿できますか？',
    answer:
      'EPUB 形式およびなろう・カクヨム形式への自動整形出力に対応しています。出力したファイルを各投稿サイトにアップロードしてご利用ください。',
  },
  {
    question: 'R18 表現は生成できますか？',
    answer:
      '年齢制限に応じたフィルタリング設定が可能です。R18 表現の生成は設定で制御でき、プラットフォームのガイドラインに準拠した利用をお願いします。デフォルトでは無効（ENABLE_NSFW=false）です。',
  },
  {
    question: 'データはどこに保存されますか？',
    answer:
      'ユーザーデータは暗号化されたデータベースに保存されます。プライバシーポリシーに基づき、第三者に提供することはありません。創作データは外部 LLM プロバイダのモデル訓練に利用されない（Zero Data Retention）契約を採用しています。',
  },
  {
    question: '解約はいつでもできますか？',
    answer:
      'はい、いつでも解約できます。解約後は当課金期間の終了日まで有料プランの機能を利用可能です。',
  },
  {
    question: 'クレジットとは何ですか？',
    answer:
      '小説生成・イラスト生成・音声合成などの AI 機能を利用する際に消費される単位です。プランごとに毎月一定量が付与され、不足した場合は都度購入またはプランアップグレードで追加できます。',
  },
  {
    question: 'API キーは必要ですか？',
    answer:
      '開発環境ではデフォルトのモックアダプターが使用されます。本番環境で実 LLM を使用する場合は、設定パネルから API キーを入力してください。',
  },
];

export const FaqPage: React.FC = () => {
  return (
    <div className="min-h-screen bg-brand-dark text-brand-text">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-brand-accent font-bold text-xl tracking-tight">AutoNovel</span>
        </div>
        <h1 className="text-3xl sm:text-4xl font-bold text-brand-text mb-2">
          よくある質問（FAQ）
        </h1>
        <p className="text-brand-textMuted mb-10">
          AutoNovel の利用に関するよくある質問と回答です。
        </p>

        <div className="space-y-4" data-testid="lp-faq-section">
          {FAQS.map((item, index) => (
            <div
              key={index}
              className="border border-brand-border rounded-lg overflow-hidden"
              data-testid={`lp-faq-item-${index}`}
            >
              <button
                type="button"
                id={`lp-faq-button-${index}`}
                onClick={() => {}}
                className="w-full flex items-center justify-between p-4 text-left text-brand-text font-medium hover:bg-brand-surfaceHover transition-colors"
                data-testid={`lp-faq-question-${index}`}
              >
                {item.question}
                <svg
                  className="w-4 h-4 text-brand-textMuted"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M19 9l-7 7-7-7"
                  />
                </svg>
              </button>
              <div className="p-4 text-brand-textMuted border-t border-brand-border" data-testid={`lp-faq-answer-${index}`}>
                {item.answer}
              </div>
            </div>
          ))}
        </div>

        <div className="mt-12 pt-8 border-t border-brand-border">
          <p className="text-brand-textMuted mb-4">
            解決しない問題は、<a href="https://github.com/annahoikuen-debug/autonovel/issues" target="_blank" rel="noopener noreferrer" className="text-brand-accent hover:underline">GitHub Issue</a> またはサポート窓口までお問い合わせください。
          </p>
        </div>
      </div>
    </div>
  );
};

export default FaqPage;
