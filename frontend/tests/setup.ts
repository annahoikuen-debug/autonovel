import '@testing-library/jest-dom';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach } from 'vitest';

/**
 * テスト間の DOM 累積を防ぐ。
 *
 * RTL は `globals: true` のとき自動クリーンアップを仕込むが、このプロジェクトは
 * テストファイルが `render` を直接 import して使う形になっており、
 * 自動クリーンアップが効かないケースで「要素が複数見つかる」失敗起きていた。
 * ここで明示的に cleanup して、テスト間の区切りを確実にする。
 */
afterEach(() => {
  cleanup();
  // テスト中に書き換えたグローバルを元へ戻す（他ファイルへの汚染防止）
  document.body.style.overflow = '';
  document.body.innerHTML = '';
});

/*
 * localStorage スタブ（Node 26 + jsdom 24 環境対策）。
 *
 * Node 26 の実験的 global localStorage は `--localstorage-file` 未指定で
 * 無効化され、jsdom 24 と衝突して `window.localStorage` が undefined になる
 * （"localStorage is not available because --localstorage-file was not provided"）。
 * 多数のテストファイルが `window.localStorage.clear()` を直書きしているため、
 * undefined のままでは全テストが環境エラーで落ちる。ここで in-memory スタブを
 * 注入し、環境エラーとテストロジックの失敗を分離する。
 * vite.config.ts 側の `environmentOptions.jsdom.url` は opaque origin 対策として設定済み。
 */
if (typeof window !== "undefined" && window.localStorage === undefined) {
  const store = new Map<string, string>();
  const stub = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, String(value));
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
    clear: () => {
      store.clear();
    },
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    get length() {
      return store.size;
    },
  };
  Object.defineProperty(window, "localStorage", {
    value: stub,
    configurable: true,
    writable: true,
  });
}

beforeEach(() => {
  /*
   * テスト間の localStorage 初期化（防御的呼び出し）。
   * 上のスタブ注入により、この環境では常に localStorage が存在する。
   */
  window.localStorage?.clear?.();
});

class MockWebSocket extends EventTarget {
  url: string;
  readyState = 1;
  onopen: any = null;
  onclose: any = null;
  onmessage: any = null;
  onerror: any = null;

  constructor(url: string) {
    super();
    this.url = url;
    setTimeout(() => {
      this.onopen?.(new Event('open'));
      this.dispatchEvent(new Event('open'));
    }, 0);
  }

  send() { }
  close() {
    this.readyState = 3;
    setTimeout(() => {
      this.onclose?.(new Event('close'));
      this.dispatchEvent(new Event('close'));
    }, 0);
  }
}

globalThis.WebSocket = MockWebSocket as any;

// Minimal setup
export const server = {
  resetHandlers: () => { },
  close: () => { },
};
