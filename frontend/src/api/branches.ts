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
