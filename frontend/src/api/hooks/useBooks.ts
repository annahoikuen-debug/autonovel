import { useQuery } from "@tanstack/react-query";
import { apiFetch, handleResponse } from "../client";
import type { BookItem } from "../../types";

// /api/books のレスポンスは作品リスト。
// 生成物 (api.generated) は openapi-typescript 由来の flat 型で `paths` を
// 持たないため、同一エンドポイントを型付けしている src/api/books.ts と同じ
// BookItem[] を利用する。
type BooksResponse = BookItem[];

export function useBooks() {
  return useQuery<BooksResponse>({
    queryKey: ["books"],
    queryFn: async () => {
      const res = await apiFetch("/api/books");
      return handleResponse<BooksResponse>(res, "Failed to fetch books");
    },
  });
}
