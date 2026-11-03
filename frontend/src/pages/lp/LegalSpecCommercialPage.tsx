/**
 * AutoNovel 商業LP - 特定商取引法に基づく表記ページ
 *
 * ファイル: frontend/src/pages/lp/LegalSpecCommercialPage.tsx
 *
 * 役割: 特定商取引法に基づく表記を SPA として表示。
 */

import React from 'react';

export const LegalSpecCommercialPage: React.FC = () => {
  return (
    <div className="min-h-screen bg-brand-dark text-brand-text">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-brand-accent font-bold text-xl tracking-tight">AutoNovel</span>
        </div>
        <h1 className="text-3xl sm:text-4xl font-bold text-brand-text mb-2">
          特定商取引法に基づく表記
        </h1>
        <p className="text-brand-textMuted mb-10">
          AutoNovel を運営する事業者情報を掲載しています。
        </p>

        <div className="prose prose-invert max-w-none text-brand-textMuted">
          <table className="w-full mb-8 text-left">
            <tbody>
              <tr>
                <td className="w-1/4 font-medium text-brand-text border-b border-brand-border py-2">
                  販売事業者
                </td>
                <td className="border-b border-brand-border py-2">AutoNovel 運営</td>
              </tr>
              <tr>
                <td className="w-1/4 font-medium text-brand-text border-b border-brand-border py-2">
                  所在地
                </td>
                <td className="border-b border-brand-border py-2">準備中</td>
              </tr>
              <tr>
                <td className="w-1/4 font-medium text-brand-text border-b border-brand-border py-2">
                  代表者
                </td>
                <td className="border-b border-brand-border py-2">準備中</td>
              </tr>
              <tr>
                <td className="w-1/4 font-medium text-brand-text border-b border-brand-border py-2">
                  お問い合わせ
                </td>
                <td className="border-b border-brand-border py-2">
                  GitHub Issue: <a href="https://github.com/annahoikuen-debug/autonovel/issues" target="_blank" rel="noopener noreferrer" className="text-brand-accent hover:underline">annahoikuen-debug/autonovel/issues</a>
                </td>
              </tr>
              <tr>
                <td className="w-1/4 font-medium text-brand-text border-b border-brand-border py-2">
                  販売価格
                </td>
                <td className="border-b border-brand-border py-2">
                  各プランページをご参照ください（Free ¥0 / Starter ¥980 / Pro ¥2,980 / Enterprise ¥9,800 税込）。
                </td>
              </tr>
              <tr>
                <td className="w-1/4 font-medium text-brand-text border-b border-brand-border py-2">
                  支払方法
                </td>
                <td className="border-b border-brand-border py-2">クレジットカード（Stripe）</td>
              </tr>
              <tr>
                <td className="w-1/4 font-medium text-brand-text border-b border-brand-border py-2">
                  引き渡し時期
                </td>
                <td className="border-b border-brand-border py-2">決済完了後、直ちにサービスをご利用いただけます。</td>
              </tr>
              <tr>
                <td className="w-1/4 font-medium text-brand-text border-b border-brand-border py-2">
                  返金・キャンセル
                </td>
                <td className="border-b border-brand-border py-2">
                  解約はいつでも可能です。利用規約をご参照ください。
                </td>
              </tr>
              <tr>
                <td className="w-1/4 font-medium text-brand-text border-b border-brand-border py-2">
                  動作環境
                </td>
                <td className="border-b border-brand-border py-2">ブラウザ（Chrome / Edge / Firefox / Safari 最新版）</td>
              </tr>
            </tbody>
          </table>
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

export default LegalSpecCommercialPage;
