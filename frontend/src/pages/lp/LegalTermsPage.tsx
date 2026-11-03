/**
 * AutoNovel 商業LP - 利用規約ページ
 *
 * ファイル: frontend/src/pages/lp/LegalTermsPage.tsx
 *
 * 役割: 利用規約を SPA として表示。
 */

import React from 'react';

export const LegalTermsPage: React.FC = () => {
  return (
    <div className="min-h-screen bg-brand-dark text-brand-text">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-brand-accent font-bold text-xl tracking-tight">AutoNovel</span>
        </div>
        <h1 className="text-3xl sm:text-4xl font-bold text-brand-text mb-2">
          利用規約 (Terms of Service)
        </h1>
        <p className="text-brand-textMuted mb-10">
          本利用規約（以下、「本規約」といいます）は、AutoNovel（以下、「当サービス」といいます）の提供条件および利用者の皆様と当サービス運営者との間の権利義務関係を定めるものです。
        </p>

        <div className="prose prose-invert max-w-none text-brand-textMuted">
          <h2 className="text-brand-text font-bold mb-2">第1条（適用）</h2>
          <p>
            1. 本規約は、当サービスの提供および利用に関する一切の事項に適用されます。<br/>
            2. 利用者は、本規約に同意した上で、当サービスを利用するものとします。
          </p>

          <h2 className="text-brand-text font-bold mb-2">第2条（知的財産権の帰属）</h2>
          <p>
            1. 当サービスを利用して生成された小説、プロット、キャラクター設定、その他の創作物（以下、「生成コンテンツ」といいます）に関する著作権その他の知的財産権は、<strong>すべて利用者に帰属</strong>します。<br/>
            2. 当サービス運営者は、利用者の明示的な事前の承諾がない限り、生成コンテンツを第三者に公開、譲渡、または商業利用することはありません。
          </p>

          <h2 className="text-brand-text font-bold mb-2">第3条（外部プラットフォームへの投稿に関する免責）</h2>
          <p>
            1. 当サービスは、各小説投稿プラットフォーム（「小説家になろう」「カクヨム」「アルファポリス」「KDP」等）の利用規約およびガイドラインを遵守する半自動投稿アシスタント機能を提供します。<br/>
            2. 各プラットフォーム側の仕様変更、規約改定、またはシステム的措置により発生した、アカウントの凍結（BAN）、警告、コンテンツの削除等について、当サービス運営者は一切の責任を負いません。
          </p>

          <h2 className="text-brand-text font-bold mb-2">第4条（損害賠償の制限）</h2>
          <p>
            当サービス運営者は、当サービスの利用に関連して利用者に生じた損害について、故意または重大な過失がある場合を除き、一切の責任を負わないものとします。
          </p>

          <h2 className="text-brand-text font-bold mb-2">第5条（規約の変更）</h2>
          <p>
            当サービス運営者は、必要と認めるときは、本規約を変更できるものとし、変更後の規約は当サービス上で掲示した時点から効力を生じるものとします。
          </p>

          <p className="mt-8 text-xs text-brand-textMuted">
            制定日: 2026年9月14日 | サービス名: AutoNovel
          </p>
        </div>

        <div className="mt-12 pt-8 border-t border-brand-border">
          <a
            href="/"
            className="text-brand-accent hover:underline"
          >
            ← ランディングページに戻る
          </a>
        </div>
      </div>
    </div>
  );
};

export default LegalTermsPage;
