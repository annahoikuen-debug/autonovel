/**
 * 回帰テスト: ストリーミング中のサーバーエラー通知（D1 / D2 / D11）。
 *
 * 以前は `data.type === "error"` で投げた Error が同じ catch に捕まり、
 * `err.message.includes("ストリーミング生成エラー")` の場合だけ再送出されていた。
 * サーバーが「LLM timeout」のような別文言を返すと JSON パース失敗として握り潰され、
 * 部分 本文が `onSuccess` で「執筆完了」扱いで保存されていた。
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
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

/** SSE の data 行を順番に返す最小のストリーム reader */
function createFakeStream(lines: string[]) {
  const queue = [...lines];
  const encoder = new TextEncoder();
  const probe = { reads: 0, cancelled: false };

  const reader = {
    read: vi.fn(async (): Promise<ReadResult> => {
      probe.reads += 1;
      const line = queue.shift();
      if (line === undefined) return { done: true };
      return { done: false, value: encoder.encode(`${line}\n`) };
    }),
    cancel: vi.fn(async () => {
      probe.cancelled = true;
    }),
    releaseLock: vi.fn(),
  };

  const response = {
    ok: true,
    status: 200,
    body: { getReader: () => reader },
  } as unknown as Response;

  return { response, probe };
}

const setCurrentChapterText = vi.fn();
const setGenerationState = vi.fn();

/** 直前の setGenerationState updater をモックの state に適用して読む */
function lastGenerationState() {
  const calls = setGenerationState.mock.calls;
  if (calls.length === 0) return null;
  const updater = calls[calls.length - 1][0] as (prev: unknown) => unknown;
  return updater({ isGenerating: true, statusText: "", suggestions: [], currentTaskId: null, error: null });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedContext.mockReturnValue({
    character: { name: "アルト", personality: "熱血", ability: "剣", genre: "ファンタジー" },
    currentChapterText: "ユーザーが書いた既存本文",
    setCurrentChapterText,
    setGenerationState,
    contentLengthLimit: 2000,
    targetEpisodes: 1,
    llmConfig: {},
  } as unknown as ReturnType<typeof useNovelContext>);
});

async function startWith(lines: string[]) {
  const { response, probe } = createFakeStream(lines);
  mockedStream.mockResolvedValue(response);
  const onSuccess = vi.fn();
  const onError = vi.fn();
  const onMessage = vi.fn();
  const { result, unmount } = renderHook(() =>
    useStreamingWriter({ onSuccess, onError, onMessage }),
  );
  await act(async () => {
    await result.current.startStreaming();
  });
  return { result, onSuccess, onError, onMessage, probe, unmount };
}

describe("useStreamingWriter: サーバーエラーの伝播", () => {
  it("type:error のサーバーメッセージを onError で通知する", async () => {
    const { onError, onSuccess, probe } = await startWith([
      'data: {"type":"chunk","text":"書き出しの段落"}',
      'data: {"type":"error","message":"LLM timeout"}',
      'data: {"type":"done"}',
    ]);

    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0][0]).toContain("LLM timeout");
    // 部分出力を成功扱いにしない
    expect(onSuccess).not.toHaveBeenCalled();
    expect(setCurrentChapterText).not.toHaveBeenCalled();
    // エラーで止めたので done 行は読まない
    expect(probe.reads).toBe(2);
    expect(lastGenerationState()).toMatchObject({ isGenerating: false, error: "LLM timeout" });
  });

  it("エラーメッセージを省略した type:error でも既定文言で通知する", async () => {
    const { onError } = await startWith(['data: {"type":"error"}']);

    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0][0]).toContain("ストリーミング生成エラー");
  });

  it("エラー通知は onError 1 系統だけで、❌ を二重に付けない", async () => {
    const { onError, onMessage } = await startWith([
      'data: {"type":"chunk","text":"途中"}',
      'data: {"type":"error","message":"レート制限"}',
    ]);

    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0][0]).not.toContain("❌");
    // GeneratePanel では onError / onMessage が同じトースト追加に流れるため、
    // 両方を呼ぶと「❌ ❌」が 2 枚出る
    expect(onMessage.mock.calls.filter(([m]) => String(m).includes("レート制限"))).toHaveLength(0);
  });

  it("JSON として壊れた行はスキップし、残りのストリームは正常終了する", async () => {
    const { onSuccess, onError } = await startWith([
      "data: {Broken JSON",
      'data: {"type":"chunk","text":"本文"}',
      'data: {"type":"done"}',
    ]);

    expect(onError).not.toHaveBeenCalled();
    expect(onSuccess).toHaveBeenCalledWith("本文");
  });

  it("完了時は本文を「全文差し替え」で 1 回だけ反映する（追記と置換の不一致を防ぐ）", async () => {
    const { onSuccess } = await startWith(['data: {"type":"chunk","text":"生成された本文"}']);

    expect(onSuccess).toHaveBeenCalledWith("生成された本文");
    expect(setCurrentChapterText).toHaveBeenCalledTimes(1);
    // updater 関数（追記）ではなく絶対値で置き換える。
    // GeneratePanel の onSuccess → syncGenerationToEditor は絶対上書きのため、
    // ここで追記すると state の更新順で既存本文が失われる。
    expect(setCurrentChapterText).toHaveBeenCalledWith("生成された本文");
  });
});
