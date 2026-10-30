/**
 * AutoNovel 商業LP - 機能セクション
 *
 * ファイル: frontend/src/components/lp/FeaturesSection.tsx
 *
 * 役割: 小説執筆を企画から納品まで一貫してサポートする 8 つの機能を
 * グリッド形式で紹介する。
 */

import React from 'react';
import { FeatureCard } from './FeatureCard';
import {
  CheckCircle2,
  ShieldCheck,
  Zap,
  Package,
  FileTypeEpub,
  Share2,
  Megaphone,
  Palette,
} from 'lucide-react';

// 各機能の定義
const FEATURES = [
  {
    icon: <CheckCircle2 size={24} />,
    title: 'AI 本文生成',
    description:
      'ジャンル・主人公・冒頭プロンプトから本文を自動生成。リアルタイム速筆（SSE）に対応。',
  },
  {
    icon: <ShieldCheck size={24} />,
    title: '8 専門オーディター監査',
    description:
      '矛盾・感情・続き・構成など 8 視点で自動診断し、作品クオリティを保証。',
  },
  {
    icon: <Zap size={24} />,
    title: 'リアルタイム速筆',
    description:
      'テキストがストリーミングで流れ込む。書き進めながら内容を確認。',
  },
  {
    icon: <Package size={24} />,
    title: '納品パッケージ（ZIP）',
    description:
      '本文・設定集・プロット・データを 1 つの ZIP でダウンロード。',
  },
  {
    icon: <FileTypeEpub size={24} />,
    title: 'EPUB / なろう形式出力',
    description:
      '投稿サイト向けに自動整形。なろう・カクヨム形式に対応。',
  },
  {
    icon: <Share2 size={24} />,
    title: '相関図ビジュアル化',
    description:
      'キャラクター関係をグラフで可視化し、設定の整合性を一目で把握。',
  },
  {
    icon: <Megaphone size={24} />,
    title: 'マーケティング支援',
    description:
      'タイトル・キャッチコピー生成（カクヨム 35 文字最適化）。',
  },
  {
    icon: <Palette size={24} />,
    title: 'テーマ切替',
    description: 'ダーク／ライト／セピア。執筆環境を好みに合わせて選択。',
  },
];

export const FeaturesSection: React.FC = () => {
  return (
    <section
      id="lp-features-section"
      className="py-16 px-4 sm:py-24 sm:px-6 lg:py-32 lg:px-8"
      data-testid="lp-features-section"
    >
      <div className="max-w-7xl mx-auto">
        {/* セクション見出し */}
        <div className="text-center mb-16" data-testid="lp-features-header">
          <h2
            className="text-3xl sm:text-4xl font-bold text-brand-text mb-4"
            data-testid="lp-features-title"
          >
            小説執筆を、企画から納品まで一貫してサポート
          </h2>
          <p
            className="text-lg text-brand-textMuted max-w-2xl mx-auto leading-relaxed"
            data-testid="lp-features-desc"
          >
            企画から執筆、矛盾診断、納品まで。AI と共に創作する小説制作プラットフォーム。
          </p>
        </div>

        {/* 機能グリッド */}
        <div
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 sm:gap-8 lg:gap-12"
          data-testid="lp-features-grid"
        >
          {FEATURES.map((feature, index) => (
            <FeatureCard
              key={index}
              index={index}
              icon={feature.icon}
              title={feature.title}
              description={feature.description}
            />
          ))}
        </div>
      </div>
    </section>
  );
};

export default FeaturesSection;