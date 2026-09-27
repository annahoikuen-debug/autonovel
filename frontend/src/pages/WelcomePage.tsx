import React, { useCallback, useState } from "react";

/**
 * 初回起動時の入口選択（オンボーディング）。
 *
 * 「目的」「所要ステップ」「おすすめ」で 3 つの入口を対比させ、
 * 小説を書く初心者が「どれを選べばよいか」を迷わないようにする。
 * 選んだ的作品は localStorage に記録し、二度と自動で表示しない。
 */

type EntryId = "easy" | "wizard" | "studio";

interface EntryPoint {
    id: EntryId;
    path: string;
    emoji: string;
    title: string;
    audience: string;
    description: string;
    steps: string;
    recommended: boolean;
    badge?: string;
    testId: string;
}

const ENTRIES: EntryPoint[] = [
    {
        id: "easy",
        path: "/",
        emoji: "⚡",
        title: "かんたん執筆",
        audience: "はじめて書きたい人に",
        description:
            "書きたい内容をそのまま入力するだけで AI が本文をつくります。操作は「書く」「出す」の 2 つだけです。",
        steps: "手順 2 つ（約 1 分）",
        recommended: true,
        badge: "おすすめ",
        testId: "welcome-entry-easy",
    },
    {
        id: "wizard",
        path: "/wizard",
        emoji: "✨",
        title: "共創ウィザード",
        audience: "物語の骨組みから作りたい人へ",
        description:
            "AI からいただいた骨組みを読みながら、場面ごとの筋道の直し方を決めていきます。方針決定から執筆まで 1 ステップずつ進められます。",
        steps: "手順 3 つ（方針 → 構成 → 執筆）",
        recommended: false,
        testId: "welcome-entry-wizard",
    },
    {
        id: "studio",
        path: "/studio",
        emoji: "🚀",
        title: "Studio",
        audience: "仕上げや設定を担う人向け",
        description:
            "書き上げた原稿を細かいところまで調整します。矛盾の探し方や設定変更、挿絵や効果音の生成もここで扱えます。",
        steps: "既存作品からすぐ開けます",
        recommended: false,
        testId: "welcome-entry-studio",
    },
];

const STORAGE_KEY = "autonovel.onboardingCompleted";

/** オンボーディングをすでに完了したかどうか（テストからも参照） */
export function isOnboardingCompleted(): boolean {
    if (typeof window === "undefined") return true;
    try {
        return window.localStorage.getItem(STORAGE_KEY) === "1";
    } catch {
        return true;
    }
}

/** オンボーディング完了を記録する */
export function markOnboardingCompleted(): void {
    if (typeof window === "undefined") return;
    try {
        window.localStorage.setItem(STORAGE_KEY, "1");
    } catch {
        // localStorage が使えない環境では毎回表示されるが致命的ではない
    }
}

export interface WelcomePageProps {
    /** 「あとで決める」で使う代替遷移（既定は "/"） */
    onSkip?: () => void;
    /**
     * 別ページへ移るための関数。
     * 既定は window.location による遷移で、Router なしでも動く（単体テスト対応）。
     */
    onNavigate?: (path: string) => void;
}

export function WelcomePage({ onSkip, onNavigate }: WelcomePageProps) {
    // Router が必要にならないよう、既定は通常のページ遷移を使う。
    const navigate = useCallback(
        (path: string) => {
            if (onNavigate) onNavigate(path);
            else if (typeof window !== "undefined") window.location.assign(path);
        },
        [onNavigate]
    );
    const [selected, setSelected] = useState<EntryId | null>(null);

    const start = (path: string) => {
        markOnboardingCompleted();
        navigate(path);
    };

    const handleSkip = () => {
        markOnboardingCompleted();
        if (onSkip) onSkip();
        else navigate("/");
    };

    const selectedEntry = ENTRIES.find((e) => e.id === selected);

    return (
        <main className="welcome-page" data-testid="welcome-page">
            <section className="welcome-hero">
                <p className="welcome-hero__eyebrow">ようこそ</p>
                <h1 className="welcome-hero__title">どれから書き始めますか？</h1>
                <p className="welcome-hero__lead">
                    AutoNovel には入口が 3 つあります。どれも同じ作品に書き足していくので、あとから
                    別の入口へ移っても内容は失われません。
                    <br />
                    <strong>はじめやすい入口</strong>を選んでください。
                </p>
            </section>

            <section className="welcome-entries">
                {ENTRIES.map((entry) => {
                    const isSelected = selected === entry.id;
                    return (
                        <button
                            key={entry.id}
                            type="button"
                            className={`welcome-entry ${isSelected ? "welcome-entry--selected" : ""}`}
                            data-testid={entry.testId}
                            aria-pressed={isSelected}
                            onClick={() => setSelected(entry.id)}
                        >
                            <span className="welcome-entry__head">
                                <span className="welcome-entry__emoji" aria-hidden>
                                    {entry.emoji}
                                </span>
                                <span className="welcome-entry__heading">
                                    <span className="welcome-entry__title">{entry.title}</span>
                                    <span className="welcome-entry__audience">{entry.audience}</span>
                                </span>
                                {entry.badge && <span className="welcome-entry__badge">{entry.badge}</span>}
                            </span>

                            <span className="welcome-entry__desc">{entry.description}</span>

                            <span className="welcome-entry__steps">
                                <span aria-hidden>🗓</span>
                                {entry.steps}
                            </span>
                        </button>
                    );
                })}
            </section>

            <section className="welcome-actions">
                <button
                    type="button"
                    className={`welcome-cta ${selected ? "" : "welcome-cta--disabled"}`}
                    data-testid="welcome-start-btn"
                    disabled={!selected}
                    onClick={() => {
                        if (selectedEntry) start(selectedEntry.path);
                    }}
                >
                    {selectedEntry
                        ? `${selectedEntry.title}をはじめる →`
                        : "入口を選んでください"}
                </button>

                <button
                    type="button"
                    className="welcome-secondary"
                    data-testid="welcome-skip-btn"
                    onClick={handleSkip}
                >
                    あとで決める（かんたん執筆へ）
                </button>
            </section>

            <p className="welcome-footnote">
                どれを選んでも、書いた内容は同じ作品にたまります。あとから「もう少し細かく編集したい」と思ったら
                Studio へそのまま引き継げます。
            </p>
        </main>
    );
}

export default WelcomePage;
