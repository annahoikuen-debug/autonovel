/**
 * AutoNovel 商業LP - E2E テスト（Playwright）
 *
 * ファイル: frontend/tests/e2e/lp.spec.ts
 *
 * ブラウザレベルで主要ユーザーフローを自動検証する。
 * 実行: npx playwright test
 */

import { test, expect } from '@playwright/test';

test.describe('LP トップページ', () => {
  test('ヒーローセクションが正しく表示される', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByTestId('lp-hero-headline')).toBeVisible();
    await expect(page.getByTestId('lp-hero-eyebrow')).toBeVisible();
    await expect(page.getByTestId('lp-hero-subhead')).toBeVisible();
    await expect(page.getByTestId('lp-hero-cta-primary')).toBeVisible();
    await expect(page.getByTestId('lp-hero-cta-secondary')).toBeVisible();
  });

  test('プライマリ CTA クリックで登録ページへ遷移する', async ({ page }) => {
    await page.goto('/');

    await page.getByTestId('lp-hero-cta-primary').click();
    await expect(page).toHaveURL(/\/register/);
  });

  test('3 つの入口カードが表示され、各 CTA で対応ページへ遷移する', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByTestId('lp-entry-easy-card')).toBeVisible();
    await expect(page.getByTestId('lp-entry-wizard-card')).toBeVisible();
    await expect(page.getByTestId('lp-entry-studio-card')).toBeVisible();

    // かんたん執筆
    await page.getByTestId('lp-entry-easy-cta').click();
    await expect(page).toHaveURL(/\/welcome/);

    await page.goto('/');

    // 共創ウィザード
    await page.getByTestId('lp-entry-wizard-cta').click();
    await expect(page).toHaveURL(/\/app\/wizard/);

    await page.goto('/');

    // Studio
    await page.getByTestId('lp-entry-studio-cta').click();
    await expect(page).toHaveURL(/\/app\/studio/);
  });

  test('FAQ アコーディオンが開閉する', async ({ page }) => {
    await page.goto('/');

    // FAQ セクションまでスクロール
    await page.getByTestId('lp-faq-section').scrollIntoViewIfNeeded();

    const firstQuestion = page.getByTestId('lp-faq-question-0');
    await firstQuestion.click();

    await expect(page.getByTestId('lp-faq-answer-0')).toBeVisible();

    await firstQuestion.click();
    await expect(page.getByTestId('lp-faq-answer-0')).toBeHidden();
  });

  test('モバイル表示でレイアウト崩れがない', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto('/');

    await expect(page.getByTestId('lp-hero-headline')).toBeVisible();
    await expect(page.getByTestId('lp-header-cta-primary')).toBeVisible();

    // モバイルメニューを開く
    await page.getByTestId('lp-header-mobile-menu').click();
    await expect(page.getByTestId('lp-mobile-nav-register')).toBeVisible();
  });

  test('Tab キーでインタラクティブ要素にフォーカスが移動する', async ({ page }) => {
    await page.goto('/');

    // 最初のフォーカス可能要素に移動
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');

    // フォーカスが可視化されているか（簡易チェック）
    const focused = page.locator(':focus');
    await expect(focused).toBeVisible();
  });
});
