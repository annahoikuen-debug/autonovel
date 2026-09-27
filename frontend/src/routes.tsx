import React from "react";
import { RouteObject } from "react-router-dom";
import { EasyModePage } from "./pages/EasyModePage";
import { StudioWorkspacePage } from "./pages/StudioWorkspacePage";
import { WizardWorkflowPage } from "./pages/WizardWorkflowPage";
import { WelcomePage } from "./pages/WelcomePage";

/**
 * ルーティングの単一の情報源。
 *
 * すべてのルート定義はここに集約し、App.tsx は {@link useRoutes} を通じて
 * この配列だけを参照する。ルートを追加・変更するときはここだけを編集すること。
 *
 * 3 つの入口:
 *   - `/`        かんたん執筆（Easy Mode）
 *   - `/wizard`  共創ウィザード（3 ステップ）
 *   - `/studio`  Studio（上級者向け）
 * ＋ 初回起動時の入口選択 `/welcome`
 */
export const routes: RouteObject[] = [
  { path: "/", element: <EasyModePage /> },
  { path: "/studio", element: <StudioWorkspacePage /> },
  { path: "/studio/:bookId", element: <StudioWorkspacePage /> },
  { path: "/wizard", element: <WizardWorkflowPage /> },
  { path: "/welcome", element: <WelcomePage /> },
];

/** 3 つの入口のメタデータ（ヘッダーナビゲーションの導線定義と共有） */
export interface EntryMeta {
  id: "easy" | "wizard" | "studio";
  path: string;
  /** 現在地判定用の前方一致プレフィックス */
  matchPrefix: string;
  emoji: string;
  label: string;
  /** 非技術者に渡す 1 行の説明 */
  description: string;
  testId: string;
}

export const ENTRY_POINTS: EntryMeta[] = [
  {
    id: "easy",
    path: "/",
    matchPrefix: "/",
    emoji: "⚡",
    label: "かんたん",
    description: "書きたい内容を入れるだけ",
    testId: "nav-entry-easy",
  },
  {
    id: "wizard",
    path: "/wizard",
    matchPrefix: "/wizard",
    emoji: "✨",
    label: "共創ウィザード",
    description: "骨組みを決めてから書く",
    testId: "nav-entry-wizard",
  },
  {
    id: "studio",
    path: "/studio",
    matchPrefix: "/studio",
    emoji: "🚀",
    label: "Studio",
    description: "仕上げと詳細設定",
    testId: "nav-entry-studio",
  },
];

export default routes;
