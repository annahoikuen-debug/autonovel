/**
 * S8 の回帰テスト：生成の進捗とエラーが画面上で可視化されること。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import { render, screen, cleanup } from "@testing-library/react";
import { SimpleModePanel } from "../../../src/components/generate/SimpleModePanel";
import type { GenerationState } from "../../../src/types";

vi.mock("../../../src/api/styleApi", () => ({
  fetchStylePresets: vi.fn().mockResolvedValue([]),
}));

beforeEach(() => {
  cleanup();
  global.fetch = vi.fn().mockRejectedValue(new Error("offline")) as unknown as typeof fetch;
});

afterEach(() => {
  cleanup();
});

function state(overrides: Partial<GenerationState>): GenerationState {
  return {
    isGenerating: false,
    statusText: "",
    suggestions: [],
    currentTaskId: null,
    error: null,
    ...overrides,
  } as GenerationState;
}

describe("S8: 生成の進捗が「読める」形で出る", () => {
  it("待機中は空（不要なノイズを出さない）", () => {
    render(<SimpleModePanel generationState={state({})} />);
    expect(screen.getByTestId("generation-status")).toHaveTextContent("");
  });

  it("生成中は statusText が表示される（aria-live 付き）", () => {
    render(
      <SimpleModePanel
        generationState={state({ isGenerating: true, statusText: "執筆ステータス: running..." })}
      />,
    );

    const status = screen.getByTestId("generation-status");
    expect(status).toHaveTextContent("執筆ステータス: running...");
    expect(status).toHaveAttribute("aria-live", "polite");
  });

  it("statusText が空でも「Luciano待機している」ことを伝える", () => {
    render(<SimpleModePanel generationState={state({ isGenerating: true })} />);
    expect(screen.getByTestId("generation-status")).toHaveTextContent(/お待ちください/);
  });

  it("エラーは role=alert で年薪される", () => {
    render(
      <SimpleModePanel
        generationState={state({ error: "生成タイムアウト（60秒を超過しました）" })}
      />,
    );

    const alert = screen.getByTestId("generation-error");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent("生成タイムアウト");
  });

  it("エラーが無いときはアラートを出さない", () => {
    render(<SimpleModePanel generationState={state({})} />);
    expect(screen.queryByTestId("generation-error")).not.toBeInTheDocument();
  });
});
