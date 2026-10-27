/**
 * 章ツリーのテストで共有する差し込み口。
 *
 * `apiFetch` を差し替えた上で本物の `NovelProvider` + `ChapterOutlineTree` を描画し、
 * 章一覧は context へ直接差し込む（既存 seed のまま Hydra で上書きされないようにする）。
 */
import React, { useLayoutEffect, useRef } from "react";
import { render } from "@testing-library/react";
import { vi, type Mock } from "vitest";
import { NovelProvider, useNovelContext } from "../../../src/context/NovelContext";
import { ChapterOutlineTree } from "../../../src/components/studio/ChapterOutlineTree";
import { ChapterItem } from "../../../src/types";

export type MessageHandler = (msg: string, type: "success" | "error" | "info") => void;

/** 章データを生成する（既定のタイトルは「第N話」接頭辞無し＝话数改写の観測用） */
export const makeChapter = (epNum: number, overrides: Partial<ChapterItem> = {}): ChapterItem => ({
  ep_num: epNum,
  title: `Sample ${epNum}`,
  summary: `Summary ${epNum}`,
  content: "",
  is_catharsis: false,
  status: "draft",
  ...overrides,
});

/** 章一覧を context へ差し込む */
const ChapterSeeder = ({ chapters }: { chapters: ChapterItem[] }) => {
  const { setChapters } = useNovelContext();
  const seeded = useRef(false);
  useLayoutEffect(() => {
    if (seeded.current) return;
    seeded.current = true;
    setChapters(chapters);
  }, [chapters, setChapters]);
  return null;
};

/** `onMessage` 收到的通知を画面へ出す（ユーザー起点の検証用） */
const MessageLog = ({ onMessage }: { onMessage: MessageHandler }) => {
  const counter = useRef(0);
  const [items, setItems] = React.useState<{ id: number; msg: string }[]>([]);
  return (
    <>
      <ul data-testid="message-log">
        {items.map((item) => (
          <li key={item.id} role="alert">
            {item.msg}
          </li>
        ))}
      </ul>
      <ChapterOutlineTree
        onMessage={(msg, type) => {
          counter.current += 1;
          const id = counter.current;
          onMessage(msg, type);
          setItems((prev) => [...prev, { id, msg }]);
        }}
      />
    </>
  );
};

/**
 * 章ツリーを描画する。
 *
 * `chapters` を渡すと context へ差し込む。省略した場合は
 * NovelContext の初期値（1 話）のまま＝Hydration の検証用。
 */
export const renderOutlineTree = (
  options: { chapters?: ChapterItem[]; onMessage?: Mock } = {},
): { onMessage: Mock } => {
  const onMessage = options.onMessage ?? vi.fn();
  render(
    <NovelProvider>
      {options.chapters ? <ChapterSeeder chapters={options.chapters} /> : null}
      <MessageLog onMessage={onMessage as MessageHandler} />
    </NovelProvider>,
  );
  return { onMessage };
};

/** `apiFetch` の呼び出しから `(endpoint, body)` を取り出す */
export const putCalls = (
  apiFetchMock: Mock,
): { endpoint: string; body: Record<string, unknown> }[] =>
  apiFetchMock.mock.calls
    .filter(([, options]) => options?.method === "PUT")
    .map(([endpoint, options]) => ({
      endpoint: String(endpoint),
      body: JSON.parse(String((options as RequestInit).body)) as Record<string, unknown>,
    }));

/** `apiFetch` の呼び出しから endpoint だけを抜き出す */
export const endpoints = (apiFetchMock: Mock, method?: string): string[] =>
  apiFetchMock.mock.calls
    .filter(([, options]) => !method || options?.method === method)
    .map(([endpoint]) => String(endpoint));

/** `ok: true` の Response を作る */
export const okResponse = (data: unknown = { saved: true }) =>
  ({ ok: true, status: 200, json: async () => data }) as unknown as Response;
