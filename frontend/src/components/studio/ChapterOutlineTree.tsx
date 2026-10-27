import React, { useState } from "react";
import { useNovelContext } from "../../context/NovelContext";
import { ChapterItem } from "../../types";
import { ChapterProgressBar } from "./ChapterProgressBar";
import { chapterStatusMap, ChapterStatus } from "../../constants/chapterStatus";
import { reorderChapters } from "../../hooks/useChapterReorder";
import { upsertChapter, deleteChapter, UpsertChapterPayload } from "../../api/chapters";

/** ステータスの更新順序（クリックごとに次のステータスへ巡回する） */
const STATUS_ORDER = ["draft", "writing", "completed", "polished"] as const;

/**
 * ステータスの表示を引く。
 *
 * サーバから読んだ章（`StoredChapter`）には `status` が無く、壊れた値も混ざりうる。
 * 未設定・未知の値は必ず `draft` へ落とす。参照が `undefined` のまま `.color` を
 * 読むと TypeError になり Studio ごと落ちる。
 */
const statusMeta = (status: ChapterItem["status"]) =>
  chapterStatusMap[status as ChapterStatus] ?? chapterStatusMap.draft;

/**
 * 章の配列位置を求める。
 *
 * 添字に `ep_num - 1` を使うと、途中の章を削除して話数が空いた瞬間に
 * 並び替えが黙って無効化されるため、必ず配列から探す。
 */
const indexOfChapter = (list: ChapterItem[], epNum: number) =>
  list.findIndex((c) => c.ep_num === epNum);

/** 章を別の位置へ移したときの並び（オブジェクトは元のまま。話数の追跡にだけ使う） */
const orderAfterMove = (
  list: ChapterItem[],
  fromIndex: number,
  toIndex: number,
): ChapterItem[] => {
  const next = [...list];
  const [moved] = next.splice(fromIndex, 1);
  if (!moved) return list;
  next.splice(toIndex, 0, moved);
  return next;
};

/**
 * 話数を連番に振り直す。
 *
 * `reorderChapters` の話数・タイトルの振り直しを 그대로借用している
 * （同じ添字への移動は「並びはそのまま・話数だけ付け替え」になる）。
 */
const renumberChapters = (list: ChapterItem[]): ChapterItem[] =>
  list.length > 0 ? reorderChapters(list, 0, 0) : list;

interface ChapterOutlineTreeProps {
  onSelectChapter?: (epNum: number) => void;
   onMessage?: (msg: string, type: "success" | "error" | "info") => void;
}

