import { useCallback, useEffect, useRef } from "react";
import { generateContent, pollGenerationStatus, cancelTask as apiCancelTask } from "../api/easyMode";
import { useNovelContext } from "../context/NovelContext";
import type { GenerationState } from "../types";

type TimerId = ReturnType<typeof setTimeout>;

/**
 * ポーリング間隔（ミリ秒）。
 *
 * 以前は一律 100ms（= 10req/s）で叩いていたため、生成が 1 分続くだけで
 * 600 回リクエストしていた。待ち時間に応じて段階的に広げ、サーバー負荷を下げる。
 */
const POLL_INTERVALS_MS = [100, 300, 1000] as const;

/** 経過回数から次のポーリング間隔を決める */
function nextPollDelay(attempt: number): number {
  const idx = Math.min(attempt, POLL_INTERVALS_MS.length - 1);
  return POLL_INTERVALS_MS[idx];
}

/**
 * バックエンドの内部ステータスをユーザー向け表示へ変換する。
 *
 * 以前は `running` / `queued` などの内部値をそのまま画面に出しており、
 * 非技術者にとって読み人为本が 「これは失敗なのか？」と誤解する原因になっていた。
 */
function humanizeStatus(raw: string): string {
  switch (raw) {
    case "pending":
    case "queued":
      return "リクエストを受け付けています…";
    case "running":
    case "in_progress":
      return "🪄 AIが執筆しています。このままお待ちください…";
    case "completed":
      return "✅ 執筆が完了しました";
    case "failed":
      return "❌ 執筆に失敗しました";
    default:
      return "🪄 執筆を続けています…";
  }
}
/**
 * 生成完了を待つ上限。
 *
 * 以前は 60 秒で打ち切っていたため、長めの原稿（1話 3000字超・監査込み）では
 * 必ず「生成タイムアウト」になり、正常な執筆でも失敗として扱われていた。
 * LLM 執筆は 30〜120 秒程度が現実的なので、余裕を持たせて 5 分にしている
 * （停滞を検出できない代償はユーザーが「中止」ボタンで明示的に止められること）。
 */
const POLL_TIMEOUT_MS = 300_000;

/**
 * 通常執筆のフック。
 *
 * `startGeneration` は **文体プリセット ID を引数に取る**。以前は画面側の
 * ローカル state に留まっていたため「選んだ文体が反映されない」状態だった。
 */
export function useNovelGeneration(
  onSuccess?: (output: string, suggestions: string[]) => void,
  onMessage?: (msg: string) => void,
  onError?: (msg: string) => void
) {
  const {
    character,
    currentChapterText,
    setCurrentChapterText,
    setGenerationState,
    contentLengthLimit,
    targetEpisodes,
    llmConfig,
  } = useNovelContext();
  const isCancelledRef = useRef<boolean>(false);
  const abortRef = useRef<AbortController | null>(null);
  /** アンマウント済みなら true。以降の setState / コールバックを止める */
  const isMountedRef = useRef<boolean>(true);
  /** ポーリング間隔の setTimeout（アンマウント時に clear する） */
  const pollTimerRef = useRef<TimerId | null>(null);

  // アンマウント時はポーリングを止め、進行中のリクエストも中断する。
  // 以前は abort する主体が無く、最大 5 分間のポーリングと未管理の setTimeout が
  // アンマウント後も setState を呼び続けていた。
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      abortRef.current?.abort();
      abortRef.current = null;
      if (pollTimerRef.current !== null) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, []);

  const updateGenerationState = useCallback(
    (updater: (prev: GenerationState) => GenerationState) => {
      if (!isMountedRef.current) return;
      setGenerationState(updater);
    },
    [setGenerationState],
  );

  const startGeneration = useCallback(async (styleKey?: string) => {
    isCancelledRef.current = false;
    abortRef.current = new AbortController();
    const signal = abortRef.current.signal;
    updateGenerationState((prev) => ({
      ...prev,
      isGenerating: true,
      statusText: "生成リクエストを送信中...",
      error: null,
    }));

    try {
      const response = await generateContent({
        chapter_history: [currentChapterText],
        current_chapter: currentChapterText,
        character_params: character,
        content_length_limit: contentLengthLimit || 2000,
        target_episodes: targetEpisodes || 1,
        // 画面で選んだ文体プリセット。従来は SimpleModePanel のローカル state に
        // 留まっており生成に届いていなかった（選んだ設定が効かない）。
        ...(styleKey ? { style_override: { style_id: styleKey } } : {}),
        ...( (llmConfig && (llmConfig.api_key || llmConfig.provider)) ? { llm_config: llmConfig } : {} ),
      });

      // suggestions はバックエンドが省略しうるため既定値を必ず与える
      const taskId =
        response.task_id ||
        (response.suggestions || [])
          .join("\n")
          .match(/(?:ステータスを\s*)?\/easy_mode\/status\/([^\s]+)/)?.[1];

      if (!isMountedRef.current || signal.aborted) return;

      if (taskId) {
        updateGenerationState((prev) => ({
          ...prev,
          currentTaskId: taskId,
          statusText: "🪄 AIが執筆しています。このままお待ちください…",
        }));

        const deadline = Date.now() + POLL_TIMEOUT_MS;
        let attempt = 0;
        while (Date.now() < deadline) {
          if (isCancelledRef.current) {
            // .loop を打ち切るための内部シグナル。catch 側で静かに吸収する
            throw new Error("生成がキャンセルされました");
          }

          const status = await pollGenerationStatus(taskId, signal);
          if (status.status === "completed") {
            const rawResult = status.result;
            const parsed =
              typeof rawResult === "string"
                ? JSON.parse(rawResult || "{}")
                : rawResult || {};

            const out = typeof parsed.output === "string" ? parsed.output.trim() : "";
            const sug = parsed.suggestions || [];

            // 本文が空だった場合に既定の文字列を 本文 に流し込むと、
            // setCurrentChapterText（＝章节の上書き）によってユーザーの本文が
            // 「生成が完了しました。」という状態メッセージで破壊される。
            // 空本文はエラーとして扱い、既存本文を温存する。
            if (!out) {
              throw new Error(
                "生成結果が空でした。既存本文は保持されています。"
              );
            }

            // 単一ソース化: currentChapterText に本文を反映、currentOutput は setter しない
            setCurrentChapterText(out);
            updateGenerationState((prev) => ({
              ...prev,
              isGenerating: false,
              statusText: "",
              suggestions: sug,
              currentTaskId: null,
            }));
            onSuccess?.(out, sug);
            onMessage?.("✨ 本文のAI生成が完了しました。");
            return;
          }

          if (status.status === "failed") {
            throw new Error(status.error || "生成タスクが失敗しました");
          }

          // キャンセル済みの表示（"キャンセルされました"）を上書きしない
          if (!isCancelledRef.current) {
            updateGenerationState((prev) => ({
              ...prev,
              statusText: humanizeStatus(status.status),
            }));
          }

          // ポーリング間隔。ref に残してアンマウント時に clear し、
          // abort された場合は待たずに抜ける（ハング防止）。
          const delay = nextPollDelay(attempt);
          await new Promise<void>((resolve) => {
            if (signal.aborted) {
              resolve();
              return;
            }
            const onAbort = () => {
              clearTimeout(timer);
              pollTimerRef.current = null;
              resolve();
            };
            const timer = setTimeout(() => {
              signal.removeEventListener("abort", onAbort);
              pollTimerRef.current = null;
              resolve();
            }, delay);
            pollTimerRef.current = timer;
            signal.addEventListener("abort", onAbort, { once: true });
          });
          attempt += 1;
        }

        throw new Error("生成タイムアウト（5分を超過しました。時間を置いて再度お試しください）");
      } else {
        // 即時レスポンス
        const out = typeof response.output === "string" ? response.output.trim() : "";
        const sug = response.suggestions || [];

        // ポーリング経路と同じく、空本文はエラーとして扱い既存本文を温存する
        // （既定文言を本文として流すとユーザーの原稿が状態メッセージで壊れる）。
        if (!out) {
          throw new Error("生成結果が空でした。既存本文は保持されています。");
        }

        setCurrentChapterText(out);
        updateGenerationState((prev) => ({
          ...prev,
          isGenerating: false,
          statusText: "",
          suggestions: sug,
          currentTaskId: null,
        }));
        onSuccess?.(out, sug);
        onMessage?.("✨ 本文のAI生成が完了しました。");
      }
    } catch (e: unknown) {
      // ユーザーのキャンセル / アンマウントによる中断はエラーとして扱わない。
      // 以前はここで error を立てて onError も呼ぶため、
      // 意図的なキャンセルに 2 件の エラートーストと role="alert" が出ていた。
      if (isCancelledRef.current || signal.aborted) {
        if (isMountedRef.current) {
          updateGenerationState((prev) => ({
            ...prev,
            isGenerating: false,
            currentTaskId: null,
          }));
        }
        return;
      }
      const msg = e instanceof Error ? e.message : "不明なエラーが発生しました";
      updateGenerationState((prev) => ({
        ...prev,
        isGenerating: false,
        statusText: "",
        error: msg,
        currentTaskId: null,
      }));
      onError?.(`❌ エラー: ${msg}`);
    }
  }, [
    character,
    currentChapterText,
    setCurrentChapterText,
    updateGenerationState,
    onSuccess,
    onMessage,
    onError,
    contentLengthLimit,
    targetEpisodes,
    llmConfig,
  ]);

  const cancelGeneration = useCallback(
    async (taskId: string | null) => {
      isCancelledRef.current = true;
      // 実行中のポーリングも中断する（未 abort だと最大 5 分動き続ける）
      abortRef.current?.abort();
      if (pollTimerRef.current !== null) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
      if (taskId) {
        try {
          await apiCancelTask(taskId);
        } catch {
          // ignore cancel error
        }
      }
      updateGenerationState((prev) => ({
        ...prev,
        isGenerating: false,
        statusText: "キャンセルされました",
        currentTaskId: null,
      }));
      // キャンセルは失敗ではないためエラー系統では通知しない
      onMessage?.("🛑 執筆をキャンセルしました。");
    },
    [updateGenerationState, onMessage]
  );

  return { startGeneration, cancelGeneration };
}
