/**
 * R2/R3 の回帰テスト：章データが実際にサーバーへ永続化されること。
 *
 * 以前は章の追加/削除/並び替えと Wizard の執筆内容が
 * クライアント state（と localStorage のみ）に残り、
 * ブラウザを閉じると消えていた。ここでは API 呼び出しを固定する。
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  upsertChapter,
  deleteChapter,
  fetchChapters,
} from "../../../src/api/chapters";
import { apiFetch } from "../../../src/api/client";

vi.mock("../../../src/api/client", () => ({
  apiFetch: vi.fn(),
}));

const mockedApiFetch = vi.mocked(apiFetch);

function respond(ok = true, data: unknown = {}) {
  return { ok, json: async () => data, status: ok ? 200 : 500 } as unknown as Response;
}

beforeEach(() => {
  mockedApiFetch.mockReset();
});

describe("R2/R3: 章の永続化 API", () => {
  it("1 話を PUT で保存する", async () => {
    mockedApiFetch.mockResolvedValue(respond(true, { saved: true }));

    await expect(upsertChapter(1, 3, { title: "第3話", content: "本文" })).resolves.toBe(true);

    expect(mockedApiFetch).toHaveBeenCalledWith("/api/episodes/chapters/1/3", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: "第3話",
        content: "本文",
        summary: "",
        branch_id: 1,
      }),
    });
  });

  it("保存に失敗しても例外を投げず false を返す", async () => {
    mockedApiFetch.mockResolvedValue(respond(false));

    await expect(upsertChapter(1, 1, { content: "x" })).resolves.toBe(false);
  });

  it("bookId / epNum が無効なら通信しない", async () => {
    await expect(upsertChapter(0, 1, {})).resolves.toBe(false);
    await expect(upsertChapter(1, 0, {})).resolves.toBe(false);
    expect(mockedApiFetch).not.toHaveBeenCalled();
  });

  it("削除は DELETE で送る", async () => {
    mockedApiFetch.mockResolvedValue(respond(true));

    await expect(deleteChapter(1, 2)).resolves.toBe(true);
    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/api/episodes/chapters/1/2?branch_id=1",
      { method: "DELETE" },
    );
  });

  it("章一覧は配列でないレスポンスを安全に空にする", async () => {
    mockedApiFetch.mockResolvedValue(respond(true, { unexpected: true }));

    await expect(fetchChapters(1)).resolves.toEqual([]);
  });

  it("章一覧をそのまま返す", async () => {
    const rows = [{ ep_num: 1, title: "第1話", content: "本文" }];
    mockedApiFetch.mockResolvedValue(respond(true, rows));

    await expect(fetchChapters(1)).resolves.toEqual(rows);
  });
});
