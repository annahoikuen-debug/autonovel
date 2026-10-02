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
