/**
 * S11 の回帰テスト：モーダルのフォーカス管理。
 */
import { describe, it, expect, vi } from "vitest";
import React, { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Modal } from "../../../src/components/common/Modal";

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} data-testid="opener">
        開く
      </button>
      <Modal isOpen={open} onClose={() => setOpen(false)} title="設定" testId="test-modal">
        <input data-testid="first-input" />
        <button type="button" data-testid="middle-button">途中</button>
        <input data-testid="last-input" />
      </Modal>
    </>
  );
}

describe("S11: Modal のフォーカス管理", () => {
  it("開くとダイアログへフォーカスが移る", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByTestId("opener"));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(document.activeElement).toBe(dialog);
  });

  it("閉じると開いた場所（元のボタン）にフォーカスが戻る", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const opener = screen.getByTestId("opener");
    await user.click(opener);
    await user.click(screen.getByLabelText("閉じる"));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.activeElement).toBe(opener);
  });

  it("閉じている間スクロールがロックされる", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    expect(document.body.style.overflow).toBe("");
    await user.click(screen.getByTestId("opener"));
    expect(document.body.style.overflow).toBe("hidden");

    await user.click(screen.getByLabelText("閉じる"));
    expect(document.body.style.overflow).toBe("");
  });

  it("Esc キーで閉じられる", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByTestId("opener"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
