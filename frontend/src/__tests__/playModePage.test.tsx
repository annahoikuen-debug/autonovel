/**
 * PlayModePage の結合テスト(Phase 0 S14)
 *
 * api 層(api/branches, api/books)をモックし、UI の状態遷移を検証する。
 * 完了条件: npm run test:ci の失敗数が現状ベースラインから増えないこと(Q5)。
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { routes } from "../routes";
import {
  BranchResponse,
  BranchPlaySessionResponse,
  BranchPlayStateResponse,
} from "../types/branches";

/**
 * BookPicker は作品一覧を NovelContext から受けるが、
 * 一覧の読み込み(refreshBooks)は AppLayout の役割のため、
 * ページ単体テストではコンテキストをスタブする。
 */
vi.mock("../context/NovelContext", () => ({
  useNovelContext: () => ({
    books: [
      {
        id: 1,
        title: "テスト小説",
        genre: "ハイファンタジー (R15)",
        concept: "",
        synopsis: "",
        target_eps: 10,
        created_at: "2026-11-23T00:00:00Z",
      },
    ],
    selectedBook: null,
  }),
}));

vi.mock("../api/branches", () => ({
  fetchBranches: vi.fn(),
  fetchBranchTree: vi.fn(),
  forkBranch: vi.fn(),
  previewBranchMerge: vi.fn(),
  commitBranchMerge: vi.fn(),
  fetchChapterDiff: vi.fn(),
  startPlaySession: vi.fn(),
  fetchPlayState: vi.fn(),
  choosePlayChoice: vi.fn(),
  savePlayPoint: vi.fn(),
  loadPlayPoint: vi.fn(),
  endPlaySession: vi.fn(),
  fetchPlaythrough: vi.fn(),
  dynamicContinueScene: vi.fn(),
}));

vi.mock("../api/books", () => ({
  fetchBooks: vi.fn(),
  fetchBookById: vi.fn(),
  createBook: vi.fn(),
}));

vi.mock("../api/illustrations", () => ({
  // 既定は「挿絵なし」(undefined) — 画像を出すテストのみ個別に上書きする
  fetchSceneIllustration: vi.fn().mockResolvedValue(undefined),
  fetchEpisodeIllustration: vi.fn().mockResolvedValue(undefined),
}));

import { fetchEpisodeIllustration } from "../api/illustrations";

const mockFetchEpisodeIllustration = vi.mocked(fetchEpisodeIllustration);

import * as branchesApi from "../api/branches";

const mockFetchBranches = vi.mocked(branchesApi.fetchBranches);
const mockStart = vi.mocked(branchesApi.startPlaySession);
const mockState = vi.mocked(branchesApi.fetchPlayState);
const mockChoose = vi.mocked(branchesApi.choosePlayChoice);
const mockSave = vi.mocked(branchesApi.savePlayPoint);
const mockLoad = vi.mocked(branchesApi.loadPlayPoint);
const mockEnd = vi.mocked(branchesApi.endPlaySession);
const mockHistory = vi.mocked(branchesApi.fetchPlaythrough);
const mockDynamic = vi.mocked(branchesApi.dynamicContinueScene);

const BRANCHES: BranchResponse[] = [
  { id: 1, book_id: 1, name: "メイン", parent_id: null, fork_ep_num: 0, created_at: null },
  { id: 2, book_id: 1, name: "IF 分岐A", parent_id: 1, fork_ep_num: 3, created_at: null },
];

const SESSION: BranchPlaySessionResponse = {
  session_id: "22222222-2222-2222-2222-222222222222",
  book_id: 1,
  branch_id: 1,
  current_node_id: "node_1",
  status: "active",
  updated_at: "2026-11-23T00:00:00Z",
};

const STATE_A: BranchPlayStateResponse = {
  session_id: SESSION.session_id,
  book_id: 1,
  branch_id: 1,
  current_node: {
    id: "node_1",
    episode_num: 1,
    content: "目覚めのシーン。ここが分岐点だ。",
    branch_type: "choice",
    choices: [
      { id: "c1", text: "剣を取る", conditions: [], target_node_id: "node_2", effects: {}, priority: 0 },
      { id: "c2", text: "逃げる", conditions: [], target_node_id: "node_3", effects: {}, priority: 0 },
    ],
  },
  current_node_id: "node_1",
  context: {},
  available_choices: [
    { id: "c1", text: "剣を取る", conditions: [], target_node_id: "node_2", effects: {}, priority: 0 },
    { id: "c2", text: "逃げる", conditions: [], target_node_id: "node_3", effects: {}, priority: 0 },
  ],
  save_points_count: 0,
  status: "active",
  updated_at: "2026-11-23T00:00:00Z",
};

