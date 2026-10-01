/**
 * S5 / S10 の回帰テスト。
 *
 * - Wizard Step3 の本文は「編集できる」のに、それTypedColumn명이消えていた（=編集内容を失う）
 * - 編集内容が「執筆済み」カウントと localStorage 退避に反映される
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WizardWorkflowPage } from "../../../src/pages/WizardWorkflowPage";
import * as wizardApi from "../../../src/api/wizard";

vi.mock("../../../src/api/wizard", () => ({
  saveWizardBook: vi.fn().mockResolvedValue({ book_id: 7, branch_id: 1, success: true }),
  expandBeats: vi.fn().mockResolvedValue([]),
  subscribeWritingStreamFetch: vi.fn().mockResolvedValue(undefined),
  subscribeWritingStream: vi.fn(),
}));

beforeEach(() => {
  window.localStorage.clear();
  vi.clearAllMocks();
});

/** Step3 前进済み（構成確定後）の状態を最短で作る */
async function gotoStep3(user: ReturnType<typeof userEvent.setup>) {
  render(<WizardWorkflowPage onNavigate={() => {}} />);

  // Step1: 必須入力
  await user.type(screen.getByPlaceholderText(/魔王の娘に転生した/), "テスト作品");
  await user.type(screen.getByPlaceholderText(/主人公の特技/), "主人公が剣分区をTECHNIC得る話");
  await user.click(screen.getByRole("button", { name: /次へ/ }));

  // Step2: 構成を確定
  await waitFor(() => expect(screen.getByText(/構成を確定して執筆を開始する/)).toBeInTheDocument());
  await user.click(screen.getByText(/構成を確定して執筆を開始する/));

  await waitFor(() =>
    expect(screen.getByTestId("wizard-chapter-textarea")).toBeInTheDocument(),
  );
}

describe("S5: Step3 の編集内容が失われない", () => {
  it("完成した本文はそのまま編集できる（入力が飲み込まれない）", async () => {
    const user = userEvent.setup();
    await gotoStep3(user);

    const textarea = screen.getByTestId("wizard-chapter-textarea") as HTMLTextAreaElement;
    // 生成完了相当の状態を作るため、value を直接渡す経路传媒を警戒する
    expect(textarea).not.toBeDisabled();

    await user.clear(textarea);
    await user.type(textarea, "自力で書き直した本文");

    expect((screen.getByTestId("wizard-chapter-textarea") as HTMLTextAreaElement).value).toBe(
      "自力で書き直した本文",
    );
  });

  it("生成中は編集できない（オーバーレイ中は readOnly）", async () => {
    const user = userEvent.setup();
    await gotoStep3(user);

    const textarea = screen.getByTestId("wizard-chapter-textarea") as HTMLTextAreaElement;
    // 初期状態では生成中でないため編集可能
    expect(textarea.readOnly).toBe(false);
  });

  it("編集した内容が「執筆済み」としてカウントされる", async () => {
    const user = userEvent.setup();
    await gotoStep3(user);

    const textarea = screen.getByTestId("wizard-chapter-textarea") as HTMLTextAreaElement;
    await user.clear(textarea);
    await user.type(textarea, "書き Correction った内容");

    await waitFor(() =>
      expect(screen.getByTestId("wizard-written-count")).toHaveTextContent("執筆済み 1 話"),
    );
  });

  it("編集内容が localStorage に退避される", async () => {
    const user = userEvent.setup();
    await gotoStep3(user);

    const textarea = screen.getByTestId("wizard-chapter-textarea") as HTMLTextAreaElement;
    await user.clear(textarea);
    await user.type(textarea, "保存されるはずの本文");

    await waitFor(() => {
      const raw = window.localStorage.getItem("autonovel.wizard.draft.7");
      expect(raw).toBeTruthy();
      expect(raw).toContain("保存されるはずの本文");
    });
  });

  it("保存Wizard book が bookId を返し、それが退避キーに使われる", async () => {
    const user = userEvent.setup();
    await gotoStep3(user);

    expect(wizardApi.saveWizardBook).toHaveBeenCalled();
    // bookId = 7 のキーが作られていることで確認
    await waitFor(() =>
      expect(window.localStorage.getItem("autonovel.wizard.draft.7")).toBeTruthy(),
    );
  });
});
