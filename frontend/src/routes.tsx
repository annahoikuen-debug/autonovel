import React from "react";
import {
  RouteObject,
  isRouteErrorResponse,
  useNavigate,
  useRouteError,
  Navigate,
} from "react-router-dom";
import { EasyModePage } from "./pages/EasyModePage";
import { StudioWorkspacePage } from "./pages/StudioWorkspacePage";
import { WizardWorkflowPage } from "./pages/WizardWorkflowPage";
import { WelcomePage } from "./pages/WelcomePage";
import { LoginPage, RegisterPage } from "./pages/AuthPage";
import { LpPage } from "./pages/lp/LpPage";

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
 * 公開 LP:
 *   - `/`        ランディングページ（商業LP、認証不要）
 *   - `/lp`      LP エイリアス（`/` へリダイレクト）
 *
 * 既存アプリ（認証必須）は /app 配下に移行:
 *   - `/app/easy`        かんたん執筆（Easy Mode）
 *   - `/app/wizard`      共創ウィザード（3 ステップ）
 *   - `/app/studio`      Studio（上級者向け）
 *   - `/app/studio/:bookId` Studio（作品指定）
 * ＋ 初回起動時の入口選択 `/welcome`
 * ＋ 認証 `/login` `/register`（未ログイン時はここへ誘導される）
 */
export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage />, errorElement: <RouteErrorView /> },
  { path: "/register", element: <RegisterPage />, errorElement: <RouteErrorView /> },
  { path: "/", element: <LpPage />, errorElement: <RouteErrorView /> },
  { path: "/lp", element: <Navigate to="/" replace /> },
  { path: "/app/easy", element: <EasyModePage />, errorElement: <RouteErrorView /> },
  { path: "/app/wizard", element: <WizardWorkflowPage />, errorElement: <RouteErrorView /> },
  { path: "/app/studio", element: <StudioWorkspacePage />, errorElement: <RouteErrorView /> },
  { path: "/app/studio/:bookId", element: <StudioWorkspacePage />, errorElement: <RouteErrorView /> },
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
    path: "/app/easy",
    matchPrefix: "/app/easy",
    emoji: "⚡",
    label: "かんたん",
    description: "書きたい内容を入れるだけ",
    testId: "nav-entry-easy",
  },
  {
    id: "wizard",
    path: "/app/wizard",
    matchPrefix: "/app/wizard",
    emoji: "✨",
    label: "共創ウィザード",
    description: "骨組みを決めてから書く",
    testId: "nav-entry-wizard",
  },
  {
    id: "studio",
    path: "/app/studio",
    matchPrefix: "/app/studio",
    emoji: "🚀",
    label: "Studio",
    description: "仕上げと詳細設定",
    testId: "nav-entry-studio",
  },
];

export default routes;
