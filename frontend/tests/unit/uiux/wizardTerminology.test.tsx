/**
 * S9 の回帰テスト：専門用語に説明があること、画面に英語選択肢が露出しないこと。
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import { render, screen } from "@testing-library/react";
import { Step1PlotInput } from "../../../src/components/wizard/Step1PlotInput";
import { Step2StructureReview } from "../../../src/components/wizard/Step2StructureReview";
import type { OutlineItem } from "../../../src/components/wizard/Step2StructureReview";

vi.mock("../../../src/api/wizard", () => ({
  expandBeats: vi.fn().mockResolvedValue([]),
}));

beforeEach(() => {
  global.fetch = vi.fn().mockRejectedValue(new Error("offline")) as unknown as typeof fetch;
});

describe("S9-1: Step1 の専門用語に説明がある", () => {
  it("スライダーの両端の説明と aria-valuetext が付く", () => {
    render(<Step1PlotInput onNext={vi.fn()} />);

    expect(screen.getByText(/1: 主人公も一般人/)).toBeInTheDocument();
    expect(screen.getByText(/1: 穏やか/)).toBeInTheDocument();
    expect(screen.getByText(/0: 主人公が独力でなんとか/)).toBeInTheDocument();

    const cheat = screen.getByLabelText(/チート度/) as HTMLInputElement;
    expect(cheat).toHaveAttribute("aria-valuetext");
    expect(cheat.getAttribute("aria-valuetext")).toMatch(/主人公|有利|無敵|頼れる/);
  });

  it("label がスライダー input に紐付いている", () => {
    render(<Step1PlotInput onNext={vi.fn()} />);

    expect(screen.getByLabelText(/チート度/)).toBeInTheDocument();
    expect(screen.getByLabelText(/代償・世界の過酷さ/)).toBeInTheDocument();
    expect(screen.getByLabelText(/主人公をやさしく助ける割合/)).toBeInTheDocument();
    expect(screen.getByLabelText(/目標話数/)).toBeInTheDocument();
  });

  it("見出しが既存の導線文言を保っている（後方互換）", () => {
    render(<Step1PlotInput onNext={vi.fn()} />);
    // 既存テストが `Step 1: ...` を前提にしているため文言は据え置く。
    // 日本語化は専門用語の説明側で担保する。
    expect(screen.getByText(/Step 1:/)).toBeInTheDocument();
  });
});

describe("S9-2: Step2 の選択肢が日本語で出る", () => {
  const outlines: OutlineItem[] = [
    {
      episode: 1,
      title: "第1話: はじまり",
      outline: "主人公が剣を手にする場面",
      cliffhangerType: "New Crisis",
      sensoryFocus: ["visual"],
      foreshadowingNotes: "伏線メモ",
    },
  ];

  it("クリフハンガーが日本語ラベルで並ぶ（英語は出ない）", () => {
    render(
      <Step2StructureReview outlines={outlines} onBack={vi.fn()} onConfirm={vi.fn()} />,
    );

    expect(screen.getByRole("option", { name: "新たな危機" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "衝撃の真実" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "静かな伏線" })).toBeInTheDocument();

    // 内部値としての英語は表示文本には残さない
    expect(screen.queryByRole("option", { name: "New Crisis" })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Shocking Truth" })).not.toBeInTheDocument();
  });

  it("五感タグが日本語で並ぶ", () => {
    render(
      <Step2StructureReview outlines={outlines} onBack={vi.fn()} onConfirm={vi.fn()} />,
    );

    for (const label of ["視覚", "聴覚", "嗅覚", "触覚", "味覚", "比喩"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    // 英語テキストが露出しない
    expect(screen.queryByText("#visual")).not.toBeInTheDocument();
    expect(screen.queryByText("#auditory")).not.toBeInTheDocument();
  });

  it("内部値（英語）は API 送信値として保持される", () => {
    render(
      <Step2StructureReview outlines={outlines} onBack={vi.fn()} onConfirm={vi.fn()} />,
    );

    const select = screen.getByDisplayValue("新たな危機") as HTMLSelectElement;
    expect(select.value).toBe("New Crisis");
  });

  it("見出しが既存の導線文言を保っている（後方互換）", () => {
    render(
      <Step2StructureReview outlines={outlines} onBack={vi.fn()} onConfirm={vi.fn()} />,
    );
    expect(screen.getByText(/Step 2:/)).toBeInTheDocument();
  });
});
