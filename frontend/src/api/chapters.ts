import { apiFetch } from "./client";

const BASE = "/api/episodes/chapters";

export interface UpsertChapterPayload {
  title?: string;
  content?: string;
  summary?: string;
  branchId?: number;
}

export interface UpsertChapterResult {
  book_id: number;
  branch_id: number;
  ep_num: number;
  saved: boolean;
}

/**
 * 1 話を保存する（無ければ作成 / あれば更新）。
 *
 * Studio の章操作と Wizard の執筆保存の両方がこれを使う。
 * 失敗しても例外を投げず `false` を返すのは、UI 側で
 * 「ローカル更新はできたが保存に失敗した」という状態を表したいため。
 * `apiFetch` はネットワーク断で `ApiNetworkError` を投げるため、
 * ここで必ず捕まえて `false` に落としておく（放置すると unhandled rejection になり、
 * UI には何も伝わらない）。
 *
 * `summary` を渡されなかったときはキーごと送らない。
 * 常に `""` を送ると、サーバー側で保持しているプロット目標を空で上書きしてしまう。
 */
export async function upsertChapter(
  bookId: number,
  epNum: number,
  payload: UpsertChapterPayload,
): Promise<boolean> {
  if (!bookId || !epNum) return false;

  const body: Record<string, unknown> = {
    title: payload.title ?? "",
    content: payload.content ?? "",
    branch_id: payload.branchId ?? 1,
  };
  if (payload.summary !== undefined) {
    body.summary = payload.summary;
  }

  try {
    const res = await apiFetch(`${BASE}/${bookId}/${epNum}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      console.warn(`章の保存に失敗しました (book=${bookId}, ep=${epNum})`, res.status);
      return false;
    }
    return true;
  } catch (err) {
    console.warn(`章の保存に失敗しました (book=${bookId}, ep=${epNum})`, err);
    return false;
  }
}

/** 1 話を削除する（失敗は `false` に落とす。理由は {@link upsertChapter} と同じ） */
export async function deleteChapter(
  bookId: number,
  epNum: number,
  branchId = 1,
): Promise<boolean> {
  if (!bookId || !epNum) return false;

  try {
    const res = await apiFetch(
      `${BASE}/${bookId}/${epNum}?branch_id=${branchId}`,
      { method: "DELETE" },
    );
    return res.ok;
  } catch (err) {
    console.warn(`章の削除に失敗しました (book=${bookId}, ep=${epNum})`, err);
    return false;
  }
}

export interface StoredChapter {
  ep_num: number;
  title: string;
  content: string;
  summary?: string;
}

/**
 * 作品に保存済みの章一覧を取得する。
 *
 * 保存系（upsert / delete）とは違ってここでは失敗を握り潰さない。
 * HTTP エラー・ネットワーク断は例外として呼び出し側へ伝え、
 * 「読めなかった」と「0 件」を区別できるようにしている
 * （読めなかったのに 0 件で上書きすると、本文が消えたように見えてしまう）。
 */
export async function fetchChapters(bookId: number): Promise<StoredChapter[]> {
  if (!bookId) return [];
  const res = await apiFetch(`${BASE}/${bookId}`);
  if (!res.ok) {
    throw new Error(`章一覧の取得に失敗しました (book=${bookId}, status=${res.status})`);
  }
  const data = await res.json();
  return Array.isArray(data) ? (data as StoredChapter[]) : [];
}
