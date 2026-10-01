/**
 * D4 の回帰テスト：保存に失敗したら巻き戻し、ユーザーへ通知する。
 *
 * 以前は全 call site が `.then()` だけで `.catch()` が無く、
 * `apiFetch` が投げる `ApiNetworkError` が unhandled rejection になって
 * 「何も起きないまま画面だけが壊れた」状態になっていた。
 *
 * ここでは PUT / DELETE を保留させて「楽観更新 → 失敗 → 巻き戻し」の順序を
 * 観測できる状态下にしてから失敗させる。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { apiFetch } from "../../../src/api/client";
import { makeChapter, renderOutlineTree, endpoints } from "./chapterOutlineTreeHarness";

vi.mock("../../../src/api/client", () => ({
  apiFetch: vi.fn(),
}));

const mockedApiFetch = vi.mocked(apiFetch);

const THREE_CHAPTERS = [
  makeChapter(1, { title: "A" }),
  makeChapter(2, { title: "B" }),
  makeChapter(3, { title: "C" }),
];

const NETWORK_DOWN = "ネットワークに接続できません。";

/** 保留している保存リクエストをまとめて失敗させる */
let pendingRejects: ((reason: unknown) => void)[] = [];

const failPendingSaves = async () => {
  const rejects = pendingRejects;
  pendingRejects = [];
  await act(async () => {
    rejects.forEach((reject) => reject(new Error(NETWORK_DOWN)));
  });
};

let unhandled: unknown[] = [];
const trackUnhandled = (event: PromiseRejectionEvent) => {
  unhandled.push(event.reason);
};

beforeEach(() => {
  mockedApiFetch.mockReset();
  pendingRejects = [];
  // 章一覧の取得（Hydration）は即失敗、保存（PUT/DELETE）は保留する
  mockedApiFetch.mockImplementation((_endpoint, options) => {
    if (options?.method === "PUT" || options?.method === "DELETE") {
      return new Promise<Response>((_resolve, reject) => {
        pendingRejects.push(reject);
      });
    }
    return Promise.reject(new Error(NETWORK_DOWN));
  });
  unhandled = [];
  window.addEventListener("unhandledrejection", trackUnhandled);
});

afterEach(() => {
  window.removeEventListener("unhandledrejection", trackUnhandled);
});

const errorMessageShown = () => screen.getByTestId("message-log").textContent ?? "";

describe("D4: 保存失敗はユーザーへ伝えて巻き戻す", () => {
  it("章名の変更が失敗したら元のタイトルへ戻す", async () => {
    const user = userEvent.setup();
    renderOutlineTree({ chapters: THREE_CHAPTERS });

    await user.click(screen.getByTestId("btn-edit-title-2"));
    const input = screen.getByTestId("input-edit-chapter-title");
    await user.clear(input);
    await user.type(input, "書き換えたタイトル");
    await user.tab();

    // 楽観更新は画面に反映される
    expect(screen.getByText("書き換えたタイトル")).toBeInTheDocument();

    await failPendingSaves();

    await waitFor(() => expect(screen.getByText("Sample 2")).toBeInTheDocument());
    expect(screen.queryByText("書き換えたタイトル")).not.toBeInTheDocument();
    expect(errorMessageShown()).toContain("サーバーに保存できませんでした");
  });

  it("並び替えが失敗したら元の並びへ戻し、通知する", async () => {
    const user = userEvent.setup();
    renderOutlineTree({ chapters: THREE_CHAPTERS });

    await user.click(within(screen.getByTestId("chapter-item-2")).getByText("▲"));
    // 楽観更新（話数が入れ替わっている）
    expect(screen.getByTestId("chapter-item-1")).toHaveTextContent("B");

    await failPendingSaves();

    await waitFor(() => expect(errorMessageShown()).toContain("章の並び替え"));
    // 並びも選択中の話も元へ戻す
    expect(screen.getByTestId("chapter-item-1")).toHaveTextContent("Sample 1");
    expect(screen.getByTestId("chapter-item-2")).toHaveTextContent("Sample 2");
  });

  it("削除が失敗したら消した章を復活させ、通知する", async () => {
    const user = userEvent.setup();
    renderOutlineTree({ chapters: THREE_CHAPTERS });

    await user.click(screen.getByTestId("btn-delete-chapter-2"));
    expect(screen.queryByTestId("chapter-item-2")).not.toBeInTheDocument();

    await failPendingSaves();

    await waitFor(() => expect(errorMessageShown()).toContain("章の削除"));
    expect(screen.getByTestId("chapter-item-2")).toHaveTextContent("Sample 2");
    expect(endpoints(mockedApiFetch, "DELETE")).toEqual([
      "/api/episodes/chapters/1/2?branch_id=1",
    ]);
  });

  it("章の追加が失敗したら追加を取り消す", async () => {
    const user = userEvent.setup();
    renderOutlineTree({ chapters: THREE_CHAPTERS });

    await user.click(screen.getByTestId("btn-add-chapter"));
    expect(screen.getByTestId("chapter-item-4")).toBeInTheDocument();

    await failPendingSaves();

    await waitFor(() => expect(errorMessageShown()).toContain("章の追加"));
    expect(screen.queryByTestId("chapter-item-4")).not.toBeInTheDocument();
    expect(screen.getByText(/章・プロット一覧 \(3話\)/)).toBeInTheDocument();
  });

  it("保存失敗が unhandled rejection として漏れない", async () => {
    const user = userEvent.setup();
    renderOutlineTree({ chapters: THREE_CHAPTERS });

    await user.click(within(screen.getByTestId("chapter-item-2")).getByText("▲"));
    await failPendingSaves();
    // unhandledrejection が届くだけの余裕を持たせる
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 30));
    });

    expect(unhandled).toEqual([]);
    expect(errorMessageShown()).not.toBe("");
  });
});
