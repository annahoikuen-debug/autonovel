import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Editor } from "../../src/components/editor/Editor";
import { ChapterOutlineTree } from "../../src/components/studio/ChapterOutlineTree";
import { StudioWorkspace } from "../../src/components/studio/StudioWorkspace";
import { NovelProvider } from "../../src/context/NovelContext";
import { apiFetch } from "../../src/api/client";

// 章名の変更は「楽観更新 → サーバー保存 → 失敗時は巻き戻し」になったため、
// 通信が失敗すると直前のタイトルへ戻ってしまう（tests/unit/uiux/ の D4 がその契約）。
// ここでは UI の編集操作だけを検証したいので、保存 (PUT) は成功させる。
// 一方 章一覧 (GET) は失敗させる。成功させると NovelContext の hydration が
// NovelProvider の初期値 (1 話) で上書きし、章ツリーが空になるため。
vi.mock("../../src/api/client", () => ({
  apiFetch: vi.fn(),
}));

const mockedApiFetch = vi.mocked(apiFetch);

const okResponse = (data: unknown = { saved: true }) =>
  ({ ok: true, status: 200, json: async () => data }) as unknown as Response;

beforeEach(() => {
  mockedApiFetch.mockReset();
  mockedApiFetch.mockImplementation((_endpoint, options) => {
    if (options?.method === "PUT" || options?.method === "DELETE") {
      return Promise.resolve(okResponse());
    }
    return Promise.reject(new Error("章一覧は取得しない"));
  });
});

describe("Editor component refinements", () => {
  it("displays character count, line count and estimated reading time", () => {
    const handleChange = vi.fn();
    const content = "1行目テストテキスト\n2行目テストテキスト\n3行目テストテキスト";

    render(
      <NovelProvider>
        <Editor content={content} onChange={handleChange} />
      </NovelProvider>
    );

    expect(screen.getByText("3")).toBeInTheDocument(); // 行数: 3行
    expect(screen.getByTestId("editor-char-count")).toHaveTextContent("30");
    expect(screen.getByText(/読了目安:/)).toBeInTheDocument();
  });

  it("inserts ruby syntax when ruby button is clicked", async () => {
    const user = userEvent.setup();
    const handleChange = vi.fn();
    const onToast = vi.fn();

    render(
      <NovelProvider>
        <Editor content="勇者アルト" onChange={handleChange} onToast={onToast} />
      </NovelProvider>
    );

    const rubyBtn = screen.getByTestId("btn-insert-ruby");
    await user.click(rubyBtn);

    expect(handleChange).toHaveBeenCalled();
    expect(onToast).toHaveBeenCalledWith(
      expect.stringContaining("ルビ記法"),
      "info"
    );
  });
});

describe("ChapterOutlineTree inline editing", () => {
  it("allows inline editing of chapter title", async () => {
    const user = userEvent.setup();

    render(
      <NovelProvider>
        <ChapterOutlineTree />
      </NovelProvider>
    );

    // タイトル編集ボタンをクリック
    const editBtn = screen.getByTestId("btn-edit-title-1");
    await user.click(editBtn);

    // インライン入力フォームが表示される
    const editInput = screen.getByTestId("input-edit-chapter-title");
    expect(editInput).toBeInTheDocument();

    await user.clear(editInput);
    await user.type(editInput, "第1話 運命の剣{Enter}");

    // 半角スペースが入力できること（章枠側の Space 選択に奪われないこと）
    expect(editInput).toHaveValue("第1話 運命の剣");

    await waitFor(() => expect(screen.getByText("第1話 運命の剣")).toBeInTheDocument());

    // 実際に PUT へ新しいタイトルが届いていること
    const put = mockedApiFetch.mock.calls.find(
      ([, options]) => (options as RequestInit | undefined)?.method === "PUT",
    );
    expect(put).toBeDefined();
    expect(JSON.parse(String((put![1] as RequestInit).body))).toMatchObject({
      title: "第1話 運命の剣",
    });
  });
});

describe("StudioWorkspace collapsible sidebars", () => {
  it("toggles left and right sidebars smoothly", async () => {
    const user = userEvent.setup();

    render(
      <NovelProvider>
        <StudioWorkspace />
      </NovelProvider>
    );

    // 初期状態: 左ペイン・右ペインが表示されている
    expect(screen.getByTestId("btn-toggle-left-pane")).toBeInTheDocument();
    expect(screen.getByTestId("btn-toggle-right-pane")).toBeInTheDocument();

    // 左ペインを折りたたむ
    await user.click(screen.getByTestId("btn-toggle-left-pane"));
    expect(screen.queryByTestId("btn-toggle-left-pane")).not.toBeInTheDocument();
    expect(screen.getByTestId("btn-restore-left-pane")).toBeInTheDocument();

    // 左ペインを展開する
    await user.click(screen.getByTestId("btn-restore-left-pane"));
    expect(screen.getByTestId("btn-toggle-left-pane")).toBeInTheDocument();
  });
});
