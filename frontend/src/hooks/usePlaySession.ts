/**
 * Play モード(IF プレイヤーセッション)の状態管理フック
 *
 * Phase 0(docs/implementation_plans/playable_novel_phase0.md)の S03/S04。
 * グラフ型プレイ(事前生成グラフ上の選択)に限定する。動的継続生成は Phase 1。
 *
 * 状態遷移:
 *   idle → starting → playing ⇄ (choose / save / load) → ending → ended
 *   reset() で常に idle へ戻る。
 *
 * react-query を使わない理由: セッションは単一の逐次フロー(ポーリング・
 * キャッシュ・再検証の対象にならない)であり、冪等なクエリモデルより
 * 明示的な状態機械のほうが誤用が少ない。branches 一覧の取得はページ側の
 * useQuery に任せる。
 */
import { useCallback, useState } from 'react';
import {
  BranchPlaySessionResponse,
  BranchPlayStateResponse,
  BranchPlayPlaythroughResponse,
} from '../types/branches';
import {
  startPlaySession,
  fetchPlayState,
  choosePlayChoice,
  savePlayPoint,
  loadPlayPoint,
  endPlaySession,
  fetchPlaythrough,
} from '../api/branches';

/** セッションのフェーズ */
export type PlaySessionPhase = 'idle' | 'starting' | 'playing' | 'ending' | 'ended';

function toMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

export interface UsePlaySessionResult {
  phase: PlaySessionPhase;
  /** 開始済みセッション(ended 後も終了情報として保持) */
  session: BranchPlaySessionResponse | null;
  /** 現状態(playing 中のみ非 null を期待) */
  state: BranchPlayStateResponse | null;
  /** プレイスルー記録(loadHistory() 成功時に設定) */
  playthrough: BranchPlayPlaythroughResponse | null;
  /** いずれかの API 操作中 */
  busy: boolean;
  /** 直近のエラー(表示用。次の操作成功時にクリア) */
  error: string | null;
  /** セッションを開始する */
  start: (bookId: number, branchId: number) => Promise<void>;
  /** 現状態を再取得する */
  refresh: () => Promise<void>;
  /** 選択肢を実行する */
  choose: (choiceId: string) => Promise<void>;
  /** 現状態をセーブする */
  save: () => Promise<void>;
  /** 指定 index のセーブポイントから復元する */
  load: (index: number) => Promise<void>;
  /** セッションを終了する */
  end: () => Promise<void>;
  /** プレイスルー記録を取得する */
  loadHistory: () => Promise<void>;
  /** idle へ戻す(新しいプレイを始める) */
  reset: () => void;
}

export function usePlaySession(): UsePlaySessionResult {
  const [phase, setPhase] = useState<PlaySessionPhase>('idle');
  const [session, setSession] = useState<BranchPlaySessionResponse | null>(null);
  const [state, setState] = useState<BranchPlayStateResponse | null>(null);
  const [playthrough, setPlaythrough] = useState<BranchPlayPlaythroughResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = useCallback(async (bookId: number, branchId: number) => {
    setBusy(true);
    setError(null);
    setPhase('starting');
    try {
      const created = await startPlaySession({ book_id: bookId, branch_id: branchId });
      setSession(created);
      const next = await fetchPlayState(created.session_id);
      setState(next);
      setPlaythrough(null);
      setPhase('playing');
    } catch (err) {
      setError(toMessage(err));
      setPhase('idle');
    } finally {
      setBusy(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      setState(await fetchPlayState(session.session_id));
    } catch (err) {
      setError(toMessage(err));
    } finally {
      setBusy(false);
    }
  }, [session]);

  const choose = useCallback(
    async (choiceId: string) => {
      if (!session) return;
      setBusy(true);
      setError(null);
      try {
        setState(await choosePlayChoice(session.session_id, choiceId));
      } catch (err) {
        setError(toMessage(err));
      } finally {
        setBusy(false);
      }
    },
    [session]
  );

  const save = useCallback(async () => {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      setState(await savePlayPoint(session.session_id));
    } catch (err) {
      setError(toMessage(err));
    } finally {
      setBusy(false);
    }
  }, [session]);

  const load = useCallback(
    async (index: number) => {
      if (!session) return;
      setBusy(true);
      setError(null);
      try {
        setState(await loadPlayPoint(session.session_id, index));
      } catch (err) {
        setError(toMessage(err));
      } finally {
        setBusy(false);
      }
    },
    [session]
  );

  const end = useCallback(async () => {
    if (!session) return;
    setBusy(true);
    setError(null);
    setPhase('ending');
    try {
      const ended = await endPlaySession(session.session_id);
      setSession(ended);
      setPhase('ended');
    } catch (err) {
      setError(toMessage(err));
      setPhase('playing');
    } finally {
      setBusy(false);
    }
  }, [session]);

  const loadHistory = useCallback(async () => {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      setPlaythrough(await fetchPlaythrough(session.session_id));
    } catch (err) {
      setError(toMessage(err));
    } finally {
      setBusy(false);
    }
  }, [session]);

  const reset = useCallback(() => {
    setPhase('idle');
    setSession(null);
    setState(null);
    setPlaythrough(null);
    setError(null);
  }, []);

  return {
    phase,
    session,
    state,
    playthrough,
    busy,
    error,
    start,
    refresh,
    choose,
    save,
    load,
    end,
    loadHistory,
    reset,
  };
}
