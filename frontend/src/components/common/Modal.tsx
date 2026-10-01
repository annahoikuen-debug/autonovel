import React, { useEffect, useId, useRef } from "react";

interface ModalProps {
  /** モーダルを表示するか */
  isOpen: boolean;
  /** 閉じるハンドラー（オーバーレイクリック・Esc キー・閉じるボタンで呼ばれる） */
  onClose: () => void;
  /** ヘッダータイトル（アイコン付き可） */
  title: React.ReactNode;
  /** モーダル本文 */
  children: React.ReactNode;
  /** data-testid プレフィックス（例: "media-modal"） */
  testId?: string;
  /** 閉じるボタンの data-testid */
  closeBtnTestId?: string;
  /** コンテンツ最大幅 (px) */
  maxWidth?: number;
  /** コンテンツ最大高さ (vh) */
  maxHeightVh?: number;
  /** a11y: ダイアログのラベル用 id（title に設定される） */
  ariaLabelledBy?: string;
  /** z-index（デフォルト 1000） */
  zIndex?: number;
}

/**
 * 開いているモーダルのスタック（一番上に積まれているものだけが Esc を受ける）。
 *
 * 以前は全モーダルが `window` の keydown を監視していたため、2 つ同時に開いていると
 * 1 回の Esc で両方閉じてしまう。`GlobalModals` は複数のモーダルを同時に描画しうる。
 */
const openModalStack: object[] = [];

/** body のスクロールロックの深さ（モーダルごとに 1 ずつ増やす） */
let scrollLockDepth = 0;
/** ロック直前の body.style.overflow（完全解除時に戻す） */
let scrollLockPrevOverflow = "";

/**
 * 共通モーダルコンポーネント。
 *
 * - オーバーレイ + カード型コンテンツの重複実装を統合
 * - role="dialog" / aria-modal / Esc キー / フォーカストラップ対応
 * - オーバーレイクリックで閉じる（コンテンツ内クリックは無視）
 */
export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  children,
  testId,
  closeBtnTestId,
  maxWidth = 900,
  maxHeightVh = 85,
  ariaLabelledBy,
  zIndex = 1000,
}) => {
  const contentRef = useRef<HTMLDivElement>(null);
  /** 開く前にフォーカスをどこへ置いていたか */
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);
  /** このモーダルインスタンスをスタック上で識別するためのトークン */
  const stackTokenRef = useRef<object>({});
  const uid = useId();

  // Esc キーで閉じる（同時に開いているモーダルのうち一番上のものだけ）
  useEffect(() => {
    if (!isOpen) return;
    const token = stackTokenRef.current;
    openModalStack.push(token);
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (openModalStack[openModalStack.length - 1] !== token) return;
      e.preventDefault();
      onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      const idx = openModalStack.lastIndexOf(token);
      if (idx >= 0) openModalStack.splice(idx, 1);
    };
  }, [isOpen, onClose]);

  // 開いた時にフォーカスをコンテンツへ移動（キーボード操作の起点）
  // 閉じるとき / isOpen を保ったままアンマウントされたときの双方で、開く前の場所へ戻す
  useEffect(() => {
    if (!isOpen) return;
    previouslyFocusedRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    contentRef.current?.focus();
    return () => {
      previouslyFocusedRef.current?.focus?.();
      previouslyFocusedRef.current = null;
    };
  }, [isOpen]);

  // ダイアログの外のウィンドウキー操作を開かないようにする
  // 参照カウント式にして、内側のモーダルを閉じたときに
  // 外側のロックまで解けて背面がスクロールしないようにする
  useEffect(() => {
    if (!isOpen) return;
    if (scrollLockDepth === 0) {
      scrollLockPrevOverflow = document.body.style.overflow;
    }
    scrollLockDepth += 1;
    document.body.style.overflow = "hidden";
    return () => {
      scrollLockDepth = Math.max(0, scrollLockDepth - 1);
      if (scrollLockDepth === 0) {
        document.body.style.overflow = scrollLockPrevOverflow;
        scrollLockPrevOverflow = "";
      }
    };
  }, [isOpen]);

  const FOCUSABLE_SELECTOR =
    'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

  /**
   * フォーカス可能かどうかの判定。
   *
   * `offsetParent` による判定は `position: fixed` の要素を「非表示」と誤判定し、
   * jsdom では常に null（＝不可視）になるためトラップが永久に機能しなくなっていた。
   * 計算スタイルで見ればどちらの問題も避けられる。
   */
  const isFocusable = (el: HTMLElement): boolean => {
    if (el.hasAttribute("hidden") || el.getAttribute("aria-hidden") === "true") return false;
    const style = window.getComputedStyle(el);
    return style.display !== "none" && style.visibility !== "hidden";
  };

  /**
   * Tab キーの行き来をダイアログ内に留める（フォーカストラップ）。
   *
   * ダイアログが開いている間、最後の要素で Tab すると最初の要素へ、
   * 最初の要素で Shift+Tab すると最後の要素へ戻す。
   */
  const handleDialogKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "Tab" || !contentRef.current) return;
    const focusables = Array.from(
      contentRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
    ).filter(isFocusable);
    if (focusables.length === 0) return;

    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    const active = document.activeElement;

    if (e.shiftKey) {
      if (active === first || !contentRef.current.contains(active)) {
        e.preventDefault();
        last.focus();
      }
    } else if (active === last) {
      e.preventDefault();
      first.focus();
    }
  };

  if (!isOpen) return null;

  // a11y: ダイアログには必ずアクセシブルネームを与える。
  // ariaLabelledBy / testId が無ければ見出しへ自動生成した id を振り、
  // 文字列の title では aria-label で同じ名前を与える。
  const headingId = ariaLabelledBy ?? (testId ? `${testId}-title` : `modal-title-${uid}`);
  const titleText = typeof title === "string" && title.trim() !== "" ? title : undefined;
  const labelledBy = ariaLabelledBy || testId || !titleText ? headingId : undefined;
  const ariaLabel = labelledBy ? undefined : titleText;

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: "rgba(0,0,0,0.7)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex,
        backdropFilter: "blur(4px)",
      }}
      data-testid={testId}
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={contentRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-label={ariaLabel}
        onKeyDown={handleDialogKeyDown}
        className="modal-content"
        style={{
          background: "var(--card-bg, #18181b)",
          border: "1px solid var(--border-color, #27272a)",
          borderRadius: "12px",
          width: "90%",
          maxWidth: `${maxWidth}px`,
          padding: "20px",
          maxHeight: `${maxHeightVh}vh`,
          overflowY: "auto",
          outline: "none",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "16px",
          }}
        >
          <h2
            id={headingId}
            style={{
              margin: 0,
              fontSize: "1.2rem",
              color: "var(--accent-primary)",
            }}
          >
            {title}
          </h2>
          <button
            type="button"
            className="modal-close-btn"
            style={{
              background: "transparent",
              border: "none",
              color: "var(--text-muted)",
              cursor: "pointer",
              fontSize: "1.2rem",
            }}
            onClick={onClose}
            aria-label="閉じる"
            data-testid={closeBtnTestId}
          >
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
};

export default Modal;
