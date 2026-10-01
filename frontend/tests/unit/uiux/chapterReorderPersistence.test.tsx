/**
 * D1 / D7 の回帰テスト：▲▼ と D&D の並び替えがサーバーへ保存されること。
 *
 * 以前は ▲▼ が `setChapters` を呼ぶだけで PUT が発生せず、
 * リロードすると並びが元に戻っていた（DoD「並び替えが保持される」が偽）。
 * また途中の章を削除すると話数が空き、並び替えが黙って無効になっていた。
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, within, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { apiFetch } from "../../../src/api/client";
import {
  makeChapter,
  renderOutlineTree,
  putCalls,
  endpoints,
  okResponse,
} from "./chapterOutlineTreeHarness";

vi.mock("../../../src/api/client", () => ({
  apiFetch: vi.fn(),
}));

const mockedApiFetch = vi.mocked(apiFetch);

beforeEach(() => {
  mockedApiFetch.mockReset();
  // 保存系は成功、章一覧の取得（Hydration）は失敗させて
  // テストが指定した章だけを表示させる
  mockedApiFetch.mockImplementation(async (_endpoint, options) => {
    if (options?.method === "PUT" || options?.method === "DELETE") return okResponse();
    throw new Error("network down");
  });
});

const THREE_CHAPTERS = [
  makeChapter(1, { title: "A" }),
  makeChapter(2, { title: "B" }),
  makeChapter(3, { title: "C" }),
];

const upButtonOf = (epNum: number) =>
  within(screen.getByTestId(`chapter-item-${epNum}`)).getByText("▲");

const downButtonOf = (epNum: number) =>
  within(screen.getByTestId(`chapter-item-${epNum}`)).getByText("▼");

/** 保存された話数 `epNum` のタイトル（空白ゆれは話数改写の仕様なので正規化して読む） */
const savedTitle = (epNum: number) => {
  const call = putCalls(mockedApiFetch).find(
    (c) => c.endpoint === `/api/episodes/chapters/1/${epNum}`,
  );
  return String(call?.body.title ?? "").replace(/\s+/g, " ").trim();
};

describe("D1: ▲▼ の並び替えがサーバーへ保存される", () => {
  it("▲ で上げた章は 1 話目のまま PUT される（話数が入れ替わる）", async () => {
    const user = userEvent.setup();
    renderOutlineTree({ chapters: THREE_CHAPTERS });

    await user.click(upButtonOf(2));

    await waitFor(() => expect(putCalls(mockedApiFetch)).toHaveLength(3));
    // B が 1 話目、A が 2 話目に送られている（= 画面と同じ話数で保存されている）
    expect(savedTitle(1)).toBe("第1話: B");
    expect(savedTitle(2)).toBe("第2話: A");
    expect(savedTitle(3)).toBe("第3話: C");
  });

  it("▼ で下げた章は 3 話目として PUT される", async () => {
    const user = userEvent.setup();
    renderOutlineTree({ chapters: THREE_CHAPTERS });

    await user.click(downButtonOf(2));

    await waitFor(() => expect(putCalls(mockedApiFetch)).toHaveLength(3));
    expect(savedTitle(2)).toBe("第2話: C");
    expect(savedTitle(3)).toBe("第3話: B");
  });

  it("並び替え後も執筆中の章が、そのまま新しい話数へ追従する", async () => {
    const user = userEvent.setup();
    renderOutlineTree({ chapters: THREE_CHAPTERS });

    // 3 話目（= C）を選択してから 1 話目まで上げる
    await user.click(screen.getByTestId("chapter-item-3"));
    expect(screen.getByTestId("chapter-item-3")).toHaveAttribute("aria-current", "true");

    await user.click(upButtonOf(3));
    expect(screen.getByTestId("chapter-item-2")).toHaveTextContent("C");
    expect(screen.getByTestId("chapter-item-2")).toHaveAttribute("aria-current", "true");

    await user.click(upButtonOf(2));
    expect(screen.getByTestId("chapter-item-1")).toHaveTextContent("C");
    expect(screen.getByTestId("chapter-item-1")).toHaveAttribute("aria-current", "true");
    expect(screen.getByTestId("active-chapter-goal")).toHaveTextContent("C");
  });
});

describe("D7: 途中の章を削除しても並び替えが生きている", () => {
  it("削除後は話数が連番になり、残りが新しい話数で保存される", async () => {
    const user = userEvent.setup();
    renderOutlineTree({ chapters: THREE_CHAPTERS });

    await user.click(screen.getByTestId("btn-delete-chapter-2"));

    await waitFor(() =>
      expect(endpoints(mockedApiFetch, "DELETE")).toEqual([
        "/api/episodes/chapters/1/2?branch_id=1",
      ]),
    );
    // 3 話目は存在しない（話数が連番に振り直された）
    expect(screen.queryByTestId("chapter-item-3")).not.toBeInTheDocument();
    expect(screen.getByTestId("chapter-item-2")).toHaveTextContent("第2話: C");
    // 残りの 2 話も新しい話数で保存されている
    await waitFor(() => expect(putCalls(mockedApiFetch)).toHaveLength(2));
    expect(savedTitle(1)).toBe("第1話: A");
    expect(savedTitle(2)).toBe("第2話: C");
  });

  it("削除後の ▲▼ が保存まで行う（話数が空いても黙って無効にならない）", async () => {
    const user = userEvent.setup();
    renderOutlineTree({ chapters: THREE_CHAPTERS });

    await user.click(screen.getByTestId("btn-delete-chapter-2"));
    await waitFor(() => expect(putCalls(mockedApiFetch)).toHaveLength(2));
    mockedApiFetch.mockClear();

    await user.click(upButtonOf(2));

    await waitFor(() => expect(putCalls(mockedApiFetch)).toHaveLength(2));
    expect(savedTitle(1)).toBe("第1話: C");
    expect(savedTitle(2)).toBe("第2話: A");
  });

  it("削除後のドラッグ＆ドロップが実際に並べ替える", async () => {
    renderOutlineTree({ chapters: THREE_CHAPTERS });

    fireEvent.click(screen.getByTestId("btn-delete-chapter-2"));
    await waitFor(() => expect(screen.queryByTestId("chapter-item-3")).not.toBeInTheDocument());
    await waitFor(() => expect(putCalls(mockedApiFetch)).toHaveLength(2));
    mockedApiFetch.mockClear();

    // 現在の 2 話目（= C）を 1 話目へドラッグする
    fireEvent.dragStart(screen.getByTestId("chapter-item-2"));
    fireEvent.drop(screen.getByTestId("chapter-item-1"));

    await waitFor(() => expect(putCalls(mockedApiFetch)).toHaveLength(2));
    expect(savedTitle(1)).toBe("第1話: C");
    expect(savedTitle(2)).toBe("第2話: A");
  });
});
