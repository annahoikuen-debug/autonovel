import React from "react";
import { BrowserRouter, useRoutes, Navigate, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { NovelProvider } from "./context/NovelContext";
import { ModalProvider } from "./context/ModalContext";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { AppLayout } from "./components/layout/AppLayout";
import { GlobalModals } from "./components/modals/GlobalModals";
import { routes } from "./routes";

/**
 *  TanStack Query v5 のクライアント。
 *
 *  再レンダリングのたびに生成するとキャッシュが消えて無限再取得になるため、
 *  モジュールスコープで 1 つだけ生成して使い回す。
 *
 *  defaultOptions の意図:
 *  - staleTime 30 秒: 枝ツリーや差分は「編集中に見え続ける」もの。0 にすると
 *    タブ復帰・再レンダのたびに全クエリが再取得され、画面が飛ぶ。
 *  - retry 1: 一時的な 5xx は 1 回だけ再試行。認証・入力起因の 4xx は
 *    既定どおり再試行しない（TanStack は 4xx を失敗扱いにして再試行しない）。
 *  - refetchOnWindowFocus false: 執筆中はフォーカス復帰で本文が書き換わるのを防ぐ。
 *  - mutations は再試行しない: 生成は取り消すと副作用が出るため自動再試行は危険。
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
});

export function AppProviders({ children }: { children: React.ReactNode }) {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <QueryClientProvider client={queryClient}>
          <NovelProvider>
            <ModalProvider>{children}</ModalProvider>
          </NovelProvider>
        </QueryClientProvider>
      </AuthProvider>
    </ErrorBoundary>
  );
}

/**
 * ルート解決（単一の情報源）。
 *
 * ルート定義は {@link routes} に集約し、ここでは `useRoutes` に渡すだけにする。
 * 新しいページを追加するときは `routes.tsx` だけを編集すること。
 */
export function AppRoutes() {
  return <>{useRoutes(routes)}</>;
}

/**
 * 初回起動時のオンボーディング判定。
 *
 * ルート `/` は商業LP（認証不要）のため、オンボーディングゲートは適用しない。
 * /welcome は既存のオンボーディングページとして維持する。
 */
function OnboardingGate({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

/**
 * 認証必須ルートのガード。
 *
 * トークンが無い場合は `/login?next=<元のパス>` へ誘導する。
 * 認証 UI 自体のテストは AuthPage を直接レンダリングして行う。
 */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { token } = useAuth();
  const location = useLocation();

  if (token) {
    return <>{children}</>;
  }

  const next = encodeURIComponent(`${location.pathname}${location.search}`);
  return <Navigate to={`/login?next=${next}`} replace />;
}

function AppShell() {
  const location = useLocation();
  const isPublicRoute =
    location.pathname === "/login" ||
    location.pathname === "/register" ||
    location.pathname === "/" ||
    location.pathname === "/lp" ||
    location.pathname === "/welcome";

  if (isPublicRoute) {
    return <AppRoutes />;
  }

  return (
    <RequireAuth>
      <AppLayout>
        <AppRoutes />
      </AppLayout>
    </RequireAuth>
  );
}

export function App() {
  return (
    <AppProviders>
      <BrowserRouter>
        <OnboardingGate>
          <AppShell />
        </OnboardingGate>
        <GlobalModals />
      </BrowserRouter>
    </AppProviders>
  );
}

export default App;
