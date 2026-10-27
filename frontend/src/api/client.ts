/**
 * 型安全 API クライアント基盤
 *
 * 提案6: エラーUX改善
 * - AbortController によるタイムアウト（デフォルト 30 秒）
 * - ネットワーク断（fetch 自体の失敗）とHTTPエラーの区別
 * - 401 時の auth_token 除去（ログアウト連携）
 */

export const DEFAULT_API_TIMEOUT_MS = 30_000;

/**
 * アクセストークンの localStorage キー（**単一の情報源**）。
 *
 * 以前は AuthContext が `"token"` に書き、client.ts が `"auth_token"` を読んでいたため
 * ログインしても Authorization ヘッダが 付与 されず全 API が 401 になっていた。
 * client.ts 側に寄せ、ここを定数として両方から参照する。
 */
export const AUTH_TOKEN_STORAGE_KEY = "auth_token";

/** 保存済みトークンを読む。localStorage 自体が使えない環境では null。 */
export function readAuthToken(): string | null {
  try {
    return localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
  } catch {
    // プライベートモード等で localStorage が禁じられている
    return null;
  }
}

/** 保存済みトークンを消す。例外は握る（呼び出し側の@unmount を止めないため）。 */
export function clearAuthToken(): void {
  try {
    localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
  } catch {
    // ignore storage error
  }
}

export class ApiNetworkError extends Error {
  constructor(message = "ネットワークに接続できません。接続を確認してください。") {
    super(message);
    this.name = "ApiNetworkError";
  }
}

export class ApiTimeoutError extends Error {
  constructor(timeoutMs: number) {
    super(`リクエストがタイムアウトしました（${Math.round(timeoutMs / 1000)}秒）。しばらくしてから再試行してください。`);
    this.name = "ApiTimeoutError";
  }
}

/**
 * 呼び出し側の signal と内部タイムアウト用 signal をまとめて 1 つにまとめる。
 *
 * 以前は `options?.signal ?? controller.signal` と二者択一にしていたため、
 * 呼び出し側が signal を渡すと内部タイムアウトの signal が宙吊りになっていた。
 * 結果としてリクエストがハングすると誰も中断できず、ポーリング側の
 * `while (Date.now() < deadline)` も再評価されないまま止まっていた。
 */
function combineSignals(primary: AbortSignal, secondary: AbortSignal): AbortSignal {
  if (typeof AbortSignal.any === "function") {
    return AbortSignal.any([primary, secondary]);
  }
  // jsdom など AbortSignal.any 未実装の環境向けのフォールバック
  const merged = new AbortController();
  const abort = () => merged.abort();
  for (const signal of [primary, secondary]) {
    if (signal.aborted) {
      merged.abort();
      break;
    }
    signal.addEventListener("abort", abort, { once: true });
  }
  return merged.signal;
}

export async function apiFetch(
  endpoint: string,
  options?: RequestInit,
  timeoutMs: number = DEFAULT_API_TIMEOUT_MS
): Promise<Response> {
  const token = readAuthToken();
  const headers = new Headers(options?.headers || {});
  if (!headers.has("Content-Type") && options?.body) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  const isTest = typeof process !== "undefined" && process.env?.NODE_ENV === "test";
  // 呼び出し側の signal を渡された場合も内部タイムアウトを組み合わせる（ハングした
  // リクエストが無期限に待たされ、ポーリングの打ち切りにも到達しないため）。
  const signal = isTest
    ? undefined
    : options?.signal
      ? combineSignals(options.signal, controller.signal)
      : controller.signal;

  let response: Response;
  try {
    response = await fetch(endpoint, {
      ...options,
      headers,
      signal,
    });
  } catch (err: unknown) {
    clearTimeout(timeoutId);
    // AbortError: タイムアウト or 呼び出し側の中断
    if (err instanceof DOMException && err.name === "AbortError") {
      if (options?.signal?.aborted) {
        throw err; // 呼び出し側の意図的な中断はそのまま伝播
      }
      throw new ApiTimeoutError(timeoutMs);
    }
    // fetch 自体の失敗（オフライン・DNS 失敗など）
    throw new ApiNetworkError();
  }
  clearTimeout(timeoutId);

  // 401: 認証切れ → トークンを除去（AuthContext が次回未認証扱いにする）
  if (response.status === 401) {
    clearAuthToken();
  }

  return response;
}

export async function handleResponse<T>(response: Response, errorMessage?: string): Promise<T> {
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const message = errorData.detail || errorData.message || errorData.title || errorMessage || `HTTP ${response.status} ${response.statusText}`;
    const err = new Error(typeof message === "string" ? message : JSON.stringify(message));
    Object.assign(err, errorData);
    throw err;
  }
  return response.json() as Promise<T>;
}
