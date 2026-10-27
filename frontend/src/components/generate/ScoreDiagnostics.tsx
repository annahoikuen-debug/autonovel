import React from "react";
import type { BookScore } from "../../api/quality";
import { plannedReason } from "../../capabilities";

/** スコアを構成する評価軸と表示名 */
const DIMENSIONS: Array<{ key: keyof BookScore; label: string }> = [
  { key: "structure_score", label: "構成" },
  { key: "coherency_score", label: "整合性" },
  { key: "reader_experience_score", label: "読者体験" },
  { key: "visual_textual_synergy_score", label: "描写と構成" },
  { key: "factual_grounding_score", label: "事実接地" },
];

interface ScoreDiagnosticsProps {
  bookScore: BookScore | null;
  isScoring: boolean;
  onRescore: () => void;
}

/**
 * 低スコアの章节に対する診断表示。
 *
 * 以前はここに「自動改善ループ実行中…」という無限スピナーがあったが、
 * 改善ループ自体は実装されておらず、何が起きているかを表さない表示だった
 * （数次レビューで捏造表示として指摘されていた項目）。
 *
 * 現在は実装済みの実データだけで構成する:
 *  - 評価軸ごとの実測スコア（最も低い軸を強調 = 次にどこを直すべきかを示す）
 *  - 直近3章のトレンド（backend が返す trend_3ch）
 *  - backend と同じ判定規則による停滞アラート
 *  - 実際の再採点アクション
 */
export const ScoreDiagnostics: React.FC<ScoreDiagnosticsProps> = ({
  bookScore,
  isScoring,
  onRescore,
}) => {
  if (!bookScore) {
    return (
      <div
        style={{ display: "flex", alignItems: "center", gap: "8px", color: "var(--text-muted)", fontSize: "0.8rem" }}
        data-testid="score-diagnostics-empty"
      >
        スコアを取得できませんでした。
        <button type="button" onClick={onRescore} disabled={isScoring} style={linkButtonStyle}>
          再試行
        </button>
      </div>
    );
  }

  const scored = DIMENSIONS
    .map((d) => ({ ...d, value: Number(bookScore[d.key] ?? 0) }))
    .filter((d) => Number.isFinite(d.value));
  const weakest = scored.length > 0 ? scored.reduce((a, b) => (a.value <= b.value ? a : b)) : null;

  const trend = bookScore.trend_3ch;
  // backend の stagnation 判定と同じ規則: 傾斜がほぼゼロかつ平均70未満
  const isStagnant =
    !!trend && Math.abs(trend.trend_slope ?? 0) < 0.5 && (trend.avg_overall_score ?? 0) < 70;

  return (
    <div
      style={{ display: "flex", flexDirection: "column", gap: "6px", fontSize: "0.8rem" }}
      data-testid="score-diagnostics"
    >
      <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
        <span style={{ color: isStagnant ? "#f87171" : "var(--text-muted)", fontWeight: 600 }}>
          {isStagnant
            ? `スコアが停滞しています（平均 ${(trend?.avg_overall_score ?? 0).toFixed(1)}、傾斜 ${(trend?.trend_slope ?? 0).toFixed(2)}）`
            : weakest
              ? `最も低い評価軸: ${weakest.label}（${weakest.value.toFixed(1)}）`
              : "評価軸のスコアがありません"}
        </span>
        <button type="button" onClick={onRescore} disabled={isScoring} style={linkButtonStyle}>
          {isScoring ? "採点中..." : "再採点"}
        </button>
      </div>

      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
        {scored.map((d) => {
          const isWeakest = weakest?.key === d.key;
          return (
            <span
              key={String(d.key)}
              title={isWeakest ? "最も低い評価軸" : undefined}
              style={{
                padding: "1px 8px",
                borderRadius: "999px",
                fontSize: "0.75rem",
                fontWeight: isWeakest ? 700 : 500,
                background: isWeakest ? "rgba(248, 113, 113, 0.18)" : "var(--surface-3)",
                color: isWeakest ? "#fca5a5" : "var(--text-muted)",
                border: `1px solid ${isWeakest ? "rgba(248, 113, 113, 0.4)" : "var(--border-color)"}`,
              }}
            >
              {d.label}: {d.value.toFixed(1)}
            </span>
          );
        })}
      </div>

      {trend && trend.recent_scores?.length > 0 ? (
        <span style={{ color: "var(--text-muted)" }} data-testid="score-trend">
          直近 {trend.chapters_count} 章:{" "}
          {trend.recent_scores.map((s) => `第${s.chapter}話 ${Number(s.overall).toFixed(0)}`).join(" → ")}
        </span>
      ) : null}

      <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>
        ※ {plannedReason("autoImproveLoop")}
      </span>
    </div>
  );
};

const linkButtonStyle: React.CSSProperties = {
  background: "transparent",
  border: "1px solid var(--border-color)",
  borderRadius: "6px",
  color: "var(--text-muted)",
  cursor: "pointer",
  padding: "1px 8px",
  fontSize: "0.75rem",
};
