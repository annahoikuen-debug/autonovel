/**
 * Play モードページ(Phase 0)
 *
 * 生成済み書籍の IF グラフを「遊ぶ」ビューア。
 * バックエンドの /api/branches/play 系は実装済み(docs/STATUS.md §2)で、
 * 本ページはその表面化(docs/implementation_plans/playable_novel_phase0.md)。
 *
 * スコープ(Phase 0):
 *   - グラフ型プレイ(事前生成グラフ上の選択)のみ
 *   - 動的継続生成は Phase 1(feature flag ENABLE_DYNAMIC_BRANCH、既定 OFF)
 *   - WebSocket は使わない(Q2: REST のみ)
 */
import React, { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchBranches } from "../api/branches";
import { fetchEpisodeIllustration } from "../api/illustrations";
import { BranchResponse, BranchPlayNode } from "../types/branches";
import { usePlaySession } from "../hooks/usePlaySession";
import { Button } from "../components/common/Button";
import { Panel } from "../components/common/Panel";
import { useNovelContext } from "../context/NovelContext";

/** current_node は「空オブジェクト」で来ることがあるため、描画可能なノードか判定する */
function asPlayableNode(node: BranchPlayNode | Record<string, unknown> | undefined): BranchPlayNode | null {
  if (!node || typeof node !== "object") return null;
  if ("id" in node && "content" in node) return node as BranchPlayNode;
  return null;
}

