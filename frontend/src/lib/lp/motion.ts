/**
 * AutoNovel 商業LP - Framer Motion モーションプリセット
 *
 * ファイル: frontend/src/lib/lp/motion.ts
 *
 * 使用前: `npm install framer-motion` が必要。
 * 既存アプリとの整合性のため、過剰なアニメーションは避け、
 * prefers-reduced-motion に対応する。
 */

import { Variants } from 'framer-motion';

/**
 * 要素が下からゆっくり浮かび上がる（ファーストビュー・セクション導入用）
 */
export const fadeInUp: Variants = {
  hidden: { opacity: 0, y: 24 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, ease: 'easeOut' },
  },
};

/**
 * シンプルなフェードイン
 */
export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { duration: 0.5, ease: 'easeInOut' },
  },
};

/**
 * 子要素を順次表示するコンテナ用（stagger）
 */
export const staggerContainer: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.1, delayChildren: 0.1 },
  },
};

/**
 * ホバー時に微拡大・タップ時に縮小（ボタン・カード用）
 */
export const hoverScale = {
  whileHover: { scale: 1.02 },
  whileTap: { scale: 0.98 },
};

/**
 * ホバー時に微浮上＋シャドウ増強（カード用）
 */
export const hoverLift = {
  whileHover: { y: -4, boxShadow: '0 20px 25px -5px rgb(0 0 0 / 0.1)' },
  whileTap: { y: 0, scale: 0.98 },
};

/**
 * 減動設定時はすべてのアニメーションを無効化
 */
export const reducedMotion = {
  hidden: { opacity: 1 },
  visible: { opacity: 1, transition: { duration: 0 } },
};

/**
 * ページ遷移用フェード
 */
export const pageTransition = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
  transition: { duration: 0.3 },
};

/**
 * スクロール連動アニメーション用（Intersection Observer 相当）
 * whileInView でビューポート進入時に1回だけ発火
 */
export const inViewFadeUp = {
  initial: { opacity: 0, y: 24 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true },
  transition: { duration: 0.6, ease: 'easeOut' },
};
