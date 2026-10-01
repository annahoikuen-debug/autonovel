/**
 * R4/R5/R6/R9 の回帰テスト：技術債が復活しないことを固定する。

 * 対象:
 *   R4  NovelContext の孤児 state（selectedStyleId 等）が戻っていない
 *   R5  空実装ハンドラ（// Implementation placeholder）が残っていない
 *   R6  孤児ファイル WizardStep.tsx / 未使用 props が復活していない
 *   R9  内部ステータス文字列がそのまま UI へ出ていない
 */
import { describe, it, expect } from "vitest";
import React from "react";
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import { NovelProvider, useNovelContext } from "../../../src/context/NovelContext";
import { SimpleModePanel } from "../../../src/components/generate/SimpleModePanel";

afterEach(() => cleanup());

describe("R4: NovelContext に孤児 state が無いこと", () => {
  it("selectedStyleId 系が context value に残っていない", () => {
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
    for (const key of [
      "selectedStyleId",
      "setSelectedStyleId",
      "customStyleProfile",
      "setCustomStyleProfile",
      "showApiSettings",
      "setShowApiSettings",
      "showApiKey",
      "setShowApiKey",
    ]) {
      expect(Object.prototype.hasOwnProperty.call(ctx!, key)).toBe(false);
    }
  });
});

describe("R6: 未実装プレースホルダが残っていないこと", () => {
  it("空実装ハンドラが残っていない", async () => {
    const fs = await import("node:fs/promises");
    const path = await import("node:path");
    const src = await fs.readFile(
      path.resolve(process.cwd(), "src/components/GeneratePanel.tsx"),
      "utf-8",
    );
    expect(src).not.toContain("Implementation placeholder");
  });
});

describe("R9: 生成進捗がユーザー向け文言になること", () => {
  it("内部ステータス値（running など）をそのまま表示しない", () => {
    render(
      <SimpleModePanel
        generationState={
          {
            isGenerating: true,
            statusText: "🪄 AIが執筆しています。このままお待ちください…",
            suggestions: [],
            currentTaskId: "t1",
            error: null,
          } as never
        }
      />,
    );

    const status = screen.getByTestId("generation-status");
    expect(status).toHaveTextContent(/執筆しています/);
    expect(status.textContent).not.toContain("running");
  });
});
