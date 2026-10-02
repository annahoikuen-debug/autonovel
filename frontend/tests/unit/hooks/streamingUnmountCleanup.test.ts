/**
 * 回帰テスト: useStreamingWriter のアンマウント時クリーンアップ（D4）。
 *
 * 以前は useEffect 自体が無く、abort する主体も無かったため、
 * ストリームの読み出しループ・150ms のポーズ待機・リトライの setTimeout が
 * アンマウント後も動き続け、reader も閉じられていなかった。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useStreamingWriter } from "../../../src/hooks/useStreamingWriter";
import { generateContentStream } from "../../../src/api/easyMode";
import { useNovelContext } from "../../../src/context/NovelContext";

vi.mock("../../../src/api/easyMode", () => ({
  generateContentStream: vi.fn(),
}));

vi.mock("../../../src/context/NovelContext", () => ({
  useNovelContext: vi.fn(),
}));

const mockedStream = vi.mocked(generateContentStream);
const mockedContext = vi.mocked(useNovelContext);

type ReadResult = { done: boolean; value?: Uint8Array };

interface SignalHolder {
  signal: AbortSignal | null;
}

/** テスト側から任意のタイミングで read を解決できるストリーム */
function createControllableStream(holder: SignalHolder) {
  const encoder = new TextEncoder();
  const queue: ReadResult[] = [];
  const probe = { reads: 0, cancelled: false };
  let pending: { resolve: (r: ReadResult) => void; reject: (e: unknown) => void } | null = null;

  const settle = (result: ReadResult) => {
    if (pending) {
      const p = pending;
      pending = null;
      p.resolve(result);
    } else {
      queue.push(result);
    }
  };

  const reader = {
    read: vi.fn((): Promise<ReadResult> => {
      probe.reads += 1;
      const signal = holder.signal;
      if (signal?.aborted) {
        return Promise.reject(new DOMException("The operation was aborted.", "AbortError"));
      }
      if (queue.length > 0) return Promise.resolve(queue.shift() as ReadResult);
      return new Promise<ReadResult>((resolve, reject) => {
        pending = { resolve, reject };
        // 実 fetch / ReadableStream と同じく abort で AbortError を投げる
        signal?.addEventListener(
          "abort",
          () => {
            pending = null;
            reject(new DOMException("The operation was aborted.", "AbortError"));
          },
          { once: true },
        );
      });
    }),
    cancel: vi.fn(async () => {
      probe.cancelled = true;
      pending = null;
    }),
    releaseLock: vi.fn(),
  };

  const response = {
    ok: true,
    status: 200,
    body: { getReader: () => reader },
  } as unknown as Response;

  return {
    response,
    probe,
    push: (line: string) => settle({ done: false, value: encoder.encode(`${line}\n`) }),
  };
}

const setCurrentChapterText = vi.fn();
const setGenerationState = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers();
  mockedContext.mockReturnValue({
    character: { name: "アルト", personality: "熱血", ability: "剣", genre: "ファンタジー" },
    currentChapterText: "既存本文",
    setCurrentChapterText,
    setGenerationState,
    contentLengthLimit: 2000,
    targetEpisodes: 1,
    llmConfig: {},
  } as unknown as ReturnType<typeof useNovelContext>);
});

afterEach(() => {
  vi.useRealTimers();
});

/** act の中でマイクロタスクだけを進める */
async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}

describe("useStreamingWriter: アンマウント時クリーンアップ", () => {
  it("読み出し中のアンマウントで abort し、reader を閉じ、待機タイマーを片付ける", async () => {
    const holder: SignalHolder = { signal: null };
    const stream = createControllableStream(holder);
    mockedStream.mockImplementation(async (_input, signal) => {
      holder.signal = signal ?? null;
      return stream.response;
    });

    const onSuccess = vi.fn();
    const onMessage = vi.fn();
    const onError = vi.fn();
    const { result, unmount } = renderHook(() =>
      useStreamingWriter({ onSuccess, onMessage, onError }),
    );

    const baselineTimers = vi.getTimerCount();
    await act(async () => {
      void result.current.startStreaming();
    });
    expect(stream.probe.reads).toBe(1);

    // 1 チャンク目を送り、読み出しループを 1 周させる
    await act(async () => {
      stream.push('data: {"type":"chunk","text":"書き出し"}');
    });
    expect(stream.probe.reads).toBe(2);

    // ポーズして 150ms の待機タイマーを持たせる
    act(() => {
      result.current.pauseStreaming();
    });
    await act(async () => {
      stream.push('data: {"type":"chunk","text":"続き"}');
    });
    expect(vi.getTimerCount()).toBeGreaterThan(baselineTimers);

    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    unmount();
    // abort で待機が解けるのでマイクロタスクを数段回す
    await flush();
    await flush();

    expect(holder.signal?.aborted).toBe(true);
    expect(stream.probe.cancelled).toBe(true);
    expect(vi.getTimerCount()).toBe(baselineTimers);
    // アンマウント後の通知・保存はしない（部分本文を完了扱いにしない）
    expect(onSuccess).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
    expect(
      consoleError.mock.calls.filter(([m]) => /unmount|state update/i.test(String(m))),
    ).toHaveLength(0);
    consoleError.mockRestore();
  });

  it("再接続待ち（アンマウント時）のリトライタイマーも clear される", async () => {
    const holder: SignalHolder = { signal: null };
    mockedStream.mockImplementation(async (_input, signal) => {
      holder.signal = signal ?? null;
      throw new Error("接続できません");
    });

    const onError = vi.fn();
    const { result, unmount } = renderHook(() =>
      useStreamingWriter({ onError, maxRetries: 2, retryDelayMs: 1000 }),
    );

    const baselineTimers = vi.getTimerCount();
    await act(async () => {
      void result.current.startStreaming();
    });
    // 1 回目の接続が失敗し、1000ms の再接続待ちに入っている
    expect(vi.getTimerCount()).toBeGreaterThan(baselineTimers);

    unmount();
    await flush();

    expect(holder.signal?.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(baselineTimers);
    expect(onError).not.toHaveBeenCalled();
  });
});
