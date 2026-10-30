/**
 * AutoNovel 商業LP - レイアウトコンポーネント
 *
 * ファイル: frontend/src/components/lp/LpLayout.tsx
 *
 * 役割: Header + main + Footer を統一したラッパー。
 * 既存 AppLayout（認証必須アプリ用）とは別系統で、認証ガードをかけない。
 */

import React, { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { LpHeader } from './LpHeader';
import { LpFooter } from './LpFooter';

interface LpLayoutProps {
  children?: React.ReactNode;
}

export const LpLayout: React.FC<LpLayoutProps> = ({ children }) => {
  const location = useLocation();

  // ページ遷移時にスクロール位置をトップにリセット
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location]);

  return (
    <div className="min-h-screen flex flex-col bg-brand-dark text-brand-text">
      <LpHeader />
      <main className="flex-grow">{children}</main>
      <LpFooter />
    </div>
  );
};

export default LpLayout;