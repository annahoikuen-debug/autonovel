import { useState, useEffect } from 'react';
import { apiFetch } from '../api/client';

export interface AgentThoughtStep {
  phase: string;
  step_name: string;
  detail_thought: string;
  progress_percent: number;
  timestamp: number;
}

interface UseGenerationProgressOptions {
  taskId?: string;
  onComplete?: () => void;
}

export function useGenerationProgress({ taskId, onComplete }: UseGenerationProgressOptions) {
  const [currentThought, setCurrentThought] = useState<AgentThoughtStep | null>(null);
  const [history, setHistory] = useState<AgentThoughtStep[]>([]);
  const [displayProgress, setDisplayProgress] = useState<number>(0);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);

  // 進捗率の滑らかな補間アニメーション
  useEffect(() => {
    if (!currentThought) return;
    const target = currentThought.progress_percent;
    if (displayProgress === target) return;

    const timer = setInterval(() => {
      setDisplayProgress((prev) => {
        if (prev < target) {
          const next = prev + 2;
          return next > target ? target : next;
        } else if (prev > target) {
          const next = prev - 2;
          return next < target ? target : next;
        }
        return prev;
      });
    }, 20);

    return () => clearInterval(timer);
  }, [currentThought?.progress_percent, displayProgress]);

  // SSE 購読
  //
  // 以前は `new EventSource('/api/tasks/{id}/stream')` を使っていたが、EventSource は
  // Authorization ヘッダーを付けられず、素の URL は必ず 401 になっていた
  // （バックエンドは `Depends(get_current_user)` 必須）。
  // このパスは `/api/stream/` 配下ではないため、クエリトークンを載せる
  // buildStreamUrl() 経路（auth_middleware の STREAM_PATH_PREFIX）も通らない。
  // したがって **fetch + ReadableStream** に置き換える（ヘッダーを付けられるため）。
  useEffect(() => {
    if (!taskId) return;

    const controller = new AbortController();
    let disposed = false;

    setIsGenerating(true);

    const applyStep = (step: AgentThoughtStep) => {
      if (disposed) return;
      setCurrentThought(step);
      setHistory((prev) => [...prev, step]);
      if (step.progress_percent >= 100) {
        setIsGenerating(false);
        onComplete?.();
      }
    };

    const run = async () => {
      try {
        const res = await apiFetch(`/api/tasks/${taskId}/stream`, { signal: controller.signal });
        if (!res.ok) throw new Error(`SSE connection failed: ${res.status}`);
        const reader = res.body?.getReader();
        if (!reader) throw new Error('Response body is not readable');

        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            const frames = buffer.split('\n\n');
            buffer = frames.pop() || '';

            for (const frame of frames) {
              // バックエンドは `event: progress\ndata: {...}` 形式で送る
              const dataLine = frame
                .split('\n')
                .find((line) => line.startsWith('data:'));
              if (!dataLine) continue;
              try {
                applyStep(JSON.parse(dataLine.replace(/^data:\s*/, '')) as AgentThoughtStep);
              } catch (err) {
                console.error('Failed to parse progress event:', err);
              }
            }
          }
        } finally {
          void reader.cancel().catch(() => { /* 既に閉じている場合は無視 */ });
        }
      } catch (err) {
        if (disposed || (err instanceof DOMException && err.name === 'AbortError')) return;
        console.error('Progress stream failed:', err);
        if (!disposed) setIsGenerating(false);
      }
    };

    void run();

    return () => {
      disposed = true;
      controller.abort();
    };
  }, [taskId, onComplete]);

  return {
    currentThought,
    history,
    displayProgress,
    isGenerating,
  };
}
