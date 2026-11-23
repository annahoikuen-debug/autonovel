import '@testing-library/jest-dom';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach } from 'vitest';

/**
 * Node 26+ 環境での localStorage フォールバック。
 *
 * Node の実験的 globalThis.localStorage は `--localstorage-file` 未指定では
 * 利用不能（"localStorage is not available" 警告）で、値が undefined になる。
 * vitest の jsdom 環境では globalThis が jsdom の window と同じ実体のため、
 * Node 側の own property が jsdom の Storage を影にしてしまい、
 * `window.localStorage` が undefined になって全テストが setup で落ちていた。
 *
 * 旧 Node(CI)では jsdom の Storage がそのまま使われ、この polyfill は発動しない。
 */
if (typeof window.localStorage === 'undefined') {
  class MemoryStorage {
    private store = new Map<string, string>();
    get length(): number {
      return this.store.size;
    }
    key(index: number): string | null {
      return Array.from(this.store.keys())[index] ?? null;
    }
    getItem(key: string): string | null {
      return this.store.has(key) ? (this.store.get(key) as string) : null;
    }
    setItem(key: string, value: string): void {
      this.store.set(String(key), String(value));
    }
    removeItem(key: string): void {
      this.store.delete(key);
    }
    clear(): void {
      this.store.clear();
    }
  }
  Object.defineProperty(window, 'localStorage', {
    value: new MemoryStorage(),
    configurable: true,
    writable: true,
  });
}

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

beforeEach(() => {
  window.localStorage.clear();
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