export const ChapterOutlineTree: React.FC<ChapterOutlineTreeProps> = ({ onSelectChapter, onMessage }) => {
  const {
    chapters: rawChapters,
    setChapters,
    currentEpNum = 1,
    setCurrentEpNum,
    selectedBookId,
  } = useNovelContext();
  const chapters = rawChapters ?? [];
  const [editingEpNum, setEditingEpNum] = useState<number | null>(null);
  const [editingTitle, setEditingTitle] = useState('');
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);

  const handleSelect = (epNum: number) => {
    setCurrentEpNum(epNum);
    onSelectChapter?.(epNum);
  };

  /**
   * サーバ保存に失敗したときの通知。
   *
   * 画面上の状態は先に更新する（楽観更新）ので、
   * 永続化に失敗したときは必ず伝える。黙って壊れた状態にはしない。
   */
  const notifyPersistFailure = (action: string, epNum: number) => {
    onMessage?.(
      `⚠️ ${action}（第${epNum}話）をサーバーに保存できませんでした。`,
      "error",
    );
  };

  /** 楽観更新を破棄して、保存前の状態（と選択中の話）へ巻き戻す */
  const restoreSnapshot = (snapshot: ChapterItem[], epNum?: number) => {
    setChapters(snapshot);
    const target =
      snapshot.find((c) => c.ep_num === epNum) ??
      snapshot.find((c) => c.ep_num === currentEpNum) ??
      snapshot[0];
    if (target) setCurrentEpNum(target.ep_num);
  };

  /**
   * 保存して、失敗したら必ず伝える。
   *
   * `rollback` を渡すと、保存前の状態へ巻き戻すまで行う。
   * `.catch` でも同じ扱いにするのは、`apiFetch` がネットワーク断で例外を投げ、
   * ここを通らないと unhandled rejection になって何も伝わらないため。
   */
  const saveChapters = (
    requests: Promise<boolean>[],
    action: string,
    epNum: number,
    rollback?: () => void,
  ) => {
    const handleFailure = () => {
      rollback?.();
      notifyPersistFailure(action, epNum);
    };
    void Promise.all(requests)
      .then((results) => {
        if (results.some((ok) => !ok)) handleFailure();
      })
      .catch(handleFailure);
  };

  /** 1 話を保存する（失敗したら巻き戻し＋通知） */
  const saveChapter = (
    epNum: number,
    payload: UpsertChapterPayload,
    action: string,
    rollback?: () => void,
  ) => {
    saveChapters(
      [upsertChapter(selectedBookId, epNum, payload)],
      action,
      epNum,
      rollback,
    );
  };

  /** 並び替え後の話数で全章を保存し直す */
  const saveChapterOrder = (
    list: ChapterItem[],
    action: string,
    epNum: number,
    rollback?: () => void,
  ) =>
    saveChapters(
      list.map((c) =>
        upsertChapter(selectedBookId, c.ep_num, {
          title: c.title,
          content: c.content,
          summary: c.summary,
        }),
      ),
      action,
      epNum,
      rollback,
    );

  const handleAddChapter = () => {
    const snapshot = chapters;
    const nextEpNum = chapters.length > 0 ? Math.max(...chapters.map((c) => c.ep_num)) + 1 : 1;
    const newChapter: ChapterItem = {
      ep_num: nextEpNum,
      title: `第${nextEpNum}話 新たな展開`,
      summary: 'プロット目標を設定してください',
      content: `【第${nextEpNum}話】\n\n`,
      is_catharsis: false,
      status: 'draft',
    };
    // 先に画面へ反映し、そのあとサーバへ保存する
    setChapters((prev) => [...prev, newChapter]);
    setCurrentEpNum(nextEpNum);
    saveChapter(
      nextEpNum,
      {
        title: newChapter.title,
        content: newChapter.content,
        summary: newChapter.summary,
      },
      "章の追加",
      () => restoreSnapshot(snapshot, currentEpNum),
    );
  };

  const handleStartEdit = (ch: ChapterItem, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingEpNum(ch.ep_num);
    setEditingTitle(ch.title);
  };

  const handleSaveTitle = (epNum: number, e?: React.FormEvent) => {
    e?.preventDefault();
    const title = editingTitle.trim();
    if (title) {
      const snapshot = chapters;
      setChapters((prev) =>
        prev.map((c) => (c.ep_num === epNum ? { ...c, title } : c))
      );
      const target = snapshot.find((c) => c.ep_num === epNum);
      saveChapter(
        epNum,
        {
          title,
          content: target?.content ?? "",
          // サマリー未設定ならキーごと送らない（サーバ側の概要を消さない）
          summary: target?.summary,
        },
        "章名の変更",
        () => restoreSnapshot(snapshot, epNum),
      );
    }
    setEditingEpNum(null);
  };

  const handleDeleteChapter = (epNum: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (chapters.length <= 1) return;
    const snapshot = chapters;
    // 残りの話は連番に振り直す。話数が空くと ▲▼ と D&D の添字が壊れるため。
    const nextChapters = renumberChapters(snapshot.filter((c) => c.ep_num !== epNum));
    setChapters(nextChapters);
    if (!nextChapters.some((c) => c.ep_num === currentEpNum)) {
      const nextChapter = nextChapters[0];
      if (nextChapter) {
        setCurrentEpNum(nextChapter.ep_num);
      }
    }
    void deleteChapter(selectedBookId, epNum)
      .then((ok) => {
        if (!ok) {
          restoreSnapshot(snapshot, epNum);
          notifyPersistFailure("章の削除", epNum);
          return;
        }
        // 削除した話枠を埋め直すため、残りを新しい話数で保存し直す
        saveChapterOrder(nextChapters, "章の削除", epNum);
      })
      .catch(() => {
        restoreSnapshot(snapshot, epNum);
        notifyPersistFailure("章の削除", epNum);
      });
  };

  const handleToggleCatharsis = (epNum: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setChapters((prev) =>
      prev.map((c) => (c.ep_num === epNum ? { ...c, is_catharsis: !c.is_catharsis } : c))
    );
  };

  const handleStatusChange = (epNum: number) => {
    setChapters((prev) =>
      prev.map((c): ChapterItem => {
        if (c.ep_num !== epNum) return c;
        const currentIndex = STATUS_ORDER.indexOf(
          (c.status ?? "draft") as (typeof STATUS_ORDER)[number],
        );
        // 未設定・未知の値は indexOf が -1 になり、そのまま計算すると
        // 何も無い 0 番（draft）へ戻ってしまう。次のステータスへ進める。
        const nextIndex = currentIndex === -1 ? 1 : (currentIndex + 1) % STATUS_ORDER.length;
        return { ...c, status: STATUS_ORDER[nextIndex] };
      })
    );
  };

  /**
   * ▲▼ とドラッグ＆ドロップが共有する並び替え。
   *
   * 保存は ▲▼ でも D&D でも同じ経路を通す。どちらかを経由しないと
   * リロードで並びが元に戻ってしまう（DoD「並び替えが保持される」が偽になる）。
   */
  const moveChapter = (fromIndex: number, toIndex: number) => {
    if (fromIndex === toIndex) return;
    const snapshot = chapters;
    const reordered = reorderChapters(chapters, fromIndex, toIndex);
    // 範囲外なら `reorderChapters` は元の配列を返す（＝何も動かしていない）
    if (reordered === snapshot) return;

    // 編集対象の話は、並びを確定させる前の配列で追う。
    // `reorderChapters` は `{...chapter}` を返すため事後の参照比較は成立しない。
    const activeIndex = indexOfChapter(snapshot, currentEpNum);
    const nextActiveIndex =
      activeIndex === -1 ? -1 : orderAfterMove(snapshot, fromIndex, toIndex).indexOf(snapshot[activeIndex]);

    setChapters(reordered);
    if (nextActiveIndex !== -1) {
      setCurrentEpNum(nextActiveIndex + 1);
    }
    onMessage?.("✨ 章の順序を並び替え、話数番号を自動再整列しました", "success");
    saveChapterOrder(
      reordered,
      "章の並び替え",
      currentEpNum,
      // 保存に失敗したら並びと選択中の話を元へ戻す
      () => restoreSnapshot(snapshot, activeIndex === -1 ? undefined : activeIndex + 1),
    );
  };

  const handleDragStart = (epNum: number) => {
    setDraggedIndex(indexOfChapter(chapters, epNum));
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    const chapterElement = e.currentTarget as HTMLElement;
    const indexStr = chapterElement.dataset.chapterIndex;
    if (indexStr !== undefined) {
      const index = parseInt(indexStr, 10);
      if (!isNaN(index)) {
        setDragOverIndex(index);
      }
    }
  };

  const handleDrop = (epNum: number) => {
    const targetIndex = indexOfChapter(chapters, epNum);
    if (draggedIndex !== null && draggedIndex !== targetIndex) {
      moveChapter(draggedIndex, targetIndex);
    }
    setDraggedIndex(null);
    setDragOverIndex(null);
  };

  const handleDragLeave = () => {
    setDragOverIndex(null);
  };

  const activeChapter = chapters.find((c) => c.ep_num === currentEpNum);

  return (
    <div className="chapter-outline-tree" data-testid="chapter-outline-tree" style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ fontSize: "0.95rem", color: "var(--accent-cyan)", fontWeight: 700, margin: 0 }}>
          📑 章・プロット一覧 ({chapters.length}話)
        </h3>
        <button
          type="button"
          className="inline-ai-btn"
          style={{ padding: "3px 8px", fontSize: "0.75rem" }}
          onClick={handleAddChapter}
          title="次の章を追加"
          data-testid="btn-add-chapter"
        >
          ➕ 章追加
        </button>
      </div>

      <ChapterProgressBar />
       {/* 現在執筆中の章のプロット目標カード */}
      {activeChapter && (
        <div
          style={{
            background: "rgba(56, 189, 248, 0.08)",
            border: "1px solid rgba(56, 189, 248, 0.25)",
            borderRadius: "6px",
            padding: "8px 10px",
            fontSize: "0.78rem",
            lineHeight: "1.4",
          }}
          data-testid="active-chapter-goal"
        >
          <div style={{ fontWeight: 700, color: "var(--accent-secondary, #38bdf8)", marginBottom: "2px" }}>
            🎯 執筆中: {activeChapter.title}
            {activeChapter.is_catharsis && <span style={{ marginLeft: "6px", color: "#fbbf24" }}>⭐ カタルシス</span>}
          </div>
          <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>
            {activeChapter.summary || "サマリー未設定"}
          </div>
        </div>
      )}

      {/* 章リスト */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "6px",
          maxHeight: "260px",
          overflowY: "auto",
          paddingRight: "2px",
        }}
      >
        {chapters.map((ch, index) => {
          const isActive = ch.ep_num === currentEpNum;
          const isEditing = editingEpNum === ch.ep_num;
          const meta = statusMeta(ch.status);

          return (
<div
               key={ch.ep_num}
               onClick={() => handleSelect(ch.ep_num)}
               onKeyDown={(e) => {
                 if (e.key === "Enter" || e.key === " ") {
                   e.preventDefault();
                   handleSelect(ch.ep_num);
                 }
               }}
               onDragStart={() => handleDragStart(ch.ep_num)}
               onDragOver={handleDragOver}
               onDragLeave={handleDragLeave}
               onDrop={() => handleDrop(ch.ep_num)}
               draggable={true}
               data-chapter-index={index}
               role="button"
               tabIndex={0}
               aria-current={isActive ? "true" : undefined}
               aria-label={`第${ch.ep_num}話 ${ch.title}`}
style={{
                  background: dragOverIndex === index ? "rgba(139, 92, 246, 0.1)" : isActive ? "rgba(139, 92, 246, 0.25)" : "rgba(255, 255, 255, 0.03)",
                  border: `1px solid ${isActive ? "var(--accent-purple, #8b5cf6)" : "rgba(255, 255, 255, 0.08)"}`,
                  borderLeft: `4px solid ${meta.color}`,
                  borderRadius: "6px",
                  padding: "8px 10px",
                  cursor: "pointer",
                  opacity: draggedIndex === index ? 0.5 : 1,
                  transition: "all 0.15s ease",
                }}
               data-testid={`chapter-item-${ch.ep_num}`}
             >
              {isEditing ? (
                 <form
                   onSubmit={(e) => handleSaveTitle(ch.ep_num, e)}
                   style={{ display: "flex", gap: "4px", alignItems: "center" }}
                   onClick={(e) => e.stopPropagation()}
                   // 親の章枠は Enter / Space で話を選択する（role="button" の役割）。
                   // stopPropagation しないと、入力欄で Enter を押しても
                   // preventDefault で form の submit が潰れ、タイトルが保存されないまま
                   // 半角スペースも入力されなくなる（= インライン編集が使えなくなる）。
                   onKeyDown={(e) => e.stopPropagation()}
                 >
                  <input
                    className="input"
                    style={{ padding: "3px 6px", fontSize: "0.78rem", flex: 1 }}
                    value={editingTitle}
                    onChange={(e) => setEditingTitle(e.target.value)}
                    autoFocus
                    onBlur={() => handleSaveTitle(ch.ep_num)}
                    aria-label={`第${ch.ep_num}話のタイトル`}
                    data-testid="input-edit-chapter-title"
                  />
                  <button type="submit" className="inline-ai-btn" style={{ padding: "2px 6px", fontSize: "0.7rem" }}>
                    ✓
                  </button>
                </form>
              ) : (
<div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                   <div style={{ display: "flex", alignItems: "center", gap: "4px", flex: 1 }}>
                     <span style={{ fontWeight: isActive ? 700 : 500, fontSize: "0.82rem", color: isActive ? "#f3f4f6" : "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                       {ch.title}
                     </span>
<span style={{ backgroundColor: "var(--bg-muted)", color: "var(--text)", padding: "2px 6px", borderRadius: "4px", fontSize: "0.7rem", marginLeft: "8px" }}>
                      {(ch.content?.length ?? 0) > 0 ? (ch.content?.length ?? 0).toLocaleString() + "字" : "未執筆"}
                    </span>
                   </div>
<div style={{ display: "flex", gap: "4px", alignItems: "center", marginLeft: "4px" }}>
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); handleStatusChange(ch.ep_num); }}
                        style={{
                          background: "transparent",
                          border: "none",
                          color: meta.color,
                          cursor: "pointer",
                          fontSize: "0.75rem",
                          padding: "1px 3px",
                        }}
                        title={meta.label}
                        aria-label={`第${ch.ep_num}話の状態: ${meta.label}`}
                      >
                        {meta.icon}
                      </button>
                      {/* Up/Down buttons */}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          moveChapter(index, index - 1);
                        }}
                        disabled={index === 0}
                        aria-label={`第${ch.ep_num}話を上へ移動`}
                        data-testid={`btn-move-up-${ch.ep_num}`}
                        style={{ background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: "0.75rem", padding: "1px 3px" }}
                      >
                        ▲
                      </button>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          moveChapter(index, index + 1);
                        }}
                        disabled={index === chapters.length - 1}
                        aria-label={`第${ch.ep_num}話を下へ移動`}
                        data-testid={`btn-move-down-${ch.ep_num}`}
                        style={{ background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: "0.75rem", padding: "1px 3px" }}
                      >
                        ▼
                      </button>
                      <button
                        type="button"
                        style={{ background: "transparent", border: "none", color: ch.is_catharsis ? "#fbbf24" : "var(--text-muted)", cursor: "pointer", fontSize: "0.75rem", padding: "1px 3px" }}
                        onClick={(e) => handleToggleCatharsis(ch.ep_num, e)}
                        title={ch.is_catharsis ? "カタルシス解除" : "カタルシス回に設定"}
                      >
                        {ch.is_catharsis ? "⭐" : "☆"}
                      </button>
                      <button
                        type="button"
                        style={{ background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: "0.75rem", padding: "1px 3px" }}
                        onClick={(e) => handleStartEdit(ch, e)}
                        title="タイトル編集"
                        data-testid={`btn-edit-title-${ch.ep_num}`}
                      >
                        ✏️
                      </button>
                      {chapters.length > 1 && (
                        <button
                          type="button"
                          style={{ background: "transparent", border: "none", color: "rgba(239, 68, 68, 0.7)", cursor: "pointer", fontSize: "0.75rem", padding: "1px 3px" }}
                          onClick={(e) => handleDeleteChapter(ch.ep_num, e)}
                          title="章を削除"
                          data-testid={`btn-delete-chapter-${ch.ep_num}`}
                        >
                          🗑️
                        </button>
                      )}
                    </div>
                 </div>
              )}

              {ch.summary && (
                <div
                  style={{
                    fontSize: "0.72rem",
                    color: "var(--text-muted)",
                    marginTop: "2px",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {ch.summary}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
