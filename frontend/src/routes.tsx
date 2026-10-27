import React from "react";
import { RouteObject, isRouteErrorResponse, useNavigate, useRouteError } from "react-router-dom";
import { EasyModePage } from "./pages/EasyModePage";
import { StudioWorkspacePage } from "./pages/StudioWorkspacePage";
import { WizardWorkflowPage } from "./pages/WizardWorkflowPage";
import { WelcomePage } from "./pages/WelcomePage";

/**
 * ルート単位のエラー表示（react-router v7 の `errorElement`）。
 *
 * loader / レンダリング中に投げられたエラーの受け皿。スタックトレースは出さず、
 * 「前の画面に戻る」と「再読み込み」の 2 手段だけを提供する。
 * 絶対に出典（URL・localStorage 等）を載せない。
 */
export function RouteErrorView() {
  const error = useRouteError();
  const navigate = useNavigate();

  let message = "ページを表示できませんでした。";
  if (isRouteErrorResponse(error)) {
    message =
      error.status === 404
        ? "ページが見つかりませんでした。"
        : `読み込みに失敗しました（HTTP ${error.status}）。`;
  }

  return (
    <div
      role="alert"
      data-testid="route-error"
      style={{
        minHeight: "60vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "12px",
        padding: "32px",
      }}
    >
      <h2 style={{ margin: 0, fontSize: "1.25rem" }}>{message}</h2>
      <div style={{ display: "flex", gap: "8px" }}>
        <button type="button" onClick={() => navigate(-1)} data-testid="route-error-back">
          前の画面に戻る
        </button>
        <button type="button" onClick={() => window.location.reload()} data-testid="route-error-reload">
          再読み込み
        </button>
      </div>
    </div>
  );
}

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
  { path: "/", element: <EasyModePage />, errorElement: <RouteErrorView /> },
  { path: "/studio", element: <StudioWorkspacePage />, errorElement: <RouteErrorView /> },
  { path: "/studio/:bookId", element: <StudioWorkspacePage />, errorElement: <RouteErrorView /> },
  { path: "/wizard", element: <WizardWorkflowPage />, errorElement: <RouteErrorView /> },
  { path: "/welcome", element: <WelcomePage />, errorElement: <RouteErrorView /> },
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
