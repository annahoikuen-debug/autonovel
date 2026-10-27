// 注意: この環境（Node.js 24 + vitest 1.6）では vitest からの名前付き import が
// undefined になるため、globals: true 設定のグローバルAPI（describe/it/expect/vi）を使用する。
// 型定義だけは明示的に取り込む（実行時には何も読み込まない）。
/// <reference types="vitest/globals" />

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import App from "../../src/App";

/**
 * 3 つの入口の導線（切れていないこと）を担保する smoke test。
 *
 *   1. 入口選択（/welcome）→ かんたん執筆 → 出力
 *   2. 共創ウィザード（/wizard）→ Studio への引き継ぎ導線
 *   3. 既存作品を Studio で開いて編集
 */

const ONBOARDING_KEY = "autonovel.onboardingCompleted";

/** 実アプリ（App.tsx）と同じ構成で、指定ルートから起動する */
function renderAt(path: string) {
    window.history.pushState({}, "", path);
    return render(<App />);
}

describe("入口導線の smoke test", () => {
    beforeEach(() => {
        vi.restoreAllMocks();
        globalThis.fetch = vi.fn().mockResolvedValue({
            ok: true,
            status: 200,
            json: async () => ({}),
            body: null,
        } as unknown as Response) as unknown as typeof globalThis.fetch;
        // 初回起動の入口選択（/welcome リダイレクト）を無効化し、
        // 各ルートの実体を検証できるようにする
        window.localStorage.setItem(ONBOARDING_KEY, "1");
    });

    afterEach(() => {
        window.localStorage.clear();
        window.history.pushState({}, "", "/");
    });

    describe("パス1: 入口選択 → かんたん執筆 → 出力", () => {
        it("/welcome は 3 つの入口を提示し、選択するまで開始できない", () => {
            renderAt("/welcome");

            // 3 つの入口カードがすべて出ている
            expect(screen.getByTestId("welcome-entry-easy")).toBeInTheDocument();
            expect(screen.getByTestId("welcome-entry-wizard")).toBeInTheDocument();
            expect(screen.getByTestId("welcome-entry-studio")).toBeInTheDocument();

            // 未選択では開始できない
            const startBtn = screen.getByTestId("welcome-start-btn") as HTMLButtonElement;
            expect(startBtn.disabled).toBe(true);
        });

        it("入口を選ぶと開始できる", async () => {
            renderAt("/welcome");
            fireEvent.click(screen.getByTestId("welcome-entry-easy"));
            await waitFor(() => {
                expect(
                    (screen.getByTestId("welcome-start-btn") as HTMLButtonElement).disabled
                ).toBe(false);
            });
        });

        it("初回起動で / を開くと入口選択（/welcome）へ誘導される", async () => {
            window.localStorage.removeItem(ONBOARDING_KEY);
            renderAt("/");
            await waitFor(() => {
                expect(screen.getByTestId("welcome-page")).toBeInTheDocument();
            });
        });

        it("ヘッダーから 3 つの入口に到達できる", async () => {
            renderAt("/");
            // ヘッダーに 3 入口が揃っている
            expect(screen.getByTestId("btn-mode-easy")).toBeInTheDocument();
            expect(screen.getByTestId("btn-mode-wizard")).toBeInTheDocument();
            expect(screen.getByTestId("btn-mode-studio")).toBeInTheDocument();

            // ウィザードへ遷移できる
            fireEvent.click(screen.getByTestId("btn-mode-wizard"));
            await waitFor(() => {
                expect(screen.getByTestId("wizard-workflow-page")).toBeInTheDocument();
            });
        });
    });

    describe("パス2: 共創ウィザード → Studio への引き継ぎ", () => {
        it("ウィザードに進捗表示と出口 CTA が常にある", () => {
            renderAt("/wizard");

            // 進捗インジケータ（3 ステップ）が明示されている
            expect(screen.getByTestId("wizard-progress-step-1")).toBeInTheDocument();
            expect(screen.getByTestId("wizard-progress-step-2")).toBeInTheDocument();
            expect(screen.getByTestId("wizard-progress-step-3")).toBeInTheDocument();
            expect(screen.getByTestId("wizard-progress-count")).toHaveTextContent(
                "1 / 3 ステップ"
            );

            // 最終ステップへ進む出口が明示されている
            expect(screen.getByTestId("wizard-exit-studio-btn")).toBeInTheDocument();
            expect(screen.getByTestId("wizard-exit-easy-btn")).toBeInTheDocument();
        });

        it("ウィザードのモーダル二重表示はない", () => {
            renderAt("/wizard");
            // 旧来のモーダル版ウィザード（.wizard-workflow-overlay）は出ない
            expect(document.querySelector(".wizard-workflow-overlay")).toBeNull();
        });
    });

    describe("パス3: 既存作品を Studio で編集", () => {
        it("/studio が開き、タブが 3 グループに整理されている", () => {
            renderAt("/studio");

            expect(screen.getByTestId("studio-workspace")).toBeInTheDocument();
            expect(screen.getByTestId("studio-workspace-page")).toBeInTheDocument();

            // 3 グループ（執筆・点検・公開）
            expect(screen.getByTestId("tab-group-writing")).toBeInTheDocument();
            expect(screen.getByTestId("tab-group-review")).toBeInTheDocument();
            expect(screen.getByTestId("tab-group-publish")).toBeInTheDocument();

            // 既存タブの testid は維持されている（導線の切断防止）
            expect(screen.getByTestId("tab-studio-editor")).toBeInTheDocument();
            expect(screen.getByTestId("tab-studio-audit")).toBeInTheDocument();
            expect(screen.getByTestId("tab-studio-multimedia")).toBeInTheDocument();
            expect(screen.getByTestId("tab-studio-commercial")).toBeInTheDocument();
        });
    });
});
