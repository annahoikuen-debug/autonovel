/**
 * D3 の回帰テスト：Wizard の下書き退避が「復元され、かつ潰されない」。
 *
 * 以前は
 *   1) 書き込み effect が復元 effect より先に走る（bookId が null → 7 のとき
 *      中身の無い `{}` で既存の退避データを上書きする）
 *   2) bookId が component state のままで、リロード後は復元に入らない
 * の 2 点で、.writer と .reader のどちらかが死んでいた。
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WizardWorkflowPage } from "../../../src/pages/WizardWorkflowPage";

vi.mock("../../../src/api/wizard", () => ({
  saveWizardBook: vi.fn().mockResolvedValue({ book_id: 7, branch_id: 1, success: true }),
  expandBeats: vi.fn().mockResolvedValue([]),
  subscribeWritingStreamFetch: vi.fn().mockResolvedValue(undefined),
  subscribeWritingStream: vi.fn(),
}));

vi.mock("../../../src/api/client", () => ({
  apiFetch: vi.fn().mockRejectedValue(new Error("ネットワークに接続できません。")),
}));

const DRAFT_KEY = "autonovel.wizard.draft.7";
const BOOK_ID_KEY = "autonovel.wizard.bookId";
const SAVED_DRAFT = { 1: "保存しておいた第1話の本文", 2: "保存しておいた第2話の本文" };

const readDraft = () => window.localStorage.getItem(DRAFT_KEY);

beforeEach(() => {
  window.localStorage.clear();
  vi.clearAllMocks();
});

/** Step1 → Step2 → Step3（書籍ID確定）まで進める */
async function gotoStep3(user: ReturnType<typeof userEvent.setup>) {
  render(<WizardWorkflowPage onNavigate={() => {}} />);

  await user.type(screen.getByPlaceholderText(/魔王の娘に転生した/), "テスト作品");
  await user.type(screen.getByPlaceholderText(/主人公の特技/), "主人公が剣分区をTECHNIC得る話");
  await user.click(screen.getByRole("button", { name: /次へ/ }));

  await waitFor(() => expect(screen.getByText(/構成を確定して執筆を開始する/)).toBeInTheDocument());
  await user.click(screen.getByText(/構成を確定して執筆を開始する/));

  await waitFor(() =>
    expect(screen.getByTestId("wizard-chapter-textarea")).toBeInTheDocument(),
  );
}

describe("D3: 既存の下書きを潰さずに復元する", () => {
  it("bookId が確定した瞬間に退避データを空で上書きしない", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(DRAFT_KEY, JSON.stringify(SAVED_DRAFT));

    await gotoStep3(user);

    // saveWizardBook が book_id = 7 を返した直後（writer が先に走る commit）
    await waitFor(() =>
      expect(window.localStorage.getItem(BOOK_ID_KEY)).toBe("7"),
    );
    expect(readDraft()).toBe(JSON.stringify(SAVED_DRAFT));
    expect(readDraft()).not.toBe("{}");
    // 復元もまっている
    expect(screen.getByTestId("wizard-written-count")).toHaveTextContent("執筆済み 2 話");
  });

  it("リロード後（bookId が保存されている）でも下書きを復元する", async () => {
    window.localStorage.setItem(BOOK_ID_KEY, "7");
    window.localStorage.setItem(DRAFT_KEY, JSON.stringify(SAVED_DRAFT));

    render(<WizardWorkflowPage onNavigate={() => {}} />);

    expect(screen.getByTestId("wizard-written-count")).toHaveTextContent("執筆済み 2 話");
    // 復元で上書きもされない（本文が `{}` に落ちる問題）
    expect(readDraft()).toBe(JSON.stringify(SAVED_DRAFT));
  });

  it("復元された下書きが「最後の執筆話」として退出導線に出る", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(DRAFT_KEY, JSON.stringify(SAVED_DRAFT));

    await gotoStep3(user);

    expect(screen.getByTestId("wizard-exit-panel")).toHaveTextContent("第2話");
  });

  it("下書きが無い作品では空の退避データを書き込まない", async () => {
    const user = userEvent.setup();

    render(<WizardWorkflowPage onNavigate={() => {}} />);

    await user.type(screen.getByPlaceholderText(/魔王の娘に転生した/), "テスト作品");
    await user.type(screen.getByPlaceholderText(/主人公の特技/), "主人公が剣分区をTECHNIC得る話");
    await user.click(screen.getByRole("button", { name: /次へ/ }));
    await waitFor(() => expect(screen.getByText(/構成を確定して執筆を開始する/)).toBeInTheDocument());
    await user.click(screen.getByText(/構成を確定して執筆を開始する/));

    await waitFor(() =>
      expect(screen.getByTestId("wizard-chapter-textarea")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("wizard-written-count")).not.toBeInTheDocument();
    expect(screen.queryByTestId("wizard-exit-panel")).not.toBeInTheDocument();
    // 退避キーは作られるが、空データで上書きはしない
    expect(window.localStorage.getItem(BOOK_ID_KEY)).toBe("7");
    expect(readDraft()).toBeNull();
  });
});
