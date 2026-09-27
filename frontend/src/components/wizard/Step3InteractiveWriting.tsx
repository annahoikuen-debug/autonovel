import React, { useState, useEffect, useRef } from 'react';
import { PlatformCopyButton } from '../common/PlatformCopyButton';
import { StreamingProgressBar } from '../common/StreamingProgressBar';
import { subscribeWritingStreamFetch, WritingStreamEvent } from '../../api/wizard';

interface Step3Props {
  book_id: number;
  ep_num: number;
  branch_id: number;
  chapterTitle: string;
  chapterContent: string;
  isGenerating: boolean;
  onGenerateNext: () => void | Promise<void>;
  onRegenerate: () => void;
  /**
   * SSE から届いた本文を親へ通知する。
   * @param content 受信済みの本文（差分ではなく累積全文）
   * @param done    執筆が完了したか
   */
  onContentChange?: (content: string, done: boolean) => void;
  /**
   * ストリームがエラーになったことを親へ通知する。
   * 親は `isGenerating` を解除してボタンを再度押せるようにする。
   */
  onStreamError?: (message: string) => void;
}

export const Step3InteractiveWriting: React.FC<Step3Props> = ({
  book_id,
  ep_num,
  branch_id,
  chapterTitle,
  chapterContent,
  isGenerating,
  onGenerateNext,
  onRegenerate,
  onContentChange,
  onStreamError,
}) => {
  const [streamProgress, setStreamProgress] = useState(0);
  const [streamPhase, setStreamPhase] = useState<'ContextBuilding' | 'Drafting' | 'Auditing' | 'Complete' | 'Error' | 'Connecting'>('Connecting');
  const [streamStatus, setStreamStatus] = useState<'connecting' | 'connected' | 'receiving' | 'completed' | 'error' | 'disconnected'>('connecting');
  const [streamElapsed, setStreamElapsed] = useState(0);
  const [streamError, setStreamError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  /** SSE から受け取った本文の累積（親 state と二重管理しないためローカルに持つ） */
  const bufferRef = useRef<string>('');
  /**
   * 経過時間計算の基準時刻。
   * バックエンドの `timestamp` は `time.time()` のエポック秒なので、
   * そのままでは「経過時間」として使えない（最初のイベント時刻との差を取る）。
   */
  const streamStartTimeRef = useRef<number | null>(null);

  useEffect(() => {
    // Setup SSE stream subscription with AbortController
    const controller = new AbortController();
    abortControllerRef.current = controller;
    // 话が変わったら本文バッファをリセットする
    bufferRef.current = '';
    streamStartTimeRef.current = null;

    subscribeWritingStreamFetch(
      book_id,
      ep_num,
      branch_id,
      (event: WritingStreamEvent) => {
        setStreamProgress(event.progress);
        setStreamPhase(event.phase);
        setStreamStatus(event.phase === 'Error' ? 'error' :
          event.phase === 'Complete' ? 'completed' :
            event.progress > 0 ? 'receiving' : 'connected');
        // `event.timestamp` はエポック秒。最初のイベントを起点にした経過秒に変換する。
        if (streamStartTimeRef.current === null) {
          streamStartTimeRef.current = event.timestamp;
        }
        setStreamElapsed(Math.max(0, Math.floor(event.timestamp - streamStartTimeRef.current)));
        const errorMessage = event.phase === 'Error' ? event.message || 'Unknown error' : null;
        setStreamError(errorMessage);
        // 親側の isGenerating も解除する（解除しないとオーバーレイが回り続け、
        // ボタンが押せないまま復旧にはリロードが必要になる）
        if (errorMessage !== null) {
          onStreamError?.(errorMessage);
        }

        // 本文を溜める。バックエンドが差分(content)を刻々と送ってくる想定で、
        // phase === 'Complete' のときは全文として確定させる。
        if (typeof event.content === 'string' && event.content.length > 0) {
          if (event.phase === 'Complete') {
            bufferRef.current = event.content;
            onContentChange?.(event.content, true);
          } else {
            bufferRef.current += event.content;
            onContentChange?.(bufferRef.current, false);
          }
        } else if (event.phase === 'Complete') {
          onContentChange?.(bufferRef.current, true);
        }
      },
      controller.signal
    ).catch((err) => {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      console.error('SSE stream error:', err);
      const message = err instanceof Error ? err.message : 'ストリーム接続に失敗しました';
      setStreamStatus('error');
      setStreamError(message);
      // 接続自体が失敗した場合も親の isGenerating を解除する
      onStreamError?.(message);
    });

    // Cleanup on unmount
    return () => {
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [book_id, ep_num, branch_id]);

  const handleRegenerate = () => {
    onRegenerate();
    // Reset stream state
    bufferRef.current = '';
    streamStartTimeRef.current = null;
    setStreamProgress(0);
    setStreamPhase('Connecting');
    setStreamStatus('connecting');
    setStreamElapsed(0);
    setStreamError(null);
  };

  return (
    <div className="wizard-step step3-container p-6 bg-slate-900 text-white rounded-xl shadow-lg">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-2xl font-bold text-amber-400">
          第{ep_num}話: {chapterTitle}
        </h2>
        <PlatformCopyButton title={chapterTitle} body={chapterContent} />
      </div>

      <div className="relative mb-6">
        <textarea
          rows={16}
          readOnly={isGenerating}
          value={chapterContent}
          data-testid="wizard-chapter-textarea"
          className="w-full p-4 rounded bg-slate-950 border border-slate-800 text-slate-100 font-serif leading-relaxed text-base focus:outline-none focus:border-amber-500"
          placeholder={isGenerating ? "AIが本文を執筆中... (約30秒)" : "本文がここに表示されます"}
        />
        {isGenerating && (
          <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-[1px] flex items-center justify-center">
            <span className="text-sky-300 font-semibold animate-pulse">執筆＆二層監査中... ⚡</span>
          </div>
        )}
      </div>

      {/* Streaming Progress Bar */}
      <div className="mb-6">
        <StreamingProgressBar
          progress={streamProgress}
          phaseName={streamPhase}
          elapsedSeconds={streamElapsed}
          connectionStatus={streamStatus}
          onElapsedChange={setStreamElapsed}
        />
        {streamError && (
          <div className="mt-2 p-3 bg-red-900/50 border border-red-700 rounded-lg text-red-200 text-sm">
            エラー: {streamError}
          </div>
        )}
      </div>

      <div className="flex gap-4">
        <button
          onClick={handleRegenerate}
          disabled={isGenerating}
          className="px-6 py-3 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 rounded font-semibold transition-colors"
        >
          リテイク（再執筆）
        </button>
        <button
          onClick={onGenerateNext}
          disabled={isGenerating}
          className="flex-1 py-3 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 rounded font-semibold transition-colors"
        >
          次の一話を執筆する →
        </button>
      </div>
    </div>
  );
};
