import { useQuery } from '@tanstack/react-query';
import { BranchTreeData } from '../types/branches';
import { fetchBranchTree } from '../api/branches';

export function useBranchTree(bookId: number) {
  // ブランチ更新のリアルタイム通知用 WebSocket は意図的に使用しない。
  //
  // 以前は `/api/branches/{bookId}/ws` に接続していたが、バックエンドに
  // そのルートは存在しない（`src/backend/routers/branches.py` の唯一の WS は
  // play セッション単位の `/api/branches/play/{session_id}/ws` で、
  // `POST /play` で得た session_id が必要）。存在しないエンドポイントへの
  // 接続は毎回ハンドシェイクに失敗してノイズになるだけなので撤去した。
  //
  // マージ後の更新は `useCommitBranchMerge` の onSuccess が
  // `['branchTree', bookId]` を invalidate するため、その経路で担保される。
  return useQuery<BranchTreeData, Error>({
    queryKey: ['branchTree', bookId],
    queryFn: () => fetchBranchTree(bookId),
    // Enable caching and automatic refetching
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes
    refetchOnWindowFocus: false,
  });
}
