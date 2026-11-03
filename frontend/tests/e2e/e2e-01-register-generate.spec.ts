import { test, expect } from '@playwright/test';

test.describe('E2E-01: 登録→作品作成→第1話生成', () => {
  test('LP から新規登録ページへ遷移し、登録フォームが表示される', async ({ page }) => {
    // 1. LP トップページにアクセス（SPA フォールバック対応のためルートから開始）
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // 2. LP が表示されることを確認
    await expect(page.getByTestId('lp-page')).toBeVisible();

    // 3. プライマリ CTA をクリックして登録ページへ遷移
    await page.getByTestId('lp-hero-cta-primary').click();

    // 3. URL が /register になることを確認
    await expect(page).toHaveURL(/\/register/);

    // 4. 登録フォームが表示されることを確認
    await expect(page.getByTestId('register-page')).toBeVisible();
  });
});
