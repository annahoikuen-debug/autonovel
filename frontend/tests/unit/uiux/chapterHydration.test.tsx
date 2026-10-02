/**
 * D2 の回帰テスト：サーバに保存済みの章一覧が読み込まれ、画面へ反映されること。
 *
 * 以前は `fetchChapters` の呼び出しが 0 箇所で、章一覧はハードコードされた 1 話のまま。
 * そのためリロードすると追加/削除/並び替えがすべて消えていた。
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { apiFetch } from "../../../src/api/client";
import { renderOutlineTree, endpoints, okResponse } from "./chapterOutlineTreeHarness";

vi.mock("../../../src/api/client", () => ({
  apiFetch: vi.fn(),
}));

const mockedApiFetch = vi.mocked(apiFetch);

const STORED_CHAPTERS = [
  { ep_num: 1, title: "Saved One", content: "保存済みの本文です", summary: "要約1" },
  { ep_num: 2, title: "Saved Two", content: "", summary: "要約2" },
  { ep_num: 3, title: "Saved Three", content: "三話目の本文", summary: "要約3" },
];

const BOOK = {
  id: 1,
  title: "作品",
  genre: "ファンタジー",
  concept: "",
  synopsis: "",
  target_eps: 10,
  created_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  mockedApiFetch.mockReset();
  mockedApiFetch.mockImplementation(async (endpoint) => {
    if (String(endpoint) === "/api/books/1") return okResponse(BOOK);
    if (String(endpoint) === "/api/episodes/chapters/1") return okResponse(STORED_CHAPTERS);
    return okResponse({});
  });
});

describe("D2: サーバの章一覧を読み込んで描画する", () => {
  it("マウント時に章一覧 API が呼ばれる", async () => {
    renderOutlineTree();

    await waitFor(() =>
      expect(endpoints(mockedApiFetch)).toContain("/api/episodes/chapters/1"),
    );
  });

  it("保存済みの章が一覧として描画される（初期値の 1 話は消える）", async () => {
    renderOutlineTree();

    await waitFor(() =>
      expect(screen.getByText("Saved One")).toBeInTheDocument(),
    );
    expect(screen.getByText("Saved Two")).toBeInTheDocument();
    expect(screen.getByText("Saved Three")).toBeInTheDocument();
    // NovelContext の初期値（デモの 1 話）は消える
    expect(screen.queryByText("第1話 運命の覚醒")).not.toBeInTheDocument();
    expect(screen.getByText(/章・プロット一覧 \(3話\)/)).toBeInTheDocument();
  });

  it("本文の有無からステータスを導出して描画できる", async () => {
    renderOutlineTree();

    await waitFor(() =>
      expect(screen.getByText("Saved One")).toBeInTheDocument(),
    );
    // 本文がある章は「執筆中」
    expect(screen.getByLabelText("第1話の状態: 執筆中")).toBeInTheDocument();
    // 本文が空の章は「プロット構想」
    expect(screen.getByLabelText("第2話の状態: プロット構想")).toBeInTheDocument();
    expect(screen.getByLabelText("第3話の状態: 執筆中")).toBeInTheDocument();
  });

  it("編集中の章カードも保存済みのタイトルになる", async () => {
    renderOutlineTree();

    await waitFor(() =>
      expect(screen.getByText("Saved One")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("active-chapter-goal")).toHaveTextContent("Saved One");
    expect(screen.getByTestId("btn-edit-title-1")).toBeInTheDocument();
  });
});
