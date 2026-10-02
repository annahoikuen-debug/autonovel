import { describe, it, expect } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? walk(p) : p.endsWith(".test.ts") || p.endsWith(".test.tsx") ? [p] : [];
  });
}

/**
 * src を import しないテストの正当な例外。理由 必须（空文字列は不可）。
 *
 * 「ファイルシステム走査型 archangel」は方針として src を import しない。
 * 対象コードを import すると、その archangel 自身が検査対象の
 * モジュールに依存してしまう（検出したい「壊れ方」を自分で作ってしまう）ため。
 */
const IMPORT_EXEMPT_SCAN_GUARDS: Record<string, string> = {
  "tautology.guard.test.ts": "本 guard 自身（ファイルシステム走査型）",
  "apiFetchContract.guard.test.ts":
    "apiFetch 契約の archangel。frontend/tests と frontend/src を走査する型で、" +
    "src を import すると検査対象自身が検査対象に依存してしまうため",
};

describe("tautology guard (frontend)", () => {
  it("src を import しないテストが無いこと", () => {
    const offenders: string[] = [];
    for (const p of walk("tests")) {
      // 本テスト自身および e2e (Playwright) は除外
      if (p.includes("tests\\e2e") || p.includes("tests/e2e")) {
        continue;
      }
      const base = p.split(/[\\/]/).pop() ?? "";
      if (base in IMPORT_EXEMPT_SCAN_GUARDS) {
        continue;
      }
      const src = readFileSync(p, "utf8");
      if (src.includes("expect(1).toBe(1)")) offenders.push(`${p}: expect(1).toBe(1)`);
      if (src.includes("expect(1 + 1).toBe(2)")) offenders.push(`${p}: expect(1 + 1).toBe(2)`);
      const hasSrcImport = /from\s+["'](@\/|[^"']*src\/)/.test(src);
      const hasSrcFileRead = /["']src\//.test(src);
      if (!hasSrcImport && !hasSrcFileRead && /describe\(/.test(src)) {
        offenders.push(`${p} (src を import していない)`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("除外リストに理由が全て書いてあること（§9: 数値・理由の外れ禁止）", () => {
    for (const [file, reason] of Object.entries(IMPORT_EXEMPT_SCAN_GUARDS)) {
      expect(reason.trim(), `${file} の除外理由が空`).not.toBe("");
    }
    // 除外リストに無いファイルは tests/ に実在しない（名前 typos の検出）
    const existing = new Set(walk("tests").map((p) => p.split(/[\\/]/).pop() ?? ""));
    const stale = Object.keys(IMPORT_EXEMPT_SCAN_GUARDS).filter((f) => !existing.has(f));
    expect(stale, `除外リストのファイルが存在しない: ${stale}`).toEqual([]);
  });
});
