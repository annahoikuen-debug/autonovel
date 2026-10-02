/**
 * S4 の回帰テスト：モバイルクイック操作が「実際に本文へ反映される」こと、
 * および未接続の操作は「押せるのに何も起きない」形で露出しないこと。
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import React from "react";
import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MobileQuickActionBar } from "../../../src/components/mobile/MobileQuickActionBar";
import {
  findActiveManuscriptTextarea,
  insertTextIntoActiveManuscript,
} from "../../../src/utils/manuscriptInsertion";

afterEach(() => {
  cleanup();
  document.body.innerHTML = "";
});

describe("S4: モバイルQuickAction は実際の本文へ反映される", () => {
  it("編集中の textarea に文字が挿入される", async () => {
    document.body.innerHTML = `<textarea id="editor-textarea"></textarea>`;
    const textarea = document.getElementById("editor-textarea") as HTMLTextAreaElement;
    textarea.value = "文章の";
    textarea.selectionStart = textarea.value.length;
    textarea.selectionEnd = textarea.value.length;

    const onInsert = vi.fn((text: string) => {
      insertTextIntoActiveManuscript(text);
    });

    render(<MobileQuickActionBar onInsertText={onInsert} />);
    await userEvent.click(screen.getByTestId("quick-insert-brackets"));

    expect(onInsert).toHaveBeenCalledWith("「」");
    expect(textarea.value).toBe("文章の「」");
  });

  it("選択範囲があれば置換される", () => {
    document.body.innerHTML = `<textarea id="editor-textarea"></textarea>`;
    const textarea = document.getElementById("editor-textarea") as HTMLTextAreaElement;
    textarea.value = "これは古い文章です";
    textarea.selectionStart = 3;
    textarea.selectionEnd = 7; // 「古い文章」

    expect(insertTextIntoActiveManuscript("……")).toBe(true);
    expect(textarea.value).toBe("これは……です");
  });

  it("対象 textarea が無い場合は失敗を正直に返す（嘘の成功にしない）", () => {
    document.body.innerHTML = `<div>本文を開く画面ではない</div>`;
    expect(findActiveManuscriptTextarea()).toBeNull();
    expect(insertTextIntoActiveManuscript("「」")).toBe(false);
  });

  it("Wizard の textarea も挿入先として認識される", () => {
    document.body.innerHTML = `<textarea data-testid="wizard-chapter-textarea"></textarea>`;
    expect(findActiveManuscriptTextarea()).not.toBeNull();
  });

  it("読取専用の textarea は挿入先にしない", () => {
    document.body.innerHTML = `<textarea id="editor-textarea" readonly></textarea>`;
    expect(findActiveManuscriptTextarea()).toBeNull();
  });

  it("実処理が渡されていない操作は描画されない", () => {
    render(<MobileQuickActionBar onInsertText={vi.fn()} />);

    // 記号系の操作は常に出る
    expect(screen.getByTestId("quick-insert-brackets")).toBeInTheDocument();
    expect(screen.getByTestId("quick-insert-ellipsis")).toBeInTheDocument();
    // 未提供の AI 操作は出ない（押しても何も起こらないボタンを作らない）
    expect(screen.queryByTestId("quick-ai-continue")).not.toBeInTheDocument();
    expect(screen.queryByTestId("quick-proofread")).not.toBeInTheDocument();
  });

  it("実処理が渡された操作は描画され、呼ばれたことを確認できる", async () => {
    const onAiContinue = vi.fn();
    const onProofread = vi.fn();
    render(
      <MobileQuickActionBar
        onInsertText={vi.fn()}
        onAiContinue={onAiContinue}
        onProofread={onProofread}
      />,
    );

    await userEvent.click(screen.getByTestId("quick-ai-continue"));
    await userEvent.click(screen.getByTestId("quick-proofread"));

    expect(onAiContinue).toHaveBeenCalled();
    expect(onProofread).toHaveBeenCalled();
  });
});
