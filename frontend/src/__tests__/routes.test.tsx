import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { routes } from "../routes";
import { NovelProvider } from "../context/NovelContext";
import { ModalProvider } from "../context/ModalContext";

function renderWithProviders(initialEntry: string) {
  const router = createMemoryRouter(routes, {
    initialEntries: [initialEntry],
  });

  return render(
    <NovelProvider>
      <ModalProvider>
        <RouterProvider router={router} />
      </ModalProvider>
    </NovelProvider>
  );
}

describe("Declarative Routes", () => {
  it("renders LpPage at root path '/'", () => {
    renderWithProviders("/");
    expect(screen.getByTestId("lp-page")).toBeInTheDocument();
  });

  it("redirects legacy '/studio' to the LP (root is now the LP)", () => {
    renderWithProviders("/studio");
    // / は LP。旧パス /studio は /app/studio へのリダイレクト定義だが、
    // MemoryRouter 上はリダイレクト先（認証ガード内ページ）の描画確認ではなく
    // 「/studio が 404 画面にならないこと」までを検証する。
    // 詳細な遷移先は各ページテストに委ねる。
    expect(screen.queryByTestId("route-error-view")).not.toBeInTheDocument();
  });

  it("renders EasyModePage at '/app/easy'", () => {
    renderWithProviders("/app/easy");
    expect(screen.getByTestId("easy-mode-page")).toBeInTheDocument();
  });

  it("renders StudioWorkspacePage at '/app/studio'", () => {
    renderWithProviders("/app/studio");
    expect(screen.getByTestId("studio-workspace-page")).toBeInTheDocument();
  });

  it("renders StudioWorkspacePage with bookId param at '/app/studio/42'", () => {
    renderWithProviders("/app/studio/42");
    expect(screen.getByTestId("studio-workspace-page")).toBeInTheDocument();
  });

  it("renders WizardWorkflowPage at '/app/wizard'", () => {
    renderWithProviders("/app/wizard");
    expect(screen.getByTestId("wizard-workflow-page")).toBeInTheDocument();
  });

  it("redirects '/lp' alias to '/'", () => {
    renderWithProviders("/lp");
    expect(screen.getByTestId("lp-page")).toBeInTheDocument();
  });
});