/** 書籍を選ぶ画面(/app/play) */
function BookPicker() {
  const { books, selectedBook } = useNovelContext();
  return (
    <div className="main-grid" data-testid="play-book-picker">
      <Panel title="📖 遊ぶ作品を選んでください">
        {(books || []).length === 0 ? (
          <p style={{ color: "var(--text-muted)" }}>
            まだ作品がありません。まず「かんたん執筆」で小説を生成してください。
          </p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, display: "grid", gap: "8px" }}>
            {(books || []).map((book) => (
              <li key={book.id}>
                <Link
                  to={`/app/play/${book.id}`}
                  data-testid={`play-book-${book.id}`}
                  style={{ color: "var(--accent-color, inherit)", textDecoration: "none" }}
                >
                  {book.title || `書籍 #${book.id}`}
                </Link>
                {selectedBook?.id === book.id && (
                  <span style={{ marginLeft: "8px", fontSize: "0.8rem", color: "var(--text-muted)" }}>
                    (選択中)
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

/** IF グラフが未生成の書籍に対するガイダンス(S10) */
function GraphMissingGuidance() {
  return (
    <Panel title="🧭 この作品はまだ分岐がありません">
      <p style={{ color: "var(--text-main)", lineHeight: 1.7 }}>
        この書籍には IF ルートグラフが生成されていません。
        Studio の「ブランチ管理」で分岐を作成すると、この画面で遊べるようになります。
      </p>
      <p style={{ marginTop: "8px" }}>
        <Link to="/app/studio" data-testid="play-guidance-studio-link">
          Studio を開く →
        </Link>
      </p>
    </Panel>
  );
}

export function PlayModePage() {
  const params = useParams();
  const bookIdParam = params.bookId;
  const bookId = useMemo(() => {
    const n = Number(bookIdParam);
    return Number.isInteger(n) && n > 0 ? n : null;
  }, [bookIdParam]);

  if (!bookId) {
    return (
      <main data-testid="play-mode-page">
        <BookPicker />
      </main>
    );
  }
  return (
    <main data-testid="play-mode-page">
      <PlaySessionView bookId={bookId} />
    </main>
  );
}

/** ブランチ選択 + プレイ本体 */
function PlaySessionView({ bookId }: { bookId: number }) {
  const play = usePlaySession();
  const [sceneImageUrl, setSceneImageUrl] = useState<string | null>(null);
  const [searchParams] = useSearchParams();
  /** ?branch=<id> で分岐を事前選択できる(BranchManagement からの導線) */
  const preselectedBranchId = useMemo(() => {
    const n = Number(searchParams.get("branch"));
    return Number.isInteger(n) && n > 0 ? n : null;
  }, [searchParams]);
  const [selectedBranchId, setSelectedBranchId] = useState<number | null>(preselectedBranchId);

  const { data: branches, isLoading, isError } = useQuery<BranchResponse[], Error>({
    queryKey: ["playBranches", bookId],
    queryFn: () => fetchBranches(bookId),
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });

  const effectiveBranchId = selectedBranchId ?? branches?.[0]?.id ?? null;
  const selectedBranch = branches?.find((b) => b.id === effectiveBranchId) ?? null;

  const node = asPlayableNode(play.state?.current_node);
  const hasChoices = (play.state?.available_choices ?? []).length > 0;
  /** グラフが空(未生成 or 終端後の空状態)の判定。ガイダンス表示用(S10) */
  const graphMissing = play.phase === "playing" && play.state != null && node == null && !hasChoices;

  // 現在ノードの話数に対応する挿絵を解決する(Phase 3 Increment 1)。
  // 見つからない・取得失敗のときは画像なしでフォールバック(ロードマップ受入基準)。
  const episodeNum = node?.episode_num ?? null;
  useEffect(() => {
    let cancelled = false;
    setSceneImageUrl(null);
    if (episodeNum == null || episodeNum < 1) return;
    fetchEpisodeIllustration(bookId, episodeNum)
      .then((url) => {
        if (!cancelled && url) setSceneImageUrl(url);
      })
      .catch(() => {
        // 取得失敗は「画像なし」として黙ってフォールバックする
      });
    return () => {
      cancelled = true;
    };
  }, [bookId, episodeNum]);

  const handleStart = async () => {
    if (effectiveBranchId == null) return;
    await play.start(bookId, effectiveBranchId);
  };

  return (
    <div style={{ display: "grid", gap: "16px", padding: "20px" }}>
      <header style={{ display: "flex", alignItems: "baseline", gap: "12px" }}>
        <h1 style={{ margin: 0 }}>▶ Play モード</h1>
        <span style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>
          書籍 #{bookId}
          {selectedBranch ? ` — ${selectedBranch.name}` : ""}
        </span>
        <span style={{ marginLeft: "auto" }}>
          <Link to="/app/studio" data-testid="play-back-to-studio">
            ← Studio に戻る
          </Link>
        </span>
      </header>

      {isError && (
        <p role="alert" style={{ color: "var(--danger-color, #c0392b)" }}>
          ブランチ一覧の取得に失敗しました。
        </p>
      )}

      {/* --- セッション開始前 --- */}
      {(play.phase === "idle" || play.phase === "starting") && (
        <Panel title="分岐を選んで開始">
          {isLoading ? (
            <p style={{ color: "var(--text-muted)" }}>読み込み中…</p>
          ) : (branches ?? []).length === 0 ? (
            <p style={{ color: "var(--text-muted)" }}>
              ブランチがありません。Studio で分岐を作成してください。
            </p>
          ) : (
            <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
              <select
                aria-label="プレイする分岐を選択"
                data-testid="play-branch-select"
                value={effectiveBranchId ?? ""}
                onChange={(e) => {
                  const id = Number(e.target.value);
                  if (Number.isInteger(id)) setSelectedBranchId(id);
                }}
                style={{ padding: "6px 10px" }}
              >
                {(branches ?? []).map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name || `ブランチ #${b.id}`}
                  </option>
                ))}
              </select>
              <Button
                variant="accent-cyan"
                onClick={handleStart}
                disabled={play.busy || effectiveBranchId == null}
                data-testid="play-start-btn"
              >
                {play.phase === "starting" ? "開始中…" : "▶ プレイ開始"}
              </Button>
            </div>
          )}
          {play.error && (
            <p role="alert" data-testid="play-error" style={{ color: "var(--danger-color, #c0392b)", marginTop: "8px" }}>
              {play.error}
            </p>
          )}
        </Panel>
      )}

      {/* --- グラフ未生成ガイダンス(S10) --- */}
      {graphMissing && <GraphMissingGuidance />}

      {/* --- プレイ中 --- */}
      {(play.phase === "playing" || play.phase === "ending") && play.state && (
        <>
          {node && (
            <Panel
              title={`第 ${node.episode_num} 話${node.branch_type ? `（${node.branch_type}）` : ""}`}
            >
              {sceneImageUrl && (
                <img
                  src={sceneImageUrl}
                  alt={`第 ${node.episode_num} 話の挿絵`}
                  data-testid="play-scene-image"
                  style={{
                    maxWidth: "100%",
                    borderRadius: "8px",
                    marginBottom: "12px",
                    display: "block",
                  }}
                />
              )}
              <div
                data-testid="play-scene-content"
                style={{ whiteSpace: "pre-wrap", lineHeight: 1.9, color: "var(--text-main)" }}
              >
                {node.content}
              </div>
            </Panel>
          )}

          {hasChoices && (
            <Panel title="あなたの選択 — どうする?">
              <div style={{ display: "grid", gap: "8px" }}>
                {(play.state?.available_choices ?? []).map((choice) => (
                  <Button
                    key={choice.id}
                    variant="secondary"
                    onClick={() => play.choose(choice.id)}
                    disabled={play.busy}
                    data-testid={`play-choice-${choice.id}`}
                    style={{ justifyContent: "flex-start", textAlign: "left" }}
                  >
                    {choice.text}
                  </Button>
                ))}
              </div>
            </Panel>
          )}

          {!hasChoices && node && (
            <p style={{ color: "var(--text-muted)" }}>
              この先の選択肢はありません(グラフの終端に到達しました)。
            </p>
          )}

          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            <Button
              variant="accent-purple"
              onClick={() => play.save()}
              disabled={play.busy}
              data-testid="play-save-btn"
            >
              💾 セーブ
            </Button>
            <Button
              variant="secondary"
              onClick={() => play.load((play.state?.save_points_count ?? 1) - 1)}
              disabled={play.busy || (play.state?.save_points_count ?? 0) === 0}
              data-testid="play-load-btn"
            >
              ⏪ 最新のセーブから再開
            </Button>
            <Button
              variant="secondary"
              onClick={() => play.loadHistory()}
              disabled={play.busy}
              data-testid="play-history-btn"
            >
              📋 これまでの選択を見る
            </Button>
            <Button
              variant="danger"
              onClick={() => play.end()}
              disabled={play.busy}
              data-testid="play-end-btn"
            >
              ■ プレイを終了
            </Button>
          </div>

          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }} data-testid="play-save-count">
            セーブポイント: {play.state?.save_points_count ?? 0} 件
          </p>

          {play.error && (
            <p role="alert" data-testid="play-error" style={{ color: "var(--danger-color, #c0392b)" }}>
              {play.error}
            </p>
          )}

          {play.playthrough && (
            <Panel title="📋 プレイスルー記録" >
              <div data-testid="play-playthrough">
                <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
                  選択履歴 {play.playthrough.history.length} 件
                  {play.playthrough.final_ending ? ` — 結末: ${play.playthrough.final_ending}` : ""}
                </p>
                <pre
                  style={{
                    background: "var(--bg-muted)",
                    padding: "12px",
                    borderRadius: "6px",
                    fontSize: "0.8rem",
                    overflow: "auto",
                    maxHeight: "240px",
                  }}
                >
                  {JSON.stringify(play.playthrough.history, null, 2)}
                </pre>
              </div>
            </Panel>
          )}
        </>
      )}

      {/* --- 終了後 --- */}
      {play.phase === "ended" && (
        <Panel title="▶ プレイを終了しました">
          <p style={{ color: "var(--text-main)" }}>
            おつかれさまでした。プレイの記録は作品に保存されています。
          </p>
          <div style={{ display: "flex", gap: "8px" }}>
            <Button
              variant="accent-cyan"
              onClick={() => play.reset()}
              data-testid="play-restart-btn"
            >
              もう一度遊ぶ
            </Button>
            <Link to="/app/studio" data-testid="play-ended-studio-link">
              Studio に戻る
            </Link>
          </div>
        </Panel>
      )}
    </div>
  );
}

export default PlayModePage;
