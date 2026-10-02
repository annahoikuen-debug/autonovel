/**
 * S3 / S12 の回帰テスト。
 *
 * - ORCHESTRA（マルチエージェント執筆）が実際に到達できること
 * - Studio が外部のプレースホルダー画像サービスを参照しないこと
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import GeneratePanel from "../../../src/components/GeneratePanel";
import { StudioWorkspace } from "../../../src/components/studio/StudioWorkspace";
import { NovelProvider } from "../../../src/context/NovelContext";

vi.mock("../../../src/api/styleApi", () => ({
  fetchStylePresets: vi.fn().mockResolvedValue([]),
  distillStyleFromText: vi.fn(),
}));

vi.mock("../../../src/api/easyMode", () => ({
  generateGachaPlans: vi.fn(),
  generateDigest: vi.fn(),
  promoteToStudio: vi.fn(),
  generateContent: vi.fn(),
}));

vi.mock("../../../src/api/quality", () => ({
  fetchChapterBookScore: vi.fn().mockResolvedValue({ overall_score: 90, dimensions: {} }),
}));

vi.mock("../../../src/api/client", () => ({
  apiFetch: vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({}) }),
  handleResponse: vi.fn(),
}));

beforeEach(() => {
  window.localStorage.clear();
  global.fetch = vi.fn().mockRejectedValue(new Error("offline")) as unknown as typeof fetch;
});

describe("S3: ORCHESTRA モードへ到達できる", () => {
  it("上級モードを展開すると ORCHESTRA ボタンが出現する", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <NovelProvider>
          <GeneratePanel />
        </NovelProvider>
      </MemoryRouter>,
    );

    // 既定では隠れている（段階開示の維持）
    expect(screen.queryByTestId("btn-submode-orchestrated")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("btn-show-advanced-modes"));

    expect(screen.getByTestId("btn-submode-orchestrated")).toBeInTheDocument();
    expect(screen.getByText(/マルチエージェント執筆/)).toBeInTheDocument();
  });

  it("ORCHESTRA を押すとパネルが差し替わる（デッドでない）", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <NovelProvider>
          <GeneratePanel />
        </NovelProvider>
      </MemoryRouter>,
    );

    await user.click(screen.getByTestId("btn-show-advanced-modes"));
    await user.click(screen.getByTestId("btn-submode-orchestrated"));

    // ORCHESTRA パネル固有の UI が出る
    await waitFor(() => {
      expect(screen.getByTestId("btn-submode-orchestrated")).toHaveClass("btn-primary");
    });
    // かんたんモードの主CTAは消えている（モードが切り替わっている）
    expect(screen.queryByTestId("btn-easy-generate")).not.toBeInTheDocument();
  });

  it("「かんたん執筆」に戻せる", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <NovelProvider>
          <GeneratePanel />
        </NovelProvider>
      </MemoryRouter>,
    );

    await user.click(screen.getByTestId("btn-show-advanced-modes"));
    await user.click(screen.getByTestId("btn-submode-orchestrated"));
    await user.click(screen.getByTestId("btn-submode-simple"));

    expect(screen.getByTestId("btn-easy-generate")).toBeInTheDocument();
  });
});

describe("S12: 外部プレースホルダー画像を参照しない", () => {
  it("Studio のソースが placehold.co の URL を組み立てない", async () => {
    const fs = await import("node:fs/promises");
    const path = await import("node:path");
    const src = await fs.readFile(
      path.resolve(process.cwd(), "src/components/studio/StudioWorkspace.tsx"),
      "utf-8",
    );
    // 実際に外部サービスへ接続する URL 組み立てが残っていないこと
    // （コメント中の言及は可。`https://placehold.co/...` 形式の文字列が禁止）
    expect(src).not.toMatch(/https?:\/\/placehold\.co/);
    expect(src).not.toMatch(/`https:\/\/placehold/);
  });

  it("シーン画像 API が失敗しても画面が落ちない", () => {
    render(
      <MemoryRouter initialEntries={["/studio"]}>
        <NovelProvider>
          <StudioWorkspace />
        </NovelProvider>
      </MemoryRouter>,
    );

    // プレースホルダー画像が出てこない
    expect(document.body.innerHTML).not.toContain("placehold.co");
  });
});
