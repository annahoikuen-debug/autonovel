import { useState, useCallback, useRef, useEffect } from "react";
import { generateContentStream } from "../api/easyMode";
import { generateOrchestrated, getOrchestratedStatus, subscribeToAgentEvents } from "../api/orchestratedApi";
import { StreamServerError } from "./useStreamingWriter";
import type { EasyModeInput } from "../types/easyMode";
import type { OrchestratedGenerateRequest, AgentEvent, AgentName } from "../types/orchestrated";
import type { UnifiedStreamingState, GenerationMode, GenerationState } from "../types";
import { useNovelContext } from "../context/NovelContext";

type TimerId = ReturnType<typeof setTimeout>;

/** SSE 1 フレームの処理結果：完了フレームを読み終えたら done */
type FrameOutcome = "continue" | "done";

export function useUnifiedStreaming() {
  const {
    character,
    currentChapterText,
    setCurrentChapterText,
    setGenerationState,
    contentLengthLimit,
    targetEpisodes,
    llmConfig,
  } = useNovelContext();
  const [state, setState] = useState<UnifiedStreamingState>({
    mode: "easy",
    isActive: false,
    output: "",
    agentProgress: {} as any,
    error: undefined,
  });
  const abortRef = useRef<AbortController | null>(null);
  const esRef = useRef<EventSource | null>(null);
  /** アンマウント済みなら true。以降の setState を止める */
  const isMountedRef = useRef(true);
  /** 実行中の setTimeout（オーケストレーションのポーリング待機） */
  const timersRef = useRef<Set<TimerId>>(new Set());

  // アンマウント時は EventSource を閉じ、abort し、待機タイマーを片付ける。
  // 以前は cleanup が無く、離脱後のポーリングループが setState し続けていた。
  useEffect(() => {
    isMountedRef.current = true;
    const timers = timersRef.current;
    return () => {
      isMountedRef.current = false;
      abortRef.current?.abort();
      abortRef.current = null;
      esRef.current?.close();
      esRef.current = null;
      timers.forEach((id) => clearTimeout(id));
      timers.clear();
    };
  }, []);

  /** 追跡対象の setTimeout を発行する（アンマウント時に一括 clear） */
  const sleep = useCallback((ms: number) => {
    return new Promise<void>((resolve) => {
      const id = setTimeout(() => {
        timersRef.current.delete(id);
        resolve();
      }, ms);
      timersRef.current.add(id);
    });
  }, []);

  const start = useCallback(async (mode: GenerationMode, input?: OrchestratedGenerateRequest) => {
    abortRef.current = new AbortController();
    esRef.current?.close();

    setState((s: UnifiedStreamingState) => ({ ...s, mode, isActive: true, output: "", agentProgress: {} as any, error: undefined }));
    setGenerationState(p => ({ ...p, isGenerating: true, statusText: mode === "easy" ? "リアルタイム執筆中..." : "オーケストレーション開始...", error: null }));

    try {
      if (mode === "easy") {
        const response = await generateContentStream(
          { chapter_history: [currentChapterText], current_chapter: currentChapterText, character_params: character, content_length_limit: contentLengthLimit || 2000, target_episodes: targetEpisodes || 1, llm_config: llmConfig },
          abortRef.current.signal
        );
        const reader = response.body!.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        // 1 つのフレームを処理する。
        // JSON パース失敗（不完全なフレーム等）はスキップし、
        // サーバーエラーはメッセージ文字列で判別せず型で捕捉して必ず再送出する。
        const handleFrame = (frame: string): FrameOutcome => {
          const line = frame.trim();
          if (!line.startsWith("data:")) return "continue";
          let data: { type?: string; text?: string; message?: string } | null = null;
          try {
            data = JSON.parse(line.replace(/^data:\s*/, ""));
          } catch {
            // 通常の JSON パース失敗はスキップ
            return "continue";
          }
          if (!data) return "continue";
          if (data.type === "chunk" && data.text) {
            setState((s: UnifiedStreamingState) => ({ ...s, output: s.output + data.text }));
            return "continue";
          }
          if (data.type === "error") {
            // サーバーが送ってきた実際の例外文言（レート制限・LLM timeout 等）を
            // そのまま投げ直す。文字列包含で判定すると取りこぼして握り潰していた。
            throw new StreamServerError(data.message || "ストリーミング生成エラー");
          }
          // "start" は本文に影響しないため何もしない。
          // "done" のみ読み出しループを止める合図として扱う。
          if (data.type === "done") return "done";
          return "continue";
        };

        let finished = false;
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            // バックエンドの SSE は `data: {json}\n\n` 形式でフレームを区切る。
            // バッファを未処理のまま再ループすると既読行を何度でも再処理して
            // 本文が N 重に複製されるため、最後の未完フレームは保持して差し戻す。
            const frames = buffer.split("\n\n");
            buffer = frames.pop() || "";
            for (const frame of frames) {
              if (handleFrame(frame) === "done") {
                finished = true;
                break;
              }
            }
            if (finished) break;
          }

          // 終端に改行が付かない最後のフレームはバッファに残ったまま捨てられる。
          // ループ終了後に読み残しを必ず処理する（最終チャンクの取りこぼし防止）。
          if (!finished && buffer.trim()) {
            handleFrame(buffer);
          }
        } finally {
          void reader.cancel().catch(() => { /* 既に閉じている場合は無視 */ });
        }

        if (!isMountedRef.current) return;
        setState((s: UnifiedStreamingState) => ({ ...s, isActive: false }));
        setGenerationState((p: GenerationState) => ({ ...p, isGenerating: false, statusText: "" }));
      } else {
        const { task_id } = await generateOrchestrated(input!);
        esRef.current = subscribeToAgentEvents(input!.correlation_id || `book_${input!.book_id}_branch_${input!.branch_id}_ep_${input!.ep_num}`, (event) => {
          setState((s: UnifiedStreamingState) => ({ ...s, agentProgress: { ...s.agentProgress, [event.agent]: { status: event.payload?.status, payload: event.payload } } }));
        });
        // ポーリングで完了待ち
        const deadline = Date.now() + 300_000; // 5分タイムアウト
        while (Date.now() < deadline) {
          if (!isMountedRef.current) return;
          if (abortRef.current?.signal.aborted) throw new Error("キャンセルされました");
          const status = await getOrchestratedStatus(task_id, abortRef.current.signal);

          if (status.status === "completed") {
            const result = status.result;
            if (result?.output) {
              setCurrentChapterText(result.output);
              setState((s: UnifiedStreamingState) => ({ ...s, output: result.output }));
              setGenerationState((p: GenerationState) => ({ ...p, isGenerating: false, statusText: "", error: null }));
            }
            setState((s: UnifiedStreamingState) => ({ ...s, isActive: false }));
            setGenerationState((p: GenerationState) => ({ ...p, isGenerating: false, statusText: "" }));
            esRef.current?.close();
            esRef.current = null;
            return;
          }
          if (status.status === "failed") {
            esRef.current?.close();
            esRef.current = null;
            throw new Error(status.error || "生成失敗");
          }

          await sleep(500);
        }
        throw new Error("タイムアウト");
      }
    } catch (e: any) {
      if (e.name !== "AbortError" && isMountedRef.current) {
        setState((s: UnifiedStreamingState) => ({ ...s, isActive: false, error: e.message }));
        setGenerationState((p: GenerationState) => ({ ...p, isGenerating: false, error: e.message }));
      }
    }
  },
  [
    character,
    currentChapterText,
    setCurrentChapterText,
    setGenerationState,
    contentLengthLimit,
    targetEpisodes,
    llmConfig,
    sleep,
  ]
);

   const cancel = useCallback(() => {
    abortRef.current?.abort();
    esRef.current?.close();
    esRef.current = null;
    timersRef.current.forEach((id) => clearTimeout(id));
    timersRef.current.clear();
    setState((s: UnifiedStreamingState) => ({ ...s, isActive: false }));
  }, []);

  return { ...state, start, cancel, setMode: (m: GenerationMode) => setState((s: UnifiedStreamingState) => ({ ...s, mode: m })) };
}