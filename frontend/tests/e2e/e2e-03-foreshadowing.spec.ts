import { test, expect } from '@playwright/test';

test.describe('E2E-03: 伏線KPI API', () => {
  test('存在しない作品の伏線KPIは404を返す', async ({ request }) => {
    const res = await request.get('/api/graph/foreshadowing/kpi', {
      params: { book_id: '99999' },
    });
    expect(res.status()).toBe(404);
  });
});
