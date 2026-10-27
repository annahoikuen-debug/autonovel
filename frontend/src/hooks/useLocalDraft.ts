import { useState, useEffect, useCallback } from "react";

// localStorage の概算容量制限（ブラウザによるが、安全側に倒して 4.5MB とする）。
// ドラフト保存でこれを超えると QuotaExceededError でクラッシュする。
const LOCAL_STORAGE_SOFT_LIMIT_BYTES = 4_500_000;

function estimateUtf8Bytes(str: string): number {
  // TextEncoder が使える環境では正確なバイト数を測る。
  if (typeof TextEncoder !== "undefined") {
    return new TextEncoder().encode(str).length;
  }
  // フォールバック: ASCII 近似（2バイト/文字で上回る見積もり）
  return str.length * 2;
}

export function useLocalDraft(key: string, initial: string) {
  const [content, setContent] = useState(() => {
    if (typeof window === "undefined") return initial;
    try {
      const saved = localStorage.getItem(key);
      return saved ? saved : initial;
    } catch {
      // プライベートモード等で localStorage が禁じられている
      return initial;
    }
  });

  useEffect(() => {
    const id = setInterval(() => {
      try {
        const bytes = estimateUtf8Bytes(content);
        if (bytes > LOCAL_STORAGE_SOFT_LIMIT_BYTES) {
          // 容量超過時は保存をスキップし、コンソールに警告のみ。
          // ユーザーに「下書きが大きすぎる」ことを通知するのは呼び出し側の責務。
          if (process.env.NODE_ENV !== "test") {
            console.warn(
              `[useLocalDraft] key="${key}" exceeds localStorage soft limit (${Math.round(
                LOCAL_STORAGE_SOFT_LIMIT_BYTES / 1_000_000
              )}MB). Draft not persisted.`
            );
          }
          return;
        }
        localStorage.setItem(key, content);
      } catch {
        // QuotaExceededError やプライベートモード等。保存をスキップ。
      }
    }, 2000);
    return () => clearInterval(id);
  }, [content, key]);

  const clearDraft = useCallback(() => {
    try {
      localStorage.removeItem(key);
    } catch {
      // ignore storage error
    }
    setContent(initial);
  }, [key, initial]);

  return [content, setContent, clearDraft] as const;
}