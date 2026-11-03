/**
 * AutoNovel 商業LP - プライバシーポリシーページ
 *
 * ファイル: frontend/src/pages/lp/LegalPrivacyPage.tsx
 *
 * 役割: プライバシーポリシーを SPA として表示。
 */

import React from 'react';

export const LegalPrivacyPage: React.FC = () => {
  return (
    <div className="min-h-screen bg-brand-dark text-brand-text">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-brand-accent font-bold text-xl tracking-tight">AutoNovel</span>
        </div>
        <h1 className="text-3xl sm:text-4xl font-bold text-brand-text mb-2">
          プライバシーポリシー
        </h1>
        <p className="text-brand-textMuted mb-10">
          AutoNovel（以下、「当サービス」といいます）は、利用者のプライバシーおよび創作データを保護するため、以下の通りプライバシーポリシーを定めます。
        </p>

        <div className="prose prose-invert max-w-none text-brand-textMuted">
          <h2 className="text-brand-text font-bold mb-2">1. 収集する情報</h2>
          <p>当サービスは、小説の執筆支援および管理を行うために、以下の情報を収集・保持する場合があります。</p>
          <ul className="list-disc list-inside mb-4">
            <li>アカウント情報（メールアドレス、ユーザー名等）</li>
            <li>創作データ（小説のプロット、本文、キャラクター設定、世界観設定等）</li>
            <li>利用ログおよびアクセス情報</li>
          </ul>

          <h2 className="text-brand-text font-bold mb-2">2. 創作データの非学習保証（Zero Data Retention）</h2>
          <p>
            当サービスは、<strong>利用者が入力・生成した創作データ（プロット、本文、設定等）を、外部 LLM プロバイダ（OpenAI、Anthropic、Google 等）のモデル訓練や追加学習に利用させない</strong>契約および API 構成を採用しています。
          </p>

          <h2 className="text-brand-text font-bold mb-2">3. 情報の利用目的</h2>
          <p>収集した情報は、以下の目的でのみ利用します。</p>
          <ul className="list-disc list-inside mb-4">
            <li>当サービスの執筆支援、推敲、アシスタント機能の提供および維持</li>
            <li>ユーザーからのお問い合わせへの対応</li>
            <li>サービス改善および不具合の修正</li>
          </ul>

          <h2 className="text-brand-text font-bold mb-2">4. 情報の第三者提供</h2>
          <p>
            当サービスは、法令に基づく場合を除き、利用者の同意を得ることなく、個人情報および創作データを第三者に提供することはありません。
          </p>

          <h2 className="text-brand-text font-bold mb-2">5. 安全管理措置</h2>
          <p>
            当サービスは、不正アクセス、漏洩、滅失、毀損等を防ぐため、通信の暗号化（SSL/TLS）、アクセス制御、データベースの適切な保護など、必要かつ十分なセキュリティ対策を講じます。
          </p>

          <h2 className="text-brand-text font-bold mb-2">6. お問い合わせ</h2>
          <p>
            プライバシーポリシーに関するお問い合わせは、サポート窓口までご連絡ください。
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

export default LegalPrivacyPage;
