import { test, expect } from '@playwright/test';

test.describe('E2E-02: 文体蒸留・音律整形 API', () => {
  test('文体プリセット一覧が取得できる', async ({ request }) => {
    const res = await request.get('/api/styles/presets');
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(Array.isArray(body)).toBeTruthy();
    expect(body.length).toBeGreaterThan(0);
    expect(body[0]).toHaveProperty('id');
    expect(body[0]).toHaveProperty('name');
  });

  test('文体蒸留APIが200を返す', async ({ request }) => {
    const res = await request.post('/api/styles/distill', {
      data: {
        sample_text: '彼は剣を抜いた。空気が凍りついた。',
        name_hint: '黒騎士調',
      },
    });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body).toHaveProperty('success');
  });
});
