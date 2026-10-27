/**
 * ストリーム接続用トークンの取得。
 *
 * ブラウザの `EventSource` と `WebSocket` はカスタム Authorization ヘッダーを
 * 付けられないため、クエリパラメータで認証情報を渡す必要がある。ここで
 * 取得するトークンは **60秒で失効し、対象作品のみにスコープされた**
 * ストリーム専用JWTであり、長時間有効な access トークンではない。
 *
 * access トークンをクエリに載せる形をやめた理由:
 * nginx のアクセスログ、ブラウザ履歴、CDN/リバースプロキシのログに
 * そのまま平文で残り、漏れた場合は stream トークンの有効期間 (60秒) ではなく
 * access トークンの有効期間 (既定60分) の間、API全体にアクセスできてしまう。
 */
import { apiFetch, handleResponse } from "./client";

export interface StreamTokenResponse {
  token: string;
  expires_in: number;
  book_id: number;
}

/**
 * 指定作品のみを購読できる短命トークンを取得する。
 *
 * @throws 認証失敗または作品へのアクセス権がない場合は API が 401/403 を返す
 */
export async function fetchStreamToken(bookId: number): Promise<string> {
  const res = await apiFetch(`/api/stream/token/${bookId}`, {
    method: "POST",
  });
  const data = await handleResponse<StreamTokenResponse>(
    res,
    "Failed to obtain stream token",
  );
  return data.token;
}

/**
 * EventSource 用の URL を組み立てる。
 * トークンが取得できなかった場合は `null` を返し、呼び出し側で
 * 「未認証のまま接続しない」判断ができるようにする。
 */
export async function buildStreamUrl(
  path: string,
  bookId: number,
  extraParams: Record<string, string | number> = {},
): Promise<string | null> {
  let token: string;
  try {
    token = await fetchStreamToken(bookId);
  } catch {
    return null;
  }

  const params = new URLSearchParams({ ...Object.fromEntries(
    Object.entries(extraParams).map(([k, v]) => [k, String(v)]),
  ), token });
  return `${path}?${params.toString()}`;
}
