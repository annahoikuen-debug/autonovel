import { test, expect } from '@playwright/test';

const EMAIL = `e2e-branch-${Date.now()}@example.com`;
const PASSWORD = 'password12345';
const DISPLAY_NAME = 'E2E Branch User';

test.describe('E2E-04: 分岐 fork→merge→再生', () => {
  test('ユーザー登録・ログイン → 作品作成 → フォーク → マージ(404) → ノード確認の全フロー', async ({ request }) => {
    // 1. ユーザー登録
    const regRes = await request.post('/api/auth/register', {
      data: { email: EMAIL, password: PASSWORD, display_name: DISPLAY_NAME },
    });
    expect(regRes.ok()).toBeTruthy();

    // 2. ログインしてアクセストークン取得
    const loginRes = await request.post('/api/auth/login', {
      data: { email: EMAIL, password: PASSWORD },
    });
    expect(loginRes.ok()).toBeTruthy();
    const tokenBody = await loginRes.json();
    const accessToken = tokenBody.access_token;
    expect(accessToken).toBeTruthy();

    // 3. 作品作成
    const bookRes = await request.post('/api/books', {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: { title: 'E2E 分岐テスト作品', genre: 'ファンタジー' },
    });
    expect(bookRes.ok()).toBeTruthy();
    const bookBody = await bookRes.json();
    const bookId = bookBody.id;
    expect(bookId).toBeGreaterThan(0);

    // 4. フォーク（分岐）作成
    const forkRes = await request.post(`/api/branches/${bookId}/fork`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: { name: 'E2E フォークブランチ', fork_ep_num: 1 },
    });
    expect(forkRes.ok()).toBeTruthy();
    const forkBody = await forkRes.json();
    const forkBranchId = forkBody.id;
    expect(forkBranchId).toBeGreaterThan(0);

    // 5. マージ（存在しない target に対して 404 を期待 - ネガティブテスト）
    const mergeRes = await request.post(`/api/branches/${bookId}/merge`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: {
        source_branch_id: forkBranchId,
        target_branch_id: 99999,
        merge_ep_num: 1,
        name: 'E2E マージ結果',
      },
    });
    expect(mergeRes.status()).toBe(404);

    // 6. ノード一覧（グラフ未作成時は 404 を期待 - フォーク直後の状態）
    const nodesRes = await request.get(`/api/branches/${bookId}/nodes`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      params: { branch_id: String(forkBranchId) },
    });
    // フォーク直後のブランチにはグラフがまだ作成されていないため 404 が返る
    expect(nodesRes.status()).toBe(404);
  });
});
