/**
 * ブランチ管理 API クライアント (Step 61)
 *
 * ブランチ系ルートは全て `Depends(get_current_user)` を持つため、
 * 裸の fetch では Authorization ヘッダーが無く 401 になる。
 * 必ず `apiFetch`（token 注入 + 401 時の token 除去）を通すこと。
 */
import {
  BranchResponse,
  BranchForkRequest,
  BranchMergeRequest,
  BranchMergeCommitRequest,
  BranchMergeCommitResponse,
  MergePreviewResponse,
  BranchTreeData,
  ChapterDiffResponse,
  BranchPlayRequest,
  BranchPlaySessionResponse,
  BranchPlayStateResponse,
  BranchPlayEndRequest,
  BranchPlayPlaythroughResponse,
} from '../types/branches';
import { apiFetch, handleResponse } from './client';

/**
 * ブランチツリーを取得
 */
export async function fetchBranchTree(bookId: number): Promise<BranchTreeData> {
  const res = await apiFetch(`/api/branches/${bookId}/tree`);
  return handleResponse<BranchTreeData>(res, `Failed to fetch branch tree: ${res.status}`);
}

/**
 * ブランチ一覧を取得
 */
export async function fetchBranches(bookId: number): Promise<BranchResponse[]> {
  const res = await apiFetch(`/api/branches/${bookId}`);
  return handleResponse<BranchResponse[]>(res, `Failed to fetch branches: ${res.status}`);
}

/**
 * ブランチをフォーク（分岐作成）
 */
export async function forkBranch(bookId: number, payload: BranchForkRequest): Promise<BranchResponse> {
  const res = await apiFetch(`/api/branches/${bookId}/fork`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse<BranchResponse>(res, `Fork failed with status ${res.status}`);
}

/**
 * マージプレビューを取得
 */
export async function previewBranchMerge(
  bookId: number,
  payload: BranchMergeRequest
): Promise<MergePreviewResponse> {
  const res = await apiFetch(`/api/branches/${bookId}/merge/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse<MergePreviewResponse>(res, `Merge preview failed with status ${res.status}`);
}

/**
 * マージを確定コミット (Step 61)
 */
export async function commitBranchMerge(
  bookId: number,
  payload: BranchMergeCommitRequest
): Promise<BranchMergeCommitResponse> {
  const res = await apiFetch(`/api/branches/${bookId}/merge/commit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse<BranchMergeCommitResponse>(res, `Merge commit failed with status ${res.status}`);
}

/**
 * 2 ブランチ間の章差分を取得
 *
 * バックエンドのルートは `@router.get("/{book_id}/diff")` なので、
 * bookId はパスパラメータとして渡す必要がある
 * （クエリにすると book_id="diff" として解釈され 422 になる）。
 */
export async function fetchChapterDiff(
  bookId: number,
  branchAId: number,
  branchBId: number,
  chapterNumber: number
): Promise<ChapterDiffResponse> {
  const params = new URLSearchParams({
    branchA: String(branchAId),
    branchB: String(branchBId),
    chapter: String(chapterNumber),
  });
  const res = await apiFetch(`/api/branches/${bookId}/diff?${params.toString()}`);
  return handleResponse<ChapterDiffResponse>(res, `Failed to fetch chapter diff: ${res.status}`);
}

// ============================================================================
// Play モード(IF プレイヤーセッション)
// バックエンド: src/backend/routers/branches.py の /play 系(全て Bearer 必須)
// ============================================================================

/**
 * IF プレイヤーセッションを開始する
 *
 * session_id はバックエンド側で UUID 自動発行される。
 * ブランチが書籍に属さない場合は 404、他人の書籍は 403/404 になる(IDOR 対策済み)。
 */
export async function startPlaySession(payload: BranchPlayRequest): Promise<BranchPlaySessionResponse> {
  const res = await apiFetch('/api/branches/play', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse<BranchPlaySessionResponse>(res, `Failed to start play session: ${res.status}`);
}

/** セッションの現状態(現在ノード / 利用可能な選択肢)を取得 */
export async function fetchPlayState(sessionId: string): Promise<BranchPlayStateResponse> {
  const res = await apiFetch(`/api/branches/play/${sessionId}/state`);
  return handleResponse<BranchPlayStateResponse>(res, `Failed to fetch play state: ${res.status}`);
}

/** 選択肢を実行し、遷移後の状態を返す */
export async function choosePlayChoice(sessionId: string, choiceId: string): Promise<BranchPlayStateResponse> {
  const res = await apiFetch(`/api/branches/play/${sessionId}/choose`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ choice_id: choiceId }),
  });
  return handleResponse<BranchPlayStateResponse>(res, `Failed to choose: ${res.status}`);
}

/** 現状態をセーブポイントに追記保存し、保存後の状態を返す */
export async function savePlayPoint(sessionId: string): Promise<BranchPlayStateResponse> {
  const res = await apiFetch(`/api/branches/play/${sessionId}/save`, { method: 'POST' });
  return handleResponse<BranchPlayStateResponse>(res, `Failed to save play point: ${res.status}`);
}

/** セーブポイント(index)から状態を復元する。範囲外は 400 */
export async function loadPlayPoint(sessionId: string, index: number): Promise<BranchPlayStateResponse> {
  const res = await apiFetch(`/api/branches/play/${sessionId}/load?index=${index}`, { method: 'POST' });
  return handleResponse<BranchPlayStateResponse>(res, `Failed to load play point: ${res.status}`);
}

/** セッションを終了する。デフォルトは status="completed" */
export async function endPlaySession(sessionId: string, payload?: BranchPlayEndRequest): Promise<BranchPlaySessionResponse> {
  const res = await apiFetch(`/api/branches/play/${sessionId}/end`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload ?? {}),
  });
  return handleResponse<BranchPlaySessionResponse>(res, `Failed to end play session: ${res.status}`);
}

/** プレイスルー記録(履歴 + flags / variables)を取得 */
export async function fetchPlaythrough(sessionId: string): Promise<BranchPlayPlaythroughResponse> {
  const res = await apiFetch(`/api/branches/play/${sessionId}/playthrough`);
  return handleResponse<BranchPlayPlaythroughResponse>(res, `Failed to fetch playthrough: ${res.status}`);
}
