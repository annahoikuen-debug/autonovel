import { useState, useRef, useCallback, useEffect } from "react";
import { generateContentStream } from "../api/easyMode";
import { useNovelContext } from "../context/NovelContext";

interface UseStreamingWriterOptions {
  onSuccess?: (finalText: string) => void;
  onMessage?: (msg: string) => void;
  onError?: (errMsg: string) => void;
  /** 接続エラー時の最大リトライ回数 (デフォルト: 2) */
  maxRetries?: number;
  /** リトライ間隔 (ミリ秒, デフォルト: 1000) */
  retryDelayMs?: number;
}

type TimerId = ReturnType<typeof setTimeout>;

/**
 * サーバーが `{"type":"error"}` として返したエラー。
 *
 * メッセージ文字列での判別はやめる。以前は `err.message.includes("...エラー")` で
 * 送り返しすぎていたため、サーバーが「LLM timeout」「レート制限」のように
 * 別文言を返すと JSON パース失敗とみなされ、ストリームはそのまま正常終了扱いになり、
 * 部分的な本文が「執筆が完了しました」として保存されていた。
 */
export class StreamServerError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "StreamError";
  }
}

/** 追跡対象の setTimeout を発行する（アンマウント時に一括で clear するため） */
function trackTimeout(timers: Set<TimerId>, ms: number): Promise<void> {
  return new Promise((resolve) => {
    const id = setTimeout(() => {
      timers.delete(id);
      resolve();
    }, ms);
    timers.add(id);
  });
}

/** signal が abort されたら即座に解決する（待機中の打ち切り用） */
function waitForAbort(signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.resolve();
  return new Promise((resolve) => {
    signal.addEventListener("abort", () => resolve(), { once: true });
  });
}

/** 一定時間待つ。abort された場合は待たずに打ち切る。 */
function waitWithAbort(timers: Set<TimerId>, ms: number, signal: AbortSignal): Promise<void> {
  return Promise.race([trackTimeout(timers, ms), waitForAbort(signal)]);
}

