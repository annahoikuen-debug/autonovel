import { describe, it, expect } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? walk(p) : p.endsWith(".test.ts") || p.endsWith(".test.tsx") ? [p] : [];
  });
}

describe("tautology guard (frontend)", () => {
  it("src を import しないテストが無いこと", () => {
    const offenders: string[] = [];
    for (const p of walk("tests")) {
      // 本テスト自身および e2e (Playwright) は除外
      if (p.includes("tautology.guard.test.ts") || p.includes("tests\\e2e") || p.includes("tests/e2e")) {
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
});
