import React from "react";
import GeneratePanel from "../components/GeneratePanel";
import ExportPanel from "../components/ExportPanel";
import { useModal } from "../context/ModalContext";

export interface EasyModePageProps {
  onMessage?: (msg: string) => void;
}

export function EasyModePage({ onMessage }: EasyModePageProps) {
  const { setShowTransitionOverlay } = useModal();

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
      <GeneratePanel onMessage={handleMessage} />
      <ExportPanel
        onExportMessage={handleMessage}
        onPromoteToStudio={handlePromoteToStudio}
      />
    </main>
  );
}

export default EasyModePage;
