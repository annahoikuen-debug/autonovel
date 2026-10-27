import { useQuery } from '@tanstack/react-query';
import { ChapterDiffResponse } from '@/types/branches';
import { fetchChapterDiff } from '@/api/branches';

export function useChapterDiff(bookId: number, branchAId: number, branchBId: number, chapterNumber: number) {
  return useQuery<ChapterDiffResponse, Error>({
    queryKey: ['chapterDiff', bookId, branchAId, branchBId, chapterNumber],
    queryFn: () => fetchChapterDiff(bookId, branchAId, branchBId, chapterNumber),
    enabled: !!bookId && !!branchAId && !!branchBId && !!chapterNumber,
  });
}
