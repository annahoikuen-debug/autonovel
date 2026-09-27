import React from "react";
import { BrowserRouter, useRoutes, Navigate, useLocation } from "react-router-dom";
import { NovelProvider } from "./context/NovelContext";
import { ModalProvider } from "./context/ModalContext";
import { AppLayout } from "./components/layout/AppLayout";
import { GlobalModals } from "./components/modals/GlobalModals";
import { routes } from "./routes";
import { isOnboardingCompleted } from "./pages/WelcomePage";

export function AppProviders({ children }: { children: React.ReactNode }) {
  return (
    <NovelProvider>
      <ModalProvider>{children}</ModalProvider>
    </NovelProvider>
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
 * ルート `/` への着地時に、まだ入口を選んでいなければ `/welcome` へ誘導する。
 * 入口を選んだら localStorage に記録されるので、以降はそのまま着地する。
 */
function OnboardingGate({ children }: { children: React.ReactNode }) {
  const location = useLocation();

  if (location.pathname === "/" && !isOnboardingCompleted()) {
    return <Navigate to="/welcome" replace />;
  }

  return <>{children}</>;
}

export function App() {
  return (
    <AppProviders>
      <BrowserRouter>
        <OnboardingGate>
          <AppLayout>
            <AppRoutes />
          </AppLayout>
        </OnboardingGate>
        <GlobalModals />
      </BrowserRouter>
    </AppProviders>
  );
}

export default App;
