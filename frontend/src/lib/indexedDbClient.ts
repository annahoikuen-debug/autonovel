/**
 * indexedDbClient - エディタスナップショットの IndexedDB 永続化クライアント。
 *
 * useIndexedDbAutosave / useCrashRecovery から利用されるシングルトン。
 *
 * 設計方針:
 * - DB オープンは初回アクセス時に遅延実行する（jsdom 等の indexedDB 非存在環境でも
 *   import 時に落ちず、呼び出し側の try/catch で握りつぶせる）。
 * - 失敗時は Promise を reject する。オートセーブはあくまで「ベストエフォート」であり、
 *   呼び出し元（useIndexedDbAutosave）が失敗を警告ログに落として継続する契約。
 */

import { EditorSnapshot } from "../types/editorSnapshot";

const DB_NAME = "autonovel-editor";
const DB_VERSION = 1;
const STORE_NAME = "snapshots";

/** 単一の DB 接続をプロセス内で使い回す（null = 未オープン） */
let dbPromise: Promise<IDBDatabase> | null = null;

function openDb(): Promise<IDBDatabase> {
  if (dbPromise) return dbPromise;

  dbPromise = new Promise<IDBDatabase>((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB is not available in this environment"));
      return;
    }
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: "key" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () =>
      reject(request.error ?? new Error("IndexedDB open failed"));
  });

  return dbPromise;
}

class IndexedDbClient {
  /** スナップショットの主キーを生成する */
  makeKey(bookId: string | number, episodeId: string | number): string {
    return `book:${bookId}:episode:${episodeId}`;
  }

  /** スナップショットを保存（上書き）する */
  async saveSnapshot(snapshot: EditorSnapshot): Promise<void> {
    const db = await openDb();
    return new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).put(snapshot);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error ?? new Error("saveSnapshot failed"));
      tx.onabort = () => reject(tx.error ?? new Error("saveSnapshot aborted"));
    });
  }

  /** スナップショットを取得する。無ければ null */
  async getSnapshot(
    bookId: string | number,
    episodeId: string | number
  ): Promise<EditorSnapshot | null> {
    const db = await openDb();
    return new Promise<EditorSnapshot | null>((resolve, reject) => {
      const key = this.makeKey(bookId, episodeId);
      const tx = db.transaction(STORE_NAME, "readonly");
      const request = tx.objectStore(STORE_NAME).get(key);
      request.onsuccess = () =>
        resolve((request.result as EditorSnapshot | undefined) ?? null);
      request.onerror = () => reject(request.error ?? new Error("getSnapshot failed"));
    });
  }

  /** スナップショットを削除する（復元確定後のクリーンアップ用） */
  async deleteSnapshot(bookId: string | number, episodeId: string | number): Promise<void> {
    const db = await openDb();
    return new Promise<void>((resolve, reject) => {
      const key = this.makeKey(bookId, episodeId);
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).delete(key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error ?? new Error("deleteSnapshot failed"));
    });
  }
}

export const indexedDbClient = new IndexedDbClient();
