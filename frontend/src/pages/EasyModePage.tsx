import React, { useCallback, useEffect, useState } from "react";
import GeneratePanel from "../components/GeneratePanel";
import ExportPanel from "../components/ExportPanel";
import { useModal } from "../context/ModalContext";
import { SubmissionChecklist } from "../components/publishing/SubmissionChecklist";

export interface EasyModePageProps {
  onMessage?: (msg: string) => void;
}

export function EasyModePage({ onMessage }: EasyModePageProps) {
  const { setShowTransitionOverlay } = useModal();
  const [kakuyomuMode, setKakuyomuMode] = useState<boolean>(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    setKakuyomuMode(params.get("kakuyomuMode") === "1");
  }, []);

  const handleMessage = (msg: string) => {
    onMessage?.(msg);
  };

  /**
   * Easy→Studio の移行は 1 本の導線に集約する。
   *
   * 以前は「昇格後に直接 /studio へ飛ぶ」か「移行オーバーレイを出す」の
   * 2 通りがあり、初心者が迷う原因になっていた。いまは常に
   * 移行オーバーレイ（何ができるようになるかの説明）→ /studio の順で進む。
   */
  const handlePromoteToStudio = () => {
    setShowTransitionOverlay(true);
  };

  return (
    <main className="main-grid" data-testid="easy-mode-page">
      {kakuyomuMode && (
        <section className="kakuyomu-guide" style={{ marginBottom: "16px", padding: "12px", background: "rgba(6, 182, 212, 0.1)", borderRadius: "12px", border: "1px solid rgba(6, 182, 212, 0.3)" }}>
          <h3 style={{ fontSize: "0.9rem", fontWeight: 700, color: "var(--accent-cyan, #06b6d4)", margin: "0 0 8px 0" }}>
            🏆 カクヨムランキング上位を狙うモード
          </h3>
          <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", margin: "0 0 12px 0" }}>
            ジャンル・タグ・タイトル構文を自動推奨。毎日同じ時間に更新し、投稿チェックリストで投稿準備を整えましょう。
          </p>
          <SubmissionChecklist platformName="カクヨム" publisherUrl="https://kakuyomu.jp/my/works" />
        </section>
      )}
      <GeneratePanel onMessage={handleMessage} />
      <ExportPanel
        onExportMessage={handleMessage}
        onPromoteToStudio={handlePromoteToStudio}
      />
    </main>
  );
}

export default EasyModePage;
