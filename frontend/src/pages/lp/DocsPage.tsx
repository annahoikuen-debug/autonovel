/**
 * AutoNovel 商業LP - ドキュメントページ
 *
 * ファイル: frontend/src/pages/lp/DocsPage.tsx
 *
 * 役割: docs/ のインデックスを SPA として表示。LP からの導線先。
 */

import React from 'react';
import { Link } from 'react-router-dom';

export const DocsPage: React.FC = () => {
  return (
    <div className="min-h-screen bg-brand-dark text-brand-text">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <h1 className="text-3xl sm:text-4xl font-bold text-brand-text mb-6">
          ドキュメント
        </h1>
        <p className="text-brand-textMuted mb-10">
          AutoNovel のユーザーガイド、Q&A、開発者向けドキュメント、法務情報です。
        </p>

        <section className="mb-12">
          <h2 className="text-2xl font-bold text-brand-text mb-4">👥 ユーザー向け</h2>
          <ul className="space-y-4">
            <li>
              <Link to="/app/easy" className="text-brand-accent hover:underline">
                かんたん執筆（Easy Mode）
              </Link>{' '}
              — 初心者向け、約1分で小説生成
            </li>
            <li>
              <Link to="/app/wizard" className="text-brand-accent hover:underline">
                共創ウィザード
              </Link>{' '}
              — 骨組みから作る3ステップ
            </li>
            <li>
              <Link to="/app/studio" className="text-brand-accent hover:underline">
                Studio
              </Link>{' '}
              — 仕上げ・詳細設定
            </li>
            <li>
              <Link to="/faq" className="text-brand-accent hover:underline">
                よくある質問（FAQ）
              </Link>
            </li>
            <li>
              <a
                href="docs/easy_mode_guide.md"
                target="_blank"
                rel="noopener noreferrer"
                className="text-brand-accent hover:underline"
              >
                ユーザーガイド（Markdown）
              </a>
            </li>
          </ul>
        </section>

        <section className="mb-12">
          <h2 className="text-2xl font-bold text-brand-text mb-4">⚖️ 法務</h2>
          <ul className="space-y-4">
            <li>
              <Link to="/legal/privacy" className="text-brand-accent hover:underline">
                プライバシーポリシー
              </Link>
            </li>
            <li>
              <Link to="/legal/terms" className="text-brand-accent hover:underline">
                利用規約
              </Link>
            </li>
            <li>
              <Link to="/legal/spec-commercial" className="text-brand-accent hover:underline">
                特定商取引法に基づく表記
              </Link>
            </li>
          </ul>
        </section>

        <section className="mb-12">
          <h2 className="text-2xl font-bold text-brand-text mb-4">👨‍💻 開発者向け</h2>
          <ul className="space-y-4">
            <li>
              <a
                href="docs/development_guide.md"
                target="_blank"
                rel="noopener noreferrer"
                className="text-brand-accent hover:underline"
              >
                開発者ガイド
              </a>
            </li>
            <li>
              <a
                href="docs/architecture.md"
                target="_blank"
                rel="noopener noreferrer"
                className="text-brand-accent hover:underline"
              >
                アーキテクチャ設計
              </a>
            </li>
            <li>
              <a
                href="docs/api.md"
                target="_blank"
                rel="noopener noreferrer"
                className="text-brand-accent hover:underline"
              >
                APIリファレンス
              </a>
            </li>
            <li>
              <a
                href="https://github.com/annahoikuen-debug/autonovel"
                target="_blank"
                rel="noopener noreferrer"
                className="text-brand-accent hover:underline"
              >
                GitHub リポジトリ
              </a>
            </li>
          </ul>
        </section>

        <div className="pt-8 border-t border-brand-border text-xs text-brand-textMuted">
          より詳細なドキュメント一覧は{' '}
          <a
            href="docs/README.md"
            target="_blank"
            rel="noopener noreferrer"
            className="text-brand-accent hover:underline"
          >
            docs/README.md
          </a>
          {' '} を参照してください。
        </div>
      </div>
    </div>
  );
};

export default DocsPage;
