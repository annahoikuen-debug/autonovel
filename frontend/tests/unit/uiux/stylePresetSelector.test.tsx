/**
 * S7 の回帰テスト：Easy Mode の初期画面から内部キーを排除し、
 * 選んだ文体が生成処理まで届くこと。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SimpleModePanel } from "../../../src/components/generate/SimpleModePanel";

const fetchStylePresetsMock = vi.fn();

vi.mock("../../../src/api/styleApi", () => ({
  fetchStylePresets: () => fetchStylePresetsMock(),
}));

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  fetchStylePresetsMock.mockResolvedValue([]);
  // planning_options は必ず失敗させる（このテストはスタイル選択に集中する）
  global.fetch = vi.fn().mockRejectedValue(new Error("offline")) as unknown as typeof fetch;
});

afterEach(() => {
  cleanup();
});

describe("S7: 文体は「選べる」itespace 項目になる", () => {
  it("内部キー（style_web_standard）を打つテキストボックスではない", () => {
    render(<SimpleModePanel />);

    const select = screen.getByTestId("style-preset-select");
    expect(select.tagName).toBe("SELECT");

    // 生入力欄（type=text で内部キー既定値）が出ていない
    const rawInputs = screen.queryAllByDisplayValue("style_web_standard");
    expect(rawInputs).toHaveLength(0);
    expect(select).toHaveValue("auto");
  });

  it("label が select に紐付いている（クリックでフォーカス移動する）", () => {
    render(<SimpleModePanel />);

    const label = screen.getByText("文体の雰囲気");
    expect(label.getAttribute("for")).toBe("style-preset-select");
  });

  it("バックエンドのプリセット会去時される", async () => {
    fetchStylePresetsMock.mockResolvedValue([
      { id: "style_web_standard", name: "Web小説" },
      { id: "style_dark", name: "ダークファンタジー" },
    ]);

    render(<SimpleModePanel />);

    await waitFor(() => expect(screen.getByText("Web小説")).toBeInTheDocument());
    expect(screen.getByText("ダークファンタジー")).toBeInTheDocument();
  });

  it("API が失敗してもフォールバックの選択肢で操作できる", () => {
    fetchStylePresetsMock.mockRejectedValue(new Error("offline"));

    render(<SimpleModePanel />);

    expect(screen.getByTestId("style-preset-select")).toBeInTheDocument();
    // option 要素として持つことを見る（説明文にも同じ語が出るため option に限定する）
    const options = Array.from(
      screen.getByTestId("style-preset-select").querySelectorAll("option"),
    ).map((o) => o.textContent);
    expect(options.some((t) => t?.includes("AIにおまかせ"))).toBe(true);
    expect(options.length).toBeGreaterThan(1);
  });

  it("選んだ文体が startGeneration に渡る", async () => {
    const user = userEvent.setup();
    fetchStylePresetsMock.mockResolvedValue([
      { id: "auto", name: "AIにおまかせ" },
      { id: "style_dark", name: "ダークファンタジー" },
    ]);

    const startGeneration = vi.fn();
    const startStreaming = vi.fn();

    render(<SimpleModePanel startGeneration={startGeneration} startStreaming={startStreaming} />);

    await waitFor(() => expect(screen.getByText("ダークファンタジー")).toBeInTheDocument());
    await user.selectOptions(screen.getByTestId("style-preset-select"), "style_dark");

    await user.click(screen.getByTestId("btn-easy-generate"));
    expect(startGeneration).toHaveBeenCalledWith("style_dark");

    await user.click(screen.getByTestId("btn-streaming-generate"));
    expect(startStreaming).toHaveBeenCalledWith("style_dark");
  });

  it("主CTAと副CTAの主次が明示されている", () => {
    render(<SimpleModePanel />);

    const primary = screen.getByTestId("btn-easy-generate");
    const secondary = screen.getByTestId("btn-streaming-generate");

    expect(primary.className).toContain("btn-primary");
    expect(secondary.className).toContain("btn-secondary");
    expect(primary.textContent).toContain("かんたん執筆");
  });
});
