/**
 * 回帰テスト: Modal のアクセシビリティと、複数同時に開いたときの挙動（D12）。
 *
 * - フォーカスを戻す effect に cleanup が無く、開いたまま消えると focus が迷子になる
 * - スクロールロックが入れ子（非スタック）非対応で、内側を閉じた瞬間に背面がスクロールする
 * - Esc が window 直 listeners で両方のモーダルに届き、1 回で両方閉じる
 * - ariaLabelledBy / testId のどちらも無いとダイアログにアクセシブルネームが無い
 * - フォーカス判定に offsetParent を使うと jsdom で常に不可視＝トラップが死んだまま
 */
import { describe, it, expect, afterEach } from "vitest";
import React, { useState } from "react";
import { fireEvent, render, screen, cleanup } from "@testing-library/react";
import { Modal } from "../../../src/components/common/Modal";

afterEach(() => {
  cleanup();
  document.body.style.overflow = "";
});

describe("Modal: アクセシブルネーム", () => {
  it("ariaLabelledBy も testId も無くてもダイアログに名前がある", () => {
    render(
      <Modal isOpen onClose={() => {}} title="設定">
        <p>本文</p>
      </Modal>,
    );

    expect(screen.getByRole("dialog")).toHaveAccessibleName("設定");
  });

  it("title が ReactNode でも見出し経由で名前が決まる", () => {
    render(
      <Modal isOpen onClose={() => {}} title={<span>⚙️ LLM設定</span>}>
        <p>本文</p>
      </Modal>,
    );

    expect(screen.getByRole("dialog")).toHaveAccessibleName("⚙️ LLM設定");
  });

  it("testId から作った見出し id を aria-labelledby で参照する", () => {
    render(
      <Modal isOpen onClose={() => {}} title="本棚" testId="bookshelf-modal">
        <p>本文</p>
      </Modal>,
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-labelledby", "bookshelf-modal-title");
    expect(dialog).toHaveAccessibleName("本棚");
  });
});

describe("Modal: 同時に開いたモーダル", () => {
  function Stacked() {
    const [outer, setOuter] = useState(true);
    const [inner, setInner] = useState(true);
    return (
      <>
        <Modal
          isOpen={outer}
          onClose={() => setOuter(false)}
          title="外側"
          testId="outer-modal"
          closeBtnTestId="close-outer"
        >
          <p>外側の本文</p>
        </Modal>
        <Modal
          isOpen={inner}
          onClose={() => setInner(false)}
          title="内側"
          testId="inner-modal"
          closeBtnTestId="close-inner"
        >
          <p>内側の本文</p>
        </Modal>
      </>
    );
  }

  it("Esc 1 回では一番上のモーダルしか閉じない", () => {
    render(<Stacked />);
    expect(screen.getByTestId("outer-modal")).toBeInTheDocument();
    expect(screen.getByTestId("inner-modal")).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "Escape" });

    expect(screen.queryByTestId("inner-modal")).not.toBeInTheDocument();
    expect(screen.getByTestId("outer-modal")).toBeInTheDocument();
  });

  it("外側を閉じても内側が開いている間はスクロールをロックし続ける", () => {
    render(<Stacked />);
    expect(document.body.style.overflow).toBe("hidden");

    fireEvent.click(screen.getByTestId("close-outer"));

    expect(screen.queryByTestId("outer-modal")).not.toBeInTheDocument();
    expect(screen.getByTestId("inner-modal")).toBeInTheDocument();
    // 内側が開いている間は背面をスクロールさせない
    expect(document.body.style.overflow).toBe("hidden");

    // 最後の 1 枚を閉じたら解除する
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByTestId("inner-modal")).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe("");
  });
});

describe("Modal: フォーカスの復元", () => {
  it("開いたままアンマウントされてもフォーカスを開いた場所へ戻す", () => {
    function Host() {
      const [mounted, setMounted] = useState(false);
      return (
        <>
          <button type="button" data-testid="opener" onClick={() => setMounted(true)}>
            開く
          </button>
          <button type="button" data-testid="forcer" onClick={() => setMounted(false)}>
            強制終了
          </button>
          {mounted && (
            <Modal
              isOpen
              onClose={() => setMounted(false)}
              title="設定"
              testId="unmount-modal"
            >
              <p>本文</p>
            </Modal>
          )}
        </>
      );
    }

    render(<Host />);
    const opener = screen.getByTestId("opener");
    opener.focus();
    fireEvent.click(opener);
    // 開いたらダイアログ自身へフォーカスが移る
    expect(screen.getByRole("dialog")).toHaveFocus();

    // isOpen を false にせず、要素ごと消す
    fireEvent.click(screen.getByTestId("forcer"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    // 開いた位置へフォーカスが戻る
    expect(document.activeElement).toBe(opener);
  });
});

describe("Modal: フォーカストラップ", () => {
  function Trap() {
    return (
      <Modal isOpen onClose={() => {}} title="設定" testId="trap-modal">
        <button type="button" data-testid="first">
          最初
        </button>
        <button type="button" data-testid="last">
          最後
        </button>
      </Modal>
    );
  }

  it("最後の要素で Tab すると最初のフォーカス可能要素（閉じるボタン）へ戻る", () => {
    render(<Trap />);
    const dialog = screen.getByRole("dialog");
    const close = dialog.querySelector(".modal-close-btn") as HTMLElement;
    const last = screen.getByTestId("last");

    last.focus();
    fireEvent.keyDown(dialog, { key: "Tab" });

    expect(document.activeElement).toBe(close);
  });

  it("最初の要素で Shift+Tab すると最後の要素へ戻る", () => {
    render(<Trap />);
    const dialog = screen.getByRole("dialog");
    const close = dialog.querySelector(".modal-close-btn") as HTMLElement;

    close.focus();
    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });

    expect(document.activeElement).toBe(screen.getByTestId("last"));
  });
});