export function useStreamingWriter(options?: UseStreamingWriterOptions) {
  const {
    character,
    currentChapterText,
    setCurrentChapterText,
    setGenerationState,
    contentLengthLimit,
    targetEpisodes,
    llmConfig,
  } = useNovelContext();
  const [isStreaming, setIsStreaming] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [streamOutput, setStreamOutput] = useState("");
  /** 現在のリトライ回数 (UI 表示用) */
  const [retryCount, setRetryCount] = useState(0);

  const abortControllerRef = useRef<AbortController | null>(null);
  const isPausedRef = useRef(false);
  const accumulatedTextRef = useRef("");
  /** アンマウント済みなら true。以降の setState / コールバックを止める */
  const isMountedRef = useRef(true);
  /** 実行中の setTimeout（ポーズ待機・リトライ待機） */
  const timersRef = useRef<Set<TimerId>>(new Set());

  const maxRetries = options?.maxRetries ?? 2;
  const retryDelayMs = options?.retryDelayMs ?? 1000;

  // アンマウント時はストリームの読み出し・待機タイマー・reader を必ず破棄する。
  // 以前は abort する主体が無く、読み出しループと 150ms 待機がそのまま残り、
  // アンマウント済みコンポーネントへ setState を呼び続けた。
  useEffect(() => {
    isMountedRef.current = true;
    const timers = timersRef.current;
    return () => {
      isMountedRef.current = false;
      abortControllerRef.current?.abort();
      abortControllerRef.current = null;
      timers.forEach((id) => clearTimeout(id));
      timers.clear();
    };
  }, []);

  /** キャンセル / アンマウント時にストリーミング状態を「中断」へ戻す */
  const markStopped = useCallback(
    (statusText: string) => {
      if (!isMountedRef.current) return;
      setIsStreaming(false);
      setIsPaused(false);
      isPausedRef.current = false;
      setGenerationState((prev) => ({
        ...prev,
        isGenerating: false,
        statusText,
      }));
    },
    [setGenerationState],
  );

  const startStreaming = useCallback(
    async (promptOverrideOrStyleKey?: string, styleKeyArg?: string) => {
      // 呼び出しは「プロンプト上書きなし・文体キー指定」の形を基本とする。
      // 第1引数がプロンプトなのか文体キーなのかは、`styleKeyArg` の有無で判別する。
      const styleKey = styleKeyArg ?? (promptOverrideOrStyleKey ? promptOverrideOrStyleKey : undefined);
      const promptOverride = styleKeyArg ? promptOverrideOrStyleKey : undefined;
      setIsStreaming(true);
      setIsPaused(false);
      isPausedRef.current = false;
      setStreamOutput("");
      accumulatedTextRef.current = "";
      setRetryCount(0);

      setGenerationState((prev) => ({
        ...prev,
        isGenerating: true,
        statusText: "リアルタイム執筆中...",
        error: null,
      }));

      const controller = new AbortController();
      abortControllerRef.current = controller;
      const timers = timersRef.current;

      const promptText = promptOverride !== undefined ? promptOverride : currentChapterText;

      // 接続フェーズ: リトライ機構付きでストリーム接続を確立する
      let response: Response | null = null;
      let lastConnectError: Error | null = null;
      for (let attempt = 0; attempt <= maxRetries; attempt++) {
        if (controller.signal.aborted) break;
        try {
          if (attempt > 0) {
            setRetryCount(attempt);
            setGenerationState((prev) => ({
              ...prev,
              isGenerating: true,
              statusText: `接続エラー。再接続中... (${attempt}/${maxRetries})`,
            }));
            options?.onMessage?.(`🔄 接続エラーのため再接続します (${attempt}/${maxRetries})...`);
            await waitWithAbort(timers, retryDelayMs, controller.signal);
            if (controller.signal.aborted) break;
          }
          response = await generateContentStream(
            {
              chapter_history: promptText ? [promptText] : [],
              current_chapter: promptText || "冒険のプロット",
              character_params: character,
              content_length_limit: contentLengthLimit || 2000,
              target_episodes: targetEpisodes || 1,
              // 画面で選んだ文体プリセット（従来は渡せず、選択が反映されなかった）
              ...(styleKey && styleKey !== "auto" ? { style_override: { style_id: styleKey } } : {}),
              ...( (llmConfig && (llmConfig.api_key || llmConfig.provider)) ? { llm_config: llmConfig } : {} ),
            },
            controller.signal
          );
          lastConnectError = null;
          setRetryCount(0);
          break;
        } catch (err: any) {
          // ユーザーキャンセルはリトライしない
          if (controller.signal.aborted) break;
          lastConnectError = err instanceof Error ? err : new Error(err?.message || "不明なエラー");
        }
      }

      if (!isMountedRef.current) return;

      // 接続前にユーザーキャンセルされた場合は「接続エラー」にしない
      if (!response) {
        if (controller.signal.aborted) {
          // cancelStreaming がすでに通知済み。ここで重ねてエラー通知しない。
          markStopped("執筆を中断しました");
          return;
        }
        const message = lastConnectError?.message || "接続に失敗しました";
        setIsStreaming(false);
        setStreamOutput("");
        accumulatedTextRef.current = "";
        setRetryCount(0);
        setGenerationState((prev) => ({
          ...prev,
          isGenerating: false,
          statusText: `接続エラー: ${message}`,
          error: message,
        }));
        // 通知は onError の 1 系統だけにする（GeneratePanel 側が ❌ を付けるため、
        // ここで既に付けたり onMessage にも送ったりすると「❌ ❌」になる）
        options?.onError?.(`接続エラー (${maxRetries + 1}回試行): ${message}`);
        return;
      }

      let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
      try {
        if (!response.body) {
          throw new Error("ストリームレスポンスが取得できませんでした");
        }

        reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
          // ポーズ状態の待機ループ（キャンセル時は待たずに抜ける）
          while (isPausedRef.current && !controller.signal.aborted) {
            await waitWithAbort(timers, 150, controller.signal);
          }
          if (controller.signal.aborted) break;

          const { done, value } = await reader.read();
          if (done) break;
          if (controller.signal.aborted) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || !trimmed.startsWith("data:")) continue;

            const jsonStr = trimmed.replace(/^data:\s*/, "");
            let data: any;
            try {
              data = JSON.parse(jsonStr);
            } catch {
              // 通常のJSONパーススキップ
              continue;
            }
            if (data.type === "chunk" && data.text) {
              accumulatedTextRef.current += data.text;
              setStreamOutput(accumulatedTextRef.current);
            } else if (data.type === "done") {
              // 完了
            } else if (data.type === "error") {
              // サーバーがエラーを返したら生成を中断し、onError へ伝える
              throw new StreamServerError(data.message || "ストリーミング生成エラー");
            }
          }
        }

        // キャンセル / アンマウント後に届いた内容は成功扱いしない
        if (controller.signal.aborted) {
          markStopped("執筆を一時停止・中断しました");
          if (isMountedRef.current) {
            options?.onMessage?.("⏹ 執筆ストリーミングを停止しました。");
          }
          return;
        }
        if (!isMountedRef.current) return;

        const finalText = accumulatedTextRef.current.trim();
        // 本文が空のときに「執筆が完了しました。」を本文として書き込むと、
        // setCurrentChapterText（章节の上書き）によりユーザーの原稿が
        // 状態メッセージで破壊される。空本文はエラーとして扱い既存本文を温存する。
        if (!finalText) {
          throw new Error("生成結果が空でした。既存本文は保持されています。");
        }
        // 完了時の本文反映は「全文差し替え」1 系統に統一する。
        // ここで追記（prev + finalText）しつつ onSuccess 側で絶対上書き
        // （GeneratePanel → syncGenerationToEditor）すると、
        // state の更新順次第でユーザーの既存本文が失われるため。
        setCurrentChapterText(finalText);
        setGenerationState((prev) => ({
          ...prev,
          isGenerating: false,
          statusText: "",
        }));

        setIsStreaming(false);
        options?.onSuccess?.(finalText);
        options?.onMessage?.("✨ リアルタイム執筆が完了しました！");
      } catch (err: any) {
        if (!isMountedRef.current) return;
        if (controller.signal.aborted) {
          // ユーザーキャンセル時
          markStopped("執筆を一時停止・中断しました");
          options?.onMessage?.("⏹ 執筆ストリーミングを停止しました。");
          return;
        }

        // ストリーム読み取り中のエラーはフォールバックせず明示エラーで停止する
        const message = err?.message || "不明なエラー";
        setIsStreaming(false);
        setStreamOutput("");
        accumulatedTextRef.current = "";
        setRetryCount(0);
        setGenerationState((prev) => ({
          ...prev,
          isGenerating: false,
          statusText: `接続エラー: ${message}`,
          error: message,
        }));
        // onError の 1 系統だけで通知する（❌ は呼び出し側が付ける）
        options?.onError?.(`接続エラー: ${message}`);
      } finally {
        // 途中で投げられた場合も読み出しを止め切る
        if (reader) void reader.cancel().catch(() => { /* 既に閉じている場合は無視 */ });
      }
    },
    [
      character,
      currentChapterText,
      setCurrentChapterText,
      setGenerationState,
      options,
      contentLengthLimit,
      targetEpisodes,
      llmConfig,
      maxRetries,
      retryDelayMs,
      markStopped,
    ]
  );

  const pauseStreaming = useCallback(() => {
    isPausedRef.current = true;
    setIsPaused(true);
    options?.onMessage?.("⏸ 執筆を一時停止しました");
  }, [options]);

  const resumeStreaming = useCallback(() => {
    isPausedRef.current = false;
    setIsPaused(false);
    options?.onMessage?.("▶ 執筆を再開しました");
  }, [options]);

  const cancelStreaming = useCallback(() => {
    abortControllerRef.current?.abort();
    // 待機中のタイマー（リトライ / ポーズ）を残さない
    timersRef.current.forEach((id) => clearTimeout(id));
    timersRef.current.clear();
    setIsStreaming(false);
    setIsPaused(false);
    isPausedRef.current = false;
    options?.onMessage?.("⏹ 執筆をキャンセルしました");
  }, [options]);

  return {
    isStreaming,
    isPaused,
    streamOutput,
    retryCount,
    startStreaming,
    pauseStreaming,
    resumeStreaming,
    cancelStreaming,
  };
}
