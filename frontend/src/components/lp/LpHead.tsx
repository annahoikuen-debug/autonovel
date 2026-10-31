/**
 * AutoNovel 商業LP - SEO / OGP ヘッドコンポーネント
 *
 * ファイル: frontend/src/components/lp/LpHead.tsx
 *
 * 役割: 検索エンジンと SNS シェア時に最適なタイトル・説明・OGP 画像を
 * <head> に注入する。LpPage で使用する。
 */

import React, { useEffect } from 'react';

/**
 * サイトのオリジン。
 *
 * 1. `VITE_SITE_URL`（本番ドメイン）が指定されていればそれを使用
 * 2. 未指定なら実行時の `window.location.origin`（プレビュー/ステージングでも
 *    canonical が placeholder のまま検索エンジンに渡るのを防ぐ）
 * 3. それも無い環境（SSR 等）のみフォールバック
 */
const siteOrigin = (
  (import.meta.env.VITE_SITE_URL as string | undefined) ??
  (typeof window !== 'undefined' ? window.location.origin : '')
).replace(/\/$/, '');

interface LpHeadProps {
  title?: string;
  description?: string;
  canonicalUrl?: string;
  ogImage?: string;
}

export const LpHead: React.FC<LpHeadProps> = ({
  title = 'AutoNovel | 条件を入れたら、小説が届く AI 小説執筆プラットフォーム',
  description =
    '企画から執筆、矛盾診断、納品まで。AI と共に創作する小説制作プラットフォーム。8 専門オーディター監査。無料で始められます。',
  canonicalUrl = `${siteOrigin}/`,
  ogImage = `${siteOrigin}/ogp.png`,
}) => {
  useEffect(() => {
    // タイトル
    document.title = title;

    // メタディスクリプション
    let metaDesc = document.querySelector('meta[name="description"]');
    if (!metaDesc) {
      metaDesc = document.createElement('meta');
      metaDesc.setAttribute('name', 'description');
      document.head.appendChild(metaDesc);
    }
    metaDesc.setAttribute('content', description);

    // キーワード
    let metaKeywords = document.querySelector('meta[name="keywords"]');
    if (!metaKeywords) {
      metaKeywords = document.createElement('meta');
      metaKeywords.setAttribute('name', 'keywords');
      document.head.appendChild(metaKeywords);
    }
    metaKeywords.setAttribute(
      'content',
      'AI小説, 小説執筆, なろう, カクヨム, AI ライトノベル, 物語生成, 小説支援ツール'
    );

    // Canonical URL
    let linkCanonical = document.querySelector('link[rel="canonical"]');
    if (!linkCanonical) {
      linkCanonical = document.createElement('link');
      linkCanonical.setAttribute('rel', 'canonical');
      document.head.appendChild(linkCanonical);
    }
    linkCanonical.setAttribute('href', canonicalUrl);

    // OGP
    const setOg = (property: string, content: string) => {
      let el = document.querySelector(`meta[property="${property}"]`);
      if (!el) {
        el = document.createElement('meta');
        el.setAttribute('property', property);
        document.head.appendChild(el);
      }
      el.setAttribute('content', content);
    };

    setOg('og:type', 'website');
    setOg('og:title', title);
    setOg('og:description', description);
    setOg('og:image', ogImage);
    setOg('og:url', canonicalUrl);
    setOg('og:site_name', 'AutoNovel');
    setOg('og:locale', 'ja_JP');

    // Twitter Card
    let twitterCard = document.querySelector('meta[name="twitter:card"]');
    if (!twitterCard) {
      twitterCard = document.createElement('meta');
      twitterCard.setAttribute('name', 'twitter:card');
      document.head.appendChild(twitterCard);
    }
    twitterCard.setAttribute('content', 'summary_large_image');

    let twitterImage = document.querySelector('meta[name="twitter:image"]');
    if (!twitterImage) {
      twitterImage = document.createElement('meta');
      twitterImage.setAttribute('name', 'twitter:image');
      document.head.appendChild(twitterImage);
    }
    twitterImage.setAttribute('content', ogImage);

    // 構造化データ（JSON-LD）: WebSite + Organization
    const ldJson = {
      '@context': 'https://schema.org',
      '@graph': [
        {
          '@type': 'WebSite',
          '@id': `${canonicalUrl}#website`,
          url: canonicalUrl,
          name: 'AutoNovel',
          description:
            'AI 小説執筆プラットフォーム。条件を入れたら、小説が届く。',
          publisher: {
            '@type': 'Organization',
            '@id': `${canonicalUrl}#organization`,
          },
          potentialAction: {
            '@type': 'SearchAction',
            target: `${canonicalUrl}search?q={search_string}`,
            'query-input': 'required name=search_string',
          },
        },
        {
          '@type': 'Organization',
          '@id': `${canonicalUrl}#organization`,
          name: 'HerbMatsui-spec',
          url: 'https://github.com/herbmatsui-spec/autonovel',
          logo: `${canonicalUrl}logo.png`,
        },
      ],
    };

    let scriptEl = document.querySelector('script[type="application/ld+json"]');
    if (!scriptEl) {
      scriptEl = document.createElement('script');
      scriptEl.setAttribute('type', 'application/ld+json');
      document.head.appendChild(scriptEl);
    }
    scriptEl.textContent = JSON.stringify(ldJson);

    // クリーンアップ関数は不要（ページ遷移時に head は維持されるため）
    // 必要に応じて削除ロジックを追加
  }, [title, description, canonicalUrl, ogImage]);

  return null;
};

export default LpHead;