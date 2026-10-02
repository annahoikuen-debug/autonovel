/**
 * D5 の回帰テスト：summary を渡さないときは PUT body から key ごと外す。
 *
 * 以前は常に `summary: payload.summary ?? ""` を送っていたため、
 * summary を持たない呼び出し（Wizard の執筆保存）が
 * サーバー側で保持しているプロット目標を空文字で上書きしていた。
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

const respond = (ok = true, data: unknown = {}) =>
  ({ ok, status: ok ? 200 : 500, json: async () => data }) as unknown as Response;

const sentBody = (callIndex = 0): Record<string, unknown> =>
  JSON.parse(String(mockedApiFetch.mock.calls[callIndex][1]?.body)) as Record<string, unknown>;

beforeEach(() => {
  mockedApiFetch.mockReset();
});

describe("D5: summary が渡されないときは送らない", () => {
  it("summary を渡さないと PUT body に summary key が無い", async () => {
    mockedApiFetch.mockResolvedValue(respond(true));

    await upsertChapter(1, 3, { title: "第3話", content: "本文" });

    const body = sentBody();
    expect(Object.prototype.hasOwnProperty.call(body, "summary")).toBe(false);
    expect(body).toEqual({ title: "第3話", content: "本文", branch_id: 1 });
  });

  it("summary: undefined を渡しても key は無い", async () => {
    mockedApiFetch.mockResolvedValue(respond(true));

    await upsertChapter(1, 3, { title: "第3話", content: "本文", summary: undefined });

    expect(Object.prototype.hasOwnProperty.call(sentBody(), "summary")).toBe(false);
  });

  it("summary を渡したときはそのまま送る（空文字も明示として扱う）", async () => {
    mockedApiFetch.mockResolvedValue(respond(true));

    await upsertChapter(1, 3, { title: "第3話", content: "本文", summary: "プロット目標" });
    expect(sentBody().summary).toBe("プロット目標");

    await upsertChapter(1, 4, { title: "第4話", content: "本文", summary: "" });
    expect(sentBody(1).summary).toBe("");
  });
});

describe("D4: 保存系は失敗を握り潰さない", () => {
  it("ネットワーク断でも例外を投げず false を返す", async () => {
    mockedApiFetch.mockRejectedValue(new Error("ネットワークに接続できません。"));

    await expect(upsertChapter(1, 1, { content: "x" })).resolves.toBe(false);
    await expect(deleteChapter(1, 1)).resolves.toBe(false);
  });

  it("HTTP エラーでも false を返す", async () => {
    mockedApiFetch.mockResolvedValue(respond(false));

    await expect(upsertChapter(1, 1, { content: "x" })).resolves.toBe(false);
    await expect(deleteChapter(1, 1)).resolves.toBe(false);
  });

  it("章一覧の失敗は「読めなかった」として区別できるようにする", async () => {
    mockedApiFetch.mockResolvedValue(respond(false));

    await expect(fetchChapters(1)).rejects.toThrow(/章一覧の取得に失敗/);
  });

  it("章一覧は空でも配列ならそのまま返す", async () => {
    mockedApiFetch.mockResolvedValue(respond(true, []));

    await expect(fetchChapters(1)).resolves.toEqual([]);
  });
});
