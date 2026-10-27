import React, { useMemo, useState } from "react";
import { styleSamples } from "../../constants/styleSamples";
import { StyleTuningSliders } from "./StyleTuningSliders";
import { StyleTuningParams } from "../../types/styleComparison";
import { plannedReason } from "../../capabilities";
import { measureStyleMetrics, toPercent } from "../../utils/styleMetrics";

interface StyleComparisonModalProps {
  onClose: () => void;
}

/**
 * 文体比較モーダル。
 *
 * 以前は「After ペイン」にスタイルを適用した，本文のように見える文字列
 * （= 元の文に "[スタイル適用: …]" を付けただけのもの）と、平均文長 24 /
 * 体言止め 35% / 会話文 42% / ケレン味 Lv.4 という**定数**を表示していた。
 * 表示だけがAssuranceれていて、也不可能だった。
 *
 * 現在の表示は 2 つの実データだけ:
 *  - 左: 実本文を**実測**した指標（utils/styleMetrics.ts）
 *  - 右: スライダーが表す目標仕様（体言止め率 / 比喩 / ケレン味）
 *    ※ スタイルそのものの仕様（instruction / dialogue_ratio / syntax_rhythm /
 *      metaphor_dna）はバックエンドの GET /styles/{id}/preview が持つ。
 *      現在はこの画面が library に接続されていないため、上のスライダー値を
 *      目標として提示し、実本文との差分を示す構成にしてある。
 */
export const StyleComparisonModal: React.FC<StyleComparisonModalProps> = ({ onClose }) => {
  const [activeTab, setActiveTab] = useState("action");
  const [notice, setNotice] = React.useState<string | null>(null);
  const [styleParams, setStyleParams] = React.useState<StyleTuningParams>({
    kemeritsu: 3,
    bodyStop: 50,
    metaphor: 50,
  });
  const [customStyles, setCustomStyles] = React.useState<
    Array<{ id: string; name: string; params: StyleTuningParams }>
  >(() => {
    try {
      const saved = localStorage.getItem("customStyles");
      const parsed = saved ? JSON.parse(saved) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  });

  const scene = styleSamples.find((s) => s.id === activeTab);
  const metrics = useMemo(() => measureStyleMetrics(scene?.standardText ?? ""), [scene]);

  const applyReason = plannedReason("styleApply");
  const rewriteReason = plannedReason("styleRewrite");

  if (!scene) {
    return null;
  }

  const handleSaveAsCustom = () => {
    const name = window.prompt("カスタム文体の名前を入力してください");
    if (name) {
      const newStyle = {
        id: `custom_${Date.now()}`,
        name,
        params: styleParams,
      };
      setCustomStyles([...customStyles, newStyle]);
      localStorage.setItem("customStyles", JSON.stringify([...customStyles, newStyle]));
      setNotice(`カスタム文体「${name}」をライブラリに保存しました。実際の本文への適用は行いません。`);
    }
  };

  return (
    <div className="style-comparison-modal">
      {notice && (
        <div
          role="status"
          data-testid="style-notice"
          style={{
            margin: "12px 16px 0",
            padding: "12px 16px",
            borderRadius: "10px",
            whiteSpace: "pre-line",
            background: "var(--surface-3)",
            border: "1px solid var(--accent-success)",
            color: "var(--text-main)",
            fontSize: "0.9rem",
            lineHeight: 1.7,
          }}
        >
          {notice}
          <button
            type="button"
            onClick={() => setNotice(null)}
            style={{
              marginLeft: "12px",
              background: "transparent",
              border: "1px solid var(--border-color)",
              borderRadius: "6px",
              color: "var(--text-muted)",
              cursor: "pointer",
              padding: "2px 10px",
              fontSize: "0.8rem",
            }}
          >
            閉じる
          </button>
        </div>
      )}
      <div className="style-comparison-modal-content">
        <div className="style-comparison-modal-header">
          <h2>🎨 文体の実測値とスタイル仕様の比較</h2>
          <button className="style-comparison-modal-close" onClick={onClose} aria-label="閉じる">
            ✕
          </button>
        </div>
        <div className="style-comparison-modal-body">
          <div className="style-comparison-tabs">
            {["action", "dialogue", "psychology"].map((tabId) => {
              const tab = styleSamples.find((s) => s.id === tabId);
              return (
                <button
                  key={tabId}
                  onClick={() => setActiveTab(tabId as "action")}
                  className={activeTab === tabId ? "active" : ""}
                >
                  {tab?.title}
                </button>
              );
            })}
          </div>
          <div className="style-comparison-cards">
            <div className="style-comparison-card">
              <h3>現在の本文（実測）</h3>
              <p>{scene.standardText}</p>
              <div className="style-comparison-metrics" data-testid="measured-metrics">
                <span className="metric-badge">文数: {metrics.sentenceCount}</span>
                <span className="metric-badge">
                  平均文長: {metrics.averageSentenceLength.toFixed(1)} 文字/文
                </span>
                <span className="metric-badge">会話文比率: {toPercent(metrics.dialogueRatio)}%</span>
                <span className="metric-badge" title="語尾パターンによる推定値">
                  体言止め率: {toPercent(metrics.taigenStopRatio)}%（推定）
                </span>
                <span className="metric-badge">総文字数: {metrics.charCount}</span>
              </div>
            </div>
            <div className="style-comparison-card">
              <h3>目標とするスタイル仕様</h3>
              <div className="style-comparison-text-after">
                <p>
                  スタイル文による書き換えは
                  {rewriteReason ? `未実装です（${rewriteReason}）` : "未実装です"}
                  。そのため「After」テキストは表示せず、比較対象はスタイル仕様のみです。
                </p>
              </div>
              <div className="style-comparison-metrics" data-testid="target-metrics">
                <span className="metric-badge">体言止め目標: {styleParams.bodyStop}%</span>
                <span className="metric-badge">比喩目標: {styleParams.metaphor}%</span>
                <span className="metric-badge">ケレン味: Lv.{styleParams.kemeritsu}</span>
              </div>
              <StyleTuningSliders onChange={setStyleParams} />
              <div className="style-comparison-actions">
                <button onClick={handleSaveAsCustom} className="style-comparison-save-custom">
                  💾 カスタム文体としてライブラリ保存
                </button>
                <button
                  onClick={() => {
                    setNotice(
                      "スタイル適用は行えません。章节（Chapter）にスタイルを保存する項目が無いためです。"
                    );
                  }}
                  className="style-comparison-apply"
                  disabled={!!applyReason}
                  title={applyReason ?? undefined}
                  data-testid="style-apply-button"
                >
                  ✨ この文体スタイルを採用
                </button>
              </div>
              {applyReason ? (
                <p
                  style={{ marginTop: "8px", color: "var(--text-muted)", fontSize: "0.8rem" }}
                  data-testid="style-apply-reason"
                >
                  ※ {applyReason}
                </p>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
