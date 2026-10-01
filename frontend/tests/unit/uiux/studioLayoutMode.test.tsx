/**
 * S2 の回帰テスト：「執筆重視（split）」レイアウトが実際に画面を変えること。
 *
 * 以前は切替ボタンだけが存在し、押してもレイアウトが一切変わらない
 * デッド UI だった。ここでは「押したら左右ペインが消える／戻ると復活する」を固定する。
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { StudioWorkspace } from "../../../src/components/studio/StudioWorkspace";
import { NovelProvider } from "../../../src/context/NovelContext";

vi.mock("../../../src/api/editor", () => ({
  askBible: vi.fn().mockResolvedValue({ answer: "a", evidence_nodes: [] }),
  auditConsistency: vi.fn().mockResolvedValue({ has_issues: false, issues: [] }),
  assistContent: vi.fn().mockResolvedValue({ result_text: "x", diff_summary: "" }),
  generateNextBeats: vi.fn().mockResolvedValue({ beats: [] }),
  runHybridAudit: vi.fn().mockResolvedValue({
    final_score: 80,
    qualitative: { overall_score: 80, critique: "" },
    quantitative_score: 80,
    conflicts: [],
  }),
}));

vi.mock("../../../src/api/client", () => ({
  apiFetch: vi.fn().mockResolvedValue({ ok: false, status: 404 }),
  handleResponse: vi.fn(),
}));

function renderStudio() {
  return render(
    <MemoryRouter initialEntries={["/studio"]}>
      <NovelProvider>
        <StudioWorkspace />
      </NovelProvider>
    </MemoryRouter>,
  );
}

describe("S2: レイアウト切替が実際のレイアウトを変える", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("完全Studioでは左右ペインが両方出る", () => {
    renderStudio();

    expect(screen.getByTestId("btn-toggle-left-pane")).toBeInTheDocument();
    expect(screen.getByTestId("btn-toggle-right-pane")).toBeInTheDocument();
    // 左右ペインがある = 3列（ペイン / メイン / ペイン）
    const grid = screen.getByTestId("studio-workspace");
    expect(grid.className).not.toContain("studio-grid--collapsed");
    expect((grid as HTMLElement).style.gridTemplateColumns.split(" ").length).toBe(3);
  });

  it("「執筆重視」を押すと左右ペインが消えてエディタが全幅になる", async () => {
    const user = userEvent.setup();
    renderStudio();

    await user.click(screen.getByTestId("btn-layout-split"));

    expect(screen.queryByTestId("btn-toggle-left-pane")).not.toBeInTheDocument();
    expect(screen.queryByTestId("btn-toggle-right-pane")).not.toBeInTheDocument();
    // エディタは表示されたまま
    expect(screen.getByTestId("editor-textarea")).toBeInTheDocument();
    // 全幅（列定義が 1fr のみ）になる
    const grid = screen.getByTestId("studio-workspace") as HTMLElement;
    expect(grid.className).toContain("studio-grid--collapsed-both");
    expect(grid.style.gridTemplateColumns).toBe("1fr");
  });

  it("「完全Studio」へ戻すと左右ペインが復活する", async () => {
    const user = userEvent.setup();
    renderStudio();

    await user.click(screen.getByTestId("btn-layout-split"));
    await user.click(screen.getByTestId("btn-layout-studio"));

    expect(screen.getByTestId("btn-toggle-left-pane")).toBeInTheDocument();
    expect(screen.getByTestId("btn-toggle-right-pane")).toBeInTheDocument();
  });

  it("「集中Zen」は別の専用画面になる", async () => {
    const user = userEvent.setup();
    renderStudio();

    await user.click(screen.getByTestId("btn-layout-zen"));

    expect(screen.getByTestId("zen-editor-textarea")).toBeInTheDocument();
  });

  it("選択したレイアウトが localStorage に保存される", async () => {
    const user = userEvent.setup();
    renderStudio();

    await user.click(screen.getByTestId("btn-layout-split"));

    expect(window.localStorage.getItem("autonovel.layoutMode")).toBe("split");
  });
});
