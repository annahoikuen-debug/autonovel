/**
 * 回帰テスト: apiFetch のタイムアウト（D3）。
 *
 * 以前は `options?.signal ?? controller.signal` と二者択一にしていたため、
 * 呼び出し側が signal を渡すと内部タイムアウトの signal が宙吊りになっていた。
 * ハングしたリクエストは永久に解決されず、`while (Date.now() < deadline)` の
 * ポーリングも再評価されない（「5分」タイムアウトに到達しない）状態になっていた。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiFetch, ApiTimeoutError } from "../../../src/api/client";

/** 応答しない fetch。渡された signal が abort されたら AbortError で落ちる */
function stubHangingFetch() {
  const fetchMock = vi.fn(
    (_input: RequestInfo | URL, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        const signal = init?.signal;
        if (!signal) return;
        const onAbort = () =>
          reject(new DOMException("The operation was aborted.", "AbortError"));
        if (signal.aborted) {
          onAbort();
          return;
        }
        signal.addEventListener("abort", onAbort, { once: true });
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  vi.useFakeTimers();
  // テスト環境（NODE_ENV=test）では signal を渡さない既存仕様を通したいので、
  // 本番と同じ経路を検証するため NODE_ENV を差し替える
  vi.stubEnv("NODE_ENV", "production");
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("apiFetch: 内部タイムアウト", () => {
  it("呼び出し側が自分の signal を渡していても内部タイムアウトで中断する", async () => {
    const fetchMock = stubHangingFetch();
    const caller = new AbortController();
    let outcome: string | null = null;

    const pending = apiFetch("/api/hang", { signal: caller.signal }, 5_000).then(
      () => {
        outcome = "resolved";
      },
      (err: unknown) => {
        outcome = err instanceof ApiTimeoutError ? "timeout" : `other:${(err as Error).name}`;
      },
    );

    await vi.advanceTimersByTimeAsync(5_000);
    await pending;

    expect(fetchMock).toHaveBeenCalledTimes(1);
    // 呼び出し側の signal は abort されていないが、内部タイムアウトで打ち切られる
    expect(caller.signal.aborted).toBe(false);
    expect(outcome).toBe("timeout");
  });

  it("呼び出し側が abort した場合は AbortError のまま伝播する", async () => {
    stubHangingFetch();
    const caller = new AbortController();
    let outcome: string | null = null;

    const pending = apiFetch("/api/hang", { signal: caller.signal }, 30_000).then(
      () => {
        outcome = "resolved";
      },
      (err: unknown) => {
        outcome = err instanceof ApiTimeoutError ? "timeout" : `other:${(err as Error).name}`;
      },
    );

    caller.abort();
    await vi.advanceTimersByTimeAsync(0);
    await pending;

    // タイムアウト扱い（ApiTimeoutError）に化けない
    expect(outcome).toBe("other:AbortError");
  });

  it("呼び出し側が signal を渡さない場合も従来どおりタイムアウトする", async () => {
    stubHangingFetch();
    let outcome: string | null = null;

    const pending = apiFetch("/api/hang", undefined, 1_000).then(
      () => {
        outcome = "resolved";
      },
      (err: unknown) => {
        outcome = err instanceof ApiTimeoutError ? "timeout" : `other:${(err as Error).name}`;
      },
    );

    await vi.advanceTimersByTimeAsync(1_000);
    await pending;

    expect(outcome).toBe("timeout");
  });

  it("テスト環境（NODE_ENV=test）では従来どおり signal を渡さない", async () => {
    vi.stubEnv("NODE_ENV", "test");
    const fetchMock = stubHangingFetch();
    let settled = false;

    const pending = apiFetch("/api/hang", { signal: new AbortController().signal }, 1_000).then(
      () => {
        settled = true;
      },
      () => {
        settled = true;
      },
    );

    await vi.advanceTimersByTimeAsync(10_000);

    const passedSignal = (fetchMock.mock.calls[0][1] as RequestInit | undefined)?.signal;
    expect(passedSignal).toBeUndefined();
    // テスト環境ではタイムアウトもしない（従来どおり保留のまま）
    expect(settled).toBe(false);
    void pending;
  });
});
