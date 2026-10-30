/**
 * AutoNovel 商業LP - Playwright 設定
 *
 * ファイル: frontend/playwright.config.ts
 *
 * E2E テストとビジュアルリグレッションテストの設定。
 * 実行: npx playwright test
 */

import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? 'github' : 'list',

  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    viewport: { width: 1280, height: 800 },
  },

  projects: [
    {
      name: 'chromium',
      use: devices['Desktop Chrome'],
    },
    {
      name: 'firefox',
      use: devices['Desktop Firefox'],
    },
    {
      name: 'webkit',
      use: devices['Desktop Safari'],
    },
    {
      name: 'mobile-chrome',
      use: devices['Pixel 5'],
    },
    {
      name: 'mobile-safari',
      use: devices['iPhone 12'],
    },
  ],

  webServer: {
    command: 'npm run preview --port 3000',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 120 * 1000,
  },
});
