/**
 * D6 の回帰テスト：未知の / 未設定の chapter status で Studio が落ちない。
 *
 * `StoredChapter` には `status` が無いため、サーバから読んだ章は
 * `chapterStatusMap[undefined]` になり `.color` 読みで TypeError していた。
 * また `statusOrder.indexOf(未知の値)` は -1 で、ステータスが draft へ戻っていた。
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { apiFetch } from "../../../src/api/client";
import { ChapterItem } from "../../../src/types";
import { makeChapter, renderOutlineTree } from "./chapterOutlineTreeHarness";

vi.mock("../../../src/api/client", () => ({
  apiFetch: vi.fn(),
}));

const mockedApiFetch = vi.mocked(apiFetch);

beforeEach(() => {
  mockedApiFetch.mockReset();
  // オフライン（Hydration は失敗＝テスト側の章だけが表示される）
  mockedApiFetch.mockRejectedValue(new Error("ネットワークに接続できません。"));
});

describe("D6: 未知のステータスを描画しても落ちない", () => {
  it("status が未知の値でも描画できる（draft として扱う）", () => {
    expect(() =>
      renderOutlineTree({
        chapters: [
          makeChapter(1, { title: "Unknown", status: "archived" as ChapterItem["status"] }),
          makeChapter(2, { title: "NoStatus", status: undefined }),
        ],
      }),
    ).not.toThrow();

    expect(screen.getByText("Unknown")).toBeInTheDocument();
    expect(screen.getByLabelText("第1話の状態: プロット構想")).toBeInTheDocument();
    expect(screen.getByLabelText("第2話の状態: プロット構想")).toBeInTheDocument();
  });

  it("status が無くても一覧と操作可能なボタンが描画される", () => {
    renderOutlineTree({
      chapters: [
        makeChapter(1, { title: "NoStatus", status: undefined }),
        makeChapter(2, { title: "NoStatus2", status: undefined }),
      ],
    });

    expect(screen.getByText(/章・プロット一覧 \(2話\)/)).toBeInTheDocument();
    expect(screen.getByTestId("btn-move-up-1")).toBeDisabled();
    expect(screen.getByTestId("btn-move-down-1")).toBeEnabled();
    expect(screen.getByTestId("btn-move-up-2")).toBeEnabled();
    expect(screen.getByTestId("btn-move-down-2")).toBeDisabled();
  });

  it("未知のステータスもクリックで次のステータスへ進む（draft へ戻さない）", async () => {
    const user = userEvent.setup();
    renderOutlineTree({
      chapters: [makeChapter(1, { title: "Unknown", status: "archived" as ChapterItem["status"] })],
    });

    expect(screen.getByLabelText("第1話の状態: プロット構想")).toBeInTheDocument();

    await user.click(screen.getByLabelText("第1話の状態: プロット構想"));

    // 前の実装は indexOf が -1 なので、何度押しても draft のままだった
    expect(screen.getByLabelText("第1話の状態: 執筆中")).toBeInTheDocument();
  });

  it("既知のステータスは従来どおり巡回する", async () => {
    const user = userEvent.setup();
    renderOutlineTree({ chapters: [makeChapter(1, { title: "Draft", status: "draft" })] });

    await user.click(screen.getByLabelText("第1話の状態: プロット構想"));
    expect(screen.getByLabelText("第1話の状態: 執筆中")).toBeInTheDocument();
    await user.click(screen.getByLabelText("第1話の状態: 執筆中"));
    expect(screen.getByLabelText("第1話の状態: 初稿脱稿")).toBeInTheDocument();
  });
});

describe("D8: 章の行と操作ボタンがキーボードで扱える", () => {
  it("章の行が button ロールを持ち、Enter / Space で選択できる", async () => {
    const user = userEvent.setup();
    renderOutlineTree({
      chapters: [makeChapter(1, { title: "A" }), makeChapter(2, { title: "B" })],
    });

    const second = screen.getByTestId("chapter-item-2");
    expect(second).toHaveAttribute("role", "button");
    expect(second).toHaveAttribute("tabindex", "0");
    expect(screen.getByTestId("chapter-item-1")).toHaveAttribute("aria-current", "true");

    second.focus();
    await user.keyboard("{Enter}");
    expect(second).toHaveAttribute("aria-current", "true");

    await user.keyboard(" ");
    expect(second).toHaveAttribute("aria-current", "true");
  });

  it("▲▼ と入力欄には読み上げ用のラベルがある", async () => {
    const user = userEvent.setup();
    renderOutlineTree({
      chapters: [makeChapter(1, { title: "A" }), makeChapter(2, { title: "B" })],
    });

    expect(screen.getByLabelText("第2話を上へ移動")).toBeInTheDocument();
    expect(screen.getByLabelText("第2話を下へ移動")).toBeInTheDocument();

    await user.click(screen.getByTestId("btn-edit-title-2"));
    expect(screen.getByLabelText("第2話のタイトル")).toBe(
      screen.getByTestId("input-edit-chapter-title"),
    );
  });
});
