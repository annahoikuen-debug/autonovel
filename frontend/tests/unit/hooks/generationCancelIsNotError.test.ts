/**
 * 回帰テスト: キャンセルはエラーではない（D5 / D6）と即時応答の空本文保護（D7 / D8）。
 *
 * 以前は `cancelGeneration` が onError を呼び、ポーリングループも
 * 「生成がキャンセルされました」を throw して同じ catch で error として扱っていた。
 * その結果、意図的なキャンセルでもエラートーストが 2 件出るうえ、
 * role="alert" のエラーボックスが残り続けた。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createElement, useEffect } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { useNovelGeneration } from "../../../src/hooks/useNovelGeneration";
import { generateContent, pollGenerationStatus, cancelTask } from "../../../src/api/easyMode";
import { NovelProvider } from "../../../src/context/NovelContext";
import { useNovelContext } from "../../../src/context/NovelContext";
import GeneratePanel from "../../../src/components/GeneratePanel";
import type { GenerationState } from "../../../src/types";

vi.mock("../../../src/api/easyMode", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../src/api/easyMode")>();
  return {
    ...actual,
    generateContent: vi.fn(),
    pollGenerationStatus: vi.fn(),
    cancelTask: vi.fn(),
  };
});

const mockedGenerate = vi.mocked(generateContent);
const mockedPoll = vi.mocked(pollGenerationStatus);
const mockedCancel = vi.mocked(cancelTask);

let hookApi: {
  startGeneration: (styleKey?: string) => Promise<void>;
  cancelGeneration: (taskId: string | null) => Promise<void>;
} | null = null;
let lastState: GenerationState | null = null;

function Harness(props: {
  onSuccess?: (out: string, sug: string[]) => void;
  onMessage?: (m: string) => void;
  onError?: (m: string) => void;
}) {
  const api = useNovelGeneration(props.onSuccess, props.onMessage, props.onError);
  const { generationState } = useNovelContext();
  hookApi = api;
  lastState = generationState;
  useEffect(() => {
    hookApi = api;
    lastState = generationState;
  }, [api, generationState]);
  return null;
}

function renderHarness(props: Parameters<typeof Harness>[0]) {
  return render(
    createElement(NovelProvider, null, createElement(Harness, props)),
  );
}

describe("useNovelGeneration: キャンセルはエラーとして扱わない", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    // NovelProvider の初期化（作品一覧取得）がネットワークに依存しないよう差し替える
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("[]", { status: 200, headers: { "content-type": "application/json" } })),
    );
    mockedCancel.mockResolvedValue({ task_id: "task-1", status: "cancelled" });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
    cleanup();
  });

  it("ポーリング中にキャンセルしても onError を呼ばず、error も立てない", async () => {
    const onSuccess = vi.fn();
    const onMessage = vi.fn();
    const onError = vi.fn();
    mockedGenerate.mockResolvedValue({ task_id: "task-1", output: "", suggestions: [] });

    const pollSignals: Array<AbortSignal | null | undefined> = [];
    let pollCount = 0;
    let releasePoll: (() => void) | null = null;
    mockedPoll.mockImplementation((_taskId, signal) => {
      pollSignals.push(signal);
      pollCount += 1;
      if (pollCount === 1) {
        return Promise.resolve({ task_id: "task-1", status: "running" as const });
      }
      // 2 回目以降は保留。テストが任意のタイミングで解決させる
      return new Promise((resolve) => {
        releasePoll = () => resolve({ task_id: "task-1", status: "running" as const });
      });
    });

    renderHarness({ onSuccess, onMessage, onError });
    await act(async () => {
      void hookApi!.startGeneration();
    });
    // 1 回目の応答（running）→ 100ms 待機 → 2 回目を保留状態で待つ
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });
    expect(pollCount).toBe(2);

    await act(async () => {
      await hookApi!.cancelGeneration("task-1");
    });

    // 実行中のポーリングは abort される（最長 5 分動き続けるため）
    expect(pollSignals[1]?.aborted).toBe(true);

    // 保留していたポーリングを解決させてループの打ち切りを再現する
    act(() => {
      releasePoll?.();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(onError).not.toHaveBeenCalled();
    expect(
      onMessage.mock.calls.filter(([m]) => String(m).includes("エラー")),
    ).toHaveLength(0);
    expect(onSuccess).not.toHaveBeenCalled();
    expect(lastState?.error).toBeNull();
    expect(lastState?.isGenerating).toBe(false);
    expect(lastState?.statusText).toBe("キャンセルされました");
  });

  it("suggestions を省略された応答でも例外にせず即時応答として扱う", async () => {
    const onSuccess = vi.fn();
    const onError = vi.fn();
    // バックエンドが suggestions を省略するケース（task_id なし）
    mockedGenerate.mockResolvedValue({ output: "即時本文" } as never);

    renderHarness({ onSuccess, onError });
    await act(async () => {
      await hookApi!.startGeneration();
    });

    expect(onError).not.toHaveBeenCalled();
    expect(onSuccess).toHaveBeenCalledWith("即時本文", []);
  });

  it("suggestions から task_id を抽出できる", async () => {
    const onSuccess = vi.fn();
    const onError = vi.fn();
    mockedGenerate.mockResolvedValue({
      output: "",
      suggestions: ["ステータスを /easy_mode/status/task-9 で確認してください"],
    } as never);
    mockedPoll.mockResolvedValue({
      task_id: "task-9",
      status: "completed",
      result: { output: "ポーリング本文" },
    });

    renderHarness({ onSuccess, onError });
    await act(async () => {
      await hookApi!.startGeneration();
    });

    expect(onError).not.toHaveBeenCalled();
    expect(mockedPoll).toHaveBeenCalledWith("task-9", expect.anything());
    expect(onSuccess).toHaveBeenCalledWith("ポーリング本文", []);
  });

  it("即時応答の本文が空なら既存の原稿を残し、エラーとして報告する", async () => {
    const onSuccess = vi.fn();
    const onError = vi.fn();
    mockedGenerate.mockResolvedValue({ output: "   ", suggestions: [] });

    renderHarness({ onSuccess, onError });
    await act(async () => {
      await hookApi!.startGeneration();
    });

    // 状態メッセージが本文として書き込まれることがない
    expect(onSuccess).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0][0]).toContain("生成結果が空でした");
  });
});

const server = setupServer(
  http.get("/api/books", () => HttpResponse.json([])),
  http.get("/api/styles/presets", () => HttpResponse.json([])),
  http.post("/easy_mode/generate", () =>
    HttpResponse.json({ task_id: "task-cancel-1", output: "", suggestions: [] }),
  ),
  http.get("/easy_mode/status/:taskId", () =>
    HttpResponse.json({ task_id: "task-cancel-1", status: "running" }),
  ),
  http.delete("/easy_mode/task/:taskId", () =>
    HttpResponse.json({ task_id: "task-cancel-1", status: "cancelled" }),
  ),
);

describe("GeneratePanel: 中止ボタンでエラーバナーが出ない", () => {
  beforeAll(() => server.listen({ onUnhandledRequest: "warn" }));

  beforeEach(async () => {
    // 直前のフック用モックが残っているので、実装（msw 経由）へ戻す
    const actual = await vi.importActual<typeof import("../../../src/api/easyMode")>(
      "../../../src/api/easyMode",
    );
    mockedGenerate.mockReset().mockImplementation(actual.generateContent);
    mockedPoll.mockReset().mockImplementation(actual.pollGenerationStatus);
    mockedCancel.mockReset().mockImplementation(actual.cancelTask);
  });

  afterAll(() => server.close());
  afterEach(() => {
    server.resetHandlers();
    cleanup();
  });

  it("生成中に中止しても role=alert のエラー表示が出ない", async () => {
    const onMessage = vi.fn();
    const onGenerated = vi.fn();
    render(
      createElement(
        NovelProvider,
        null,
        createElement(GeneratePanel, { onGenerated, onMessage }),
      ),
    );

    fireEvent.click(screen.getByTestId("btn-easy-generate"));
    const cancelButton = await screen.findByText("⏹ 中止", undefined, { timeout: 3000 });
    fireEvent.click(cancelButton);

    // ポーリングループが 1 周して「キャンセル」例外を処理するのを待つ
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 500));
    });

    expect(screen.queryByTestId("generation-error")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(
      onMessage.mock.calls.filter(([m]) => String(m).includes("エラー")),
    ).toHaveLength(0);
    expect(onGenerated).not.toHaveBeenCalled();
  });
});
