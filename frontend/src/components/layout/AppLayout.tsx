import React, { useState } from "react";
import { useLocation, useNavigate, Outlet } from "react-router-dom";
import { useNovelContext } from "../../context/NovelContext";
import { useModal } from "../../context/ModalContext";
import { useAppTheme, AppTheme } from "../../hooks/useAppTheme";
import { useToast } from "../../hooks/useToast";
import { ToastContainer } from "../common/ToastContainer";
import { Button } from "../common/Button";
import { BookSelector } from "../common/BookSelector";
import { getGenreBadgeConfig } from "../../constants/genres";
import { MobileBottomNav } from "../mobile/MobileBottomNav";
import { MobileChapterDrawer } from "../mobile/MobileChapterDrawer";
import { MobileQuickActionBar } from "../mobile/MobileQuickActionBar";
import { ENTRY_POINTS, EntryMeta } from "../../routes";

export interface AppLayoutProps {
  children?: React.ReactNode;
  onMessage?: (msg: string) => void;
}

export function AppLayout({ children, onMessage }: AppLayoutProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const {
    books,
    selectedBook,
    setSelectedBookId,
    refreshBooks,
    hasCompletedWizard,
    setWizardStep,
    setIsWizardActive,
    chapters,
    currentEpNum,
    setCurrentEpNum,
  } = useNovelContext();

  const {
    openModal,
    setShowConfig,
    setShowMedia,
    setShowGraph,
    isChapterDrawerOpen,
    setIsChapterDrawerOpen,
  } = useModal();

  const { theme, setTheme } = useAppTheme();
  const { toasts, addToast, removeToast } = useToast();
  const [mobileTab, setMobileTab] = useState<"books" | "plots" | "writing" | "settings">("writing");

  const isStudio = location.pathname.startsWith("/studio");
  const isWelcome = location.pathname.startsWith("/welcome");

  /** 現在のルートに対応する入口（最長プレフィックス一致）を返す */
  const activeEntry: EntryMeta | null = ENTRY_POINTS.filter((e) =>
    location.pathname.startsWith(e.matchPrefix)
  ).sort((a, b) => b.matchPrefix.length - a.matchPrefix.length)[0] ?? null;

  React.useEffect(() => {
    refreshBooks();
  }, [refreshBooks]);

  const handleMessage = (msg: string) => {
    if (!msg) return;
    if (msg.startsWith("❌")) {
      addToast(msg.replace(/^❌\s*/u, ""), "error");
    } else if (msg.startsWith("✨") || msg.startsWith("📦")) {
      addToast(msg.replace(/^[✨📦]\s*/u, ""), "success");
    } else {
      addToast(msg, "info");
    }
    onMessage?.(msg);
  };

  return (
    <div
      className={isStudio ? "container-fluid" : "container"}
      style={isStudio ? { maxWidth: "1500px", margin: "0 auto" } : undefined}
    >
      <ToastContainer toasts={toasts} onClose={removeToast} />
      <header className="header">
        <div style={{ display: "flex", alignItems: "center", gap: "16px", flex: 1 }}>
          <div>
            <h1 className="brand-title" onClick={() => navigate("/welcome")} style={{ cursor: "pointer" }}>
              AutoNovel
            </h1>
            <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", marginTop: "4px" }}>
              {isWelcome
                ? "どの入口から始めるか選んでください"
                : activeEntry
                  ? `${activeEntry.label} — ${activeEntry.description}`
                  : "AI 執筆・設定管理・矛盾診断・マルチメディア生成スタジオ"}
            </p>
          </div>
          <BookSelector
            currentBook={selectedBook}
            books={books}
            onSelectBook={(book) => setSelectedBookId(book.id)}
            onCreateBook={async (payload) => {
              const { createBook } = await import("../../api/books");
              const newBook = await createBook(payload);
              await refreshBooks();
              setSelectedBookId(newBook.id);

              if (!hasCompletedWizard) {
                setWizardStep(1);
                setIsWizardActive(true);
              }
            }}
          />
        </div>

        <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          {/* 3 つの入口（かんたん／共創ウィザード／Studio）＋現在地ハイライト */}
          <nav className="entry-nav" aria-label="入口ナビゲーション" data-testid="mode-switcher">
            {ENTRY_POINTS.map((entry) => {
              const isActive = activeEntry?.id === entry.id;
              return (
                <button
                  key={entry.id}
                  type="button"
                  className={`entry-nav__item ${isActive ? "entry-nav__item--active" : ""}`}
                  onClick={() => navigate(entry.path)}
                  data-testid={
                    entry.id === "easy"
                      ? "btn-mode-easy"
                      : entry.id === "studio"
                        ? "btn-mode-studio"
                        : "btn-mode-wizard"
                  }
                  aria-current={isActive ? "page" : undefined}
                  title={`${entry.label} — ${entry.description}`}
                >
                  <span className="entry-nav__icon" aria-hidden>
                    {entry.emoji}
                  </span>
                  <span className="entry-nav__text">
                    <span className="entry-nav__label">{entry.label}</span>
                    <span className="entry-nav__desc">{entry.description}</span>
                  </span>
                </button>
              );
            })}
          </nav>

          {/* テーマ切替セレクター */}
          <select
            className="select theme-selector"
            value={theme}
            onChange={(e) => setTheme(e.target.value as AppTheme)}
            aria-label="テーマを選択"
            data-testid="theme-selector"
            style={{ width: "auto", padding: "6px 10px", fontSize: "0.85rem" }}
          >
            <option value="dark">🌙 ダーク</option>
            <option value="light">☀️ ライト</option>
            <option value="sepia">📜 セピア</option>
          </select>

          <Button
            variant="accent-yellow"
            size="sm"
            onClick={() => setShowConfig(true)}
            data-testid="open-config-btn"
          >
            ⚙️ LLM設定
          </Button>

          <Button
            variant="accent-cyan"
            size="sm"
            onClick={() => setShowMedia(true)}
            data-testid="open-media-btn"
          >
            📦 アセットパック
          </Button>

          <Button
            variant="accent-purple"
            size="sm"
            onClick={() => setShowGraph(true)}
            data-testid="open-graph-btn"
          >
            📊 相関図
          </Button>

          {(() => {
            const c = getGenreBadgeConfig(selectedBook?.genre || "ハイファンタジー (R15)");
            return (
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "4px 12px",
                  borderRadius: "9999px",
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  backgroundColor: c.bg,
                  color: c.text,
                  border: `1px solid ${c.border}`,
                }}
              >
                <span>{c.emoji}</span>
                <span>{selectedBook?.genre || "ハイファンタジー (R15)"}</span>
              </span>
            );
          })()}
        </div>
      </header>

      {/* Main page content via Outlet or children */}
      {children || <Outlet />}

      {/* Mobile Navigation */}
      <MobileQuickActionBar
        onInsertText={(txt) => {
          handleMessage(`テキストに「${txt}」を挿入しました`);
        }}
        onAiContinue={() => handleMessage("AI続きの執筆を開始します...")}
        onProofread={() => handleMessage("文章の校正を実行中...")}
      />

      <MobileChapterDrawer
        isOpen={isChapterDrawerOpen}
        onClose={() => setIsChapterDrawerOpen(false)}
        chapters={chapters || []}
        currentChapterId={currentEpNum}
        onSelectChapter={(epNum) => {
          setCurrentEpNum(epNum);
          handleMessage(`第 ${epNum} 話を選択しました`);
        }}
      />

      <MobileBottomNav
        activeTab={mobileTab}
        onTabChange={(tab) => {
          setMobileTab(tab);
          if (tab === "books") {
            openModal("bookshelf");
          } else if (tab === "plots") {
            setShowGraph(true);
          } else if (tab === "writing") {
            setIsChapterDrawerOpen(true);
          } else if (tab === "settings") {
            setShowConfig(true);
          }
        }}
      />
    </div>
  );
}

export default AppLayout;