const STATE_B: BranchPlayStateResponse = {
  ...STATE_A,
  current_node_id: "node_2",
  current_node: {
    id: "node_2",
    episode_num: 2,
    content: "剣を取った。道は二つに分かれる。",
    branch_type: "merge",
    choices: [],
  },
  available_choices: [],
  save_points_count: 1,
};

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function renderAt(entry: string) {
  const router = createMemoryRouter(routes, { initialEntries: [entry] });
  return render(
    <QueryClientProvider client={makeQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("PlayModePage", () => {
  it("/app/play で書籍ピッカーが表示される", async () => {
    renderAt("/app/play");
    expect(screen.getByTestId("play-mode-page")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("play-book-1")).toBeInTheDocument();
    });
    expect(screen.getByText("テスト小説")).toBeInTheDocument();
  });

  it("/app/play/:bookId では分岐選択とプレイ開始 UI が表示される", async () => {
    // 注意: この環境(Node 26 × react-router)ではテスト内ナビゲーションが
    // undici の AbortSignal クロスレルム問題で壊れるため、遷移を挟まず
    // 対象ルートを直接レンダリングして検証する(routes.test.tsx の家訓)。
    mockFetchBranches.mockResolvedValue(BRANCHES);
    renderAt("/app/play/1");

    await waitFor(() => {
      expect(screen.getByTestId("play-branch-select")).toBeInTheDocument();
    });
    // 既定で最初の分岐が選択されている
    expect(screen.getByTestId("play-branch-select")).toHaveDisplayValue("メイン");
    expect(screen.getByTestId("play-start-btn")).toBeEnabled();
  });

  it("分岐を選んでプレイを開始し、シーンと選択肢が表示される", async () => {
    mockFetchBranches.mockResolvedValue(BRANCHES);
    mockStart.mockResolvedValue(SESSION);
    mockState.mockResolvedValue(STATE_A);

    const user = userEvent.setup();
    renderAt("/app/play/1");

    await waitFor(() => {
      expect(screen.getByTestId("play-branch-select")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("play-start-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("play-scene-content")).toHaveTextContent("目覚めのシーン");
    });
    expect(mockStart).toHaveBeenCalledWith({ book_id: 1, branch_id: 1 });
    expect(screen.getByTestId("play-choice-c1")).toHaveTextContent("剣を取る");
    expect(screen.getByTestId("play-choice-c2")).toHaveTextContent("逃げる");
  });

  it("選択肢を押すと次のシーンへ遷移する", async () => {
    mockFetchBranches.mockResolvedValue(BRANCHES);
    mockStart.mockResolvedValue(SESSION);
    mockState.mockResolvedValue(STATE_A);
    mockChoose.mockResolvedValue(STATE_B);

    const user = userEvent.setup();
    renderAt("/app/play/1");
    await user.click(await screen.findByTestId("play-start-btn"));
    await user.click(await screen.findByTestId("play-choice-c1"));

    await waitFor(() => {
      expect(screen.getByTestId("play-scene-content")).toHaveTextContent("剣を取った");
    });
    expect(mockChoose).toHaveBeenCalledWith(SESSION.session_id, "c1");
    // 選択肢が無いノードでは終端メッセージが出る
    expect(screen.getByText(/この先の選択肢はありません/)).toBeInTheDocument();
  });

  it("dynamic_available=true のとき動的継続 UI が表示される (PLAN_P1 TRACK-P)", async () => {
    mockFetchBranches.mockResolvedValue(BRANCHES);
    mockStart.mockResolvedValue(SESSION);
    // flag ON 相当: サーバが dynamic_available=true を返す
    mockState.mockResolvedValue({ ...STATE_A, dynamic_available: true, dynamic_count: 0 });
    mockDynamic.mockResolvedValue({
      scene: {
        session_id: SESSION.session_id,
        node_id: "dyn_1",
        text: "夜風の中、彼は剣を抜いた。",
        choices: [{ id: "dyn_1", text: "前へ進む", kind: "dynamic" }],
        dynamic_count: 1,
      },
      state: { ...STATE_A, dynamic_available: true, dynamic_count: 1 },
    });

    const user = userEvent.setup();
    renderAt("/app/play/1");
    await user.click(await screen.findByTestId("play-start-btn"));

    const btn = await screen.findByTestId("play-dynamic-btn");
    expect(btn).toBeInTheDocument();
    await user.type(screen.getByTestId("play-dynamic-input"), "前へ進む");
    await user.click(btn);
    await waitFor(() => {
      expect(mockDynamic).toHaveBeenCalledWith(SESSION.session_id, "前へ進む");
    });
  });

  it("dynamic_available=false（flag OFF）では動的継続 UI を表示しない", async () => {
    mockFetchBranches.mockResolvedValue(BRANCHES);
    mockStart.mockResolvedValue(SESSION);
    mockState.mockResolvedValue(STATE_A); // dynamic_available なし = flag OFF

    const user = userEvent.setup();
    renderAt("/app/play/1");
    await user.click(await screen.findByTestId("play-start-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("play-scene-content")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("play-dynamic-btn")).not.toBeInTheDocument();
  });

  it("セーブ→ロードが UI から行える", async () => {
    mockFetchBranches.mockResolvedValue(BRANCHES);
    mockStart.mockResolvedValue(SESSION);
    mockState.mockResolvedValue(STATE_A);
    mockSave.mockResolvedValue({ ...STATE_A, save_points_count: 1 });
    mockLoad.mockResolvedValue(STATE_A);

    const user = userEvent.setup();
    renderAt("/app/play/1");
    await user.click(await screen.findByTestId("play-start-btn"));

    const saveBtn = await screen.findByTestId("play-save-btn");
    await user.click(saveBtn);
    await waitFor(() => {
      expect(screen.getByTestId("play-save-count")).toHaveTextContent("1 件");
    });

    const loadBtn = screen.getByTestId("play-load-btn");
    await user.click(loadBtn);
    await waitFor(() => {
      expect(mockLoad).toHaveBeenCalledWith(SESSION.session_id, 0);
    });
  });

  it("プレイを終了すると終了画面になり、もう一度遊べる", async () => {
    mockFetchBranches.mockResolvedValue(BRANCHES);
    mockStart.mockResolvedValue(SESSION);
    mockState.mockResolvedValue(STATE_A);
    mockEnd.mockResolvedValue({ ...SESSION, status: "completed" });

    const user = userEvent.setup();
    renderAt("/app/play/1");
    await user.click(await screen.findByTestId("play-start-btn"));
    await user.click(await screen.findByTestId("play-end-btn"));

    await waitFor(() => {
      expect(screen.getByText("▶ プレイを終了しました")).toBeInTheDocument();
    });
    expect(screen.getByTestId("play-restart-btn")).toBeInTheDocument();
  });

  it("プレイスルー記録を表示できる", async () => {
    mockFetchBranches.mockResolvedValue(BRANCHES);
    mockStart.mockResolvedValue(SESSION);
    mockState.mockResolvedValue(STATE_A);
    mockHistory.mockResolvedValue({
      session_id: SESSION.session_id,
      book_id: 1,
      branch_id: 1,
      history: [{ node_id: "node_1", choice: "c1" }],
      flags: {},
      variables: {},
      final_ending: null,
      saved_at: "2026-11-23T00:00:00Z",
    });

    const user = userEvent.setup();
    renderAt("/app/play/1");
    await user.click(await screen.findByTestId("play-start-btn"));
    await user.click(await screen.findByTestId("play-history-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("play-playthrough")).toBeInTheDocument();
    });
    expect(screen.getByText(/選択履歴 1 件/)).toBeInTheDocument();
  });

  it("IF グラフ未生成の書籍では Studio へのガイダンスが出る(S10)", async () => {
    mockFetchBranches.mockResolvedValue(BRANCHES);
    mockStart.mockResolvedValue(SESSION);
    // グラフが空の状態(entry_node_id が無いセッション)
    mockState.mockResolvedValue({
      ...STATE_A,
      current_node: {},
      current_node_id: null,
      available_choices: [],
    });

    const user = userEvent.setup();
    renderAt("/app/play/1");
    await user.click(await screen.findByTestId("play-start-btn"));

    await waitFor(() => {
      expect(screen.getByText(/この作品はまだ分岐がありません/)).toBeInTheDocument();
    });
    expect(screen.getByTestId("play-guidance-studio-link")).toBeInTheDocument();
  });

  it("挿絵が存在する話ではシーン画像を表示する(Phase 3 Increment 1)", async () => {
    mockFetchBranches.mockResolvedValue(BRANCHES);
    mockStart.mockResolvedValue(SESSION);
    mockState.mockResolvedValue(STATE_A);
    mockFetchEpisodeIllustration.mockResolvedValue("/static/illustrations/ep2.png");

    const user = userEvent.setup();
    renderAt("/app/play/1");
    await user.click(await screen.findByTestId("play-start-btn"));

    const img = await screen.findByTestId("play-scene-image");
    expect(img).toHaveAttribute("src", "/static/illustrations/ep2.png");
    // 呼び出しは現在ノードの話数に対して行われる
    await waitFor(() => {
      expect(mockFetchEpisodeIllustration).toHaveBeenCalledWith(1, 1);
    });
  });

  it("挿絵が存在しない話では画像を表示せず本文のみでフォールバックする", async () => {
    mockFetchBranches.mockResolvedValue(BRANCHES);
    mockStart.mockResolvedValue(SESSION);
    mockState.mockResolvedValue(STATE_A);
    mockFetchEpisodeIllustration.mockResolvedValue(undefined);

    const user = userEvent.setup();
    renderAt("/app/play/1");
    await user.click(await screen.findByTestId("play-start-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("play-scene-content")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("play-scene-image")).not.toBeInTheDocument();
  });

  it("旧パス /play は 404 画面にならない(routes.test.tsx の家訓に従い、遷移先の詳細は手動 E2E に委ねる)", () => {
    // テスト環境では createMemoryRouter の <Navigate> 自動遷移が発火しないため、
    // 「route-error(404 画面)にならないこと」までを検証する。
    renderAt("/play");
    expect(screen.queryByTestId("route-error")).not.toBeInTheDocument();
  });
});
