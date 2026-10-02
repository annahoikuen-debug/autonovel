/**
 * S1 / S6 の回帰テスト。
 *
 * - 「かんたん執筆に戻る」ボタンが実際に `/` へ遷移すること
 * - NovelContext に旧 `mode` / wizard state が戻っていないこと
 * - Studio に旧 6 ステップウィザードのオーバーレイが出ていないこと
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import { StudioWorkspace } from "../../../src/components/studio/StudioWorkspace";
import { NovelProvider, useNovelContext } from "../../../src/context/NovelContext";

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

/** 現在のパスを表示するだけの小さな観測役 */
function PathProbe() {
  const location = useLocation();
  return <div data-testid="current-path">{location.pathname}</div>;
}

describe("S1/S6: 入口導線は必ず画面を変える", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.confirm = vi.fn().mockReturnValue(true);
  });

  it("Studio の「かんたん執筆に戻る」で URL が / へ変わる", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={["/studio"]}>
        <NovelProvider>
          <Routes>
            <Route path="/studio" element={<StudioWorkspace />} />
            <Route path="/" element={<div data-testid="easy-mode">かんたん執筆</div>} />
          </Routes>
          <PathProbe />
        </NovelProvider>
      </MemoryRouter>,
    );

    expect(screen.getByTestId("current-path")).toHaveTextContent("/studio");

    await user.click(screen.getByTestId("btn-switch-to-easy-mode"));

    expect(screen.getByTestId("current-path")).toHaveTextContent("/");
    expect(screen.getByTestId("easy-mode")).toBeInTheDocument();
  });

  it("旧 6 ステップウィザードのオーバーレイは Studio に含まれない", () => {
    render(
      <MemoryRouter initialEntries={["/studio"]}>
        <NovelProvider>
          <StudioWorkspace />
        </NovelProvider>
      </MemoryRouter>,
    );

    // 旧ウィザードの見出し（コンセプト設定 / プロット構築 など）が無いこと
    expect(screen.queryByText("コンセプト設定")).not.toBeInTheDocument();
    expect(screen.queryByText("プロット構築")).not.toBeInTheDocument();
    expect(screen.queryByText("AI診断と品質チェック")).not.toBeInTheDocument();
  });
});

describe("S6: NovelContext に旧モード state が無いこと", () => {
  it("コンテキスト型に mode / wizardStep / isWizardActive が存在しない", () => {
    // 実行時チェック（型レベルの保証は tsc が担保，这里はFqn の残存_curve を検出する）
    let ctx: Record<string, unknown> | null = null;
    function Probe() {
      ctx = useNovelContext() as unknown as Record<string, unknown>;
      return null;
    }
    render(
      <NovelProvider>
        <Probe />
      </NovelProvider>,
    );

    expect(ctx).not.toBeNull();
    expect(Object.prototype.hasOwnProperty.call(ctx!, "mode")).toBe(false);
    expect(Object.prototype.hasOwnProperty.call(ctx!, "setMode")).toBe(false);
    expect(Object.prototype.hasOwnProperty.call(ctx!, "wizardStep")).toBe(false);
    expect(Object.prototype.hasOwnProperty.call(ctx!, "isWizardActive")).toBe(false);
    expect(Object.prototype.hasOwnProperty.call(ctx!, "hasCompletedWizard")).toBe(false);
  });
});
