import { describe, it, expect } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

/**
 * フロントのテストが **生 fetch の古い契約** に固定されていないことの archangel。
 *
 *  PLAN_H1R H1R-2:
 *  H1 Step H8 は `frontend/src/api/graph.ts` の生 `fetch(` を `apiFetch(` に移行した
 *  （認証ヘッダ漏えい修正）。`apiFetch` は必ず `fetch(endpoint, { headers, signal })` と
 *  **第 2 引数を付ける**ため、`toHaveBeenCalledWith("<url>")` の 1 引数で検査する
 *  テストは、移行のたびに落ちる。
 *
 *  実際に `tests/api/graph.test.ts` がその状態で 2 件赤になり、H1 の受入基準 A8 を
 *  「既存の FE 不具合」と誤診させていた。同じ型の失敗を再発させない。
 */

const TEST_ROOTS = ["tests", "src"];
const TEST_FILE_RE = /\.(test|spec)\.tsx?$/;

/**
 * 本ファイル自身は counter-example（違反例）を docstring と自己検証に
 * 意図的に含むため、探索対象から外す。外さないと永久に赤になる。
 */
const SELF = "apiFetchContract.guard.test";

/** `toHaveBeenCalledWith(` の出現位置をすべて列挙する。 */
function findCallSites(src: string): number[] {
  const out: number[] = [];
  const needle = "toHaveBeenCalledWith(";
  let idx = src.indexOf(needle);
  while (idx !== -1) {
    out.push(idx);
    idx = src.indexOf(needle, idx + needle.length);
  }
  return out;
}

/**
 * 開位置 start（"toHaveBeenCalledWith(" の '(' の直後）から
 * 対応する ')' までを-balanced かるく読む。文字列・コメントはスキップ。
 */
function readArguments(src: string, openIdx: number): string | null {
  let depth = 0;
  let quote: string | null = null;
  let inLineComment = false;
  let inBlockComment = false;
  for (let i = openIdx; i < src.length; i++) {
    const ch = src[i];
    const next = src[i + 1];

    if (inLineComment) {
      if (ch === "\n") inLineComment = false;
      continue;
    }
    if (inBlockComment) {
      if (ch === "*" && next === "/") {
        inBlockComment = false;
        i++;
      }
      continue;
    }
    if (quote) {
      if (ch === "\\") {
        i++;
        continue;
      }
      if (ch === quote) quote = null;
      continue;
    }
    if (ch === "/" && next === "/") {
      inLineComment = true;
      i++;
      continue;
    }
    if (ch === "/" && next === "*") {
      inBlockComment = true;
      i++;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") {
      quote = ch;
      continue;
    }
    if (ch === "(" || ch === "[" || ch === "{") depth++;
    if (ch === ")" || ch === "]" || ch === "}") {
      depth--;
      if (depth === 0) return src.slice(openIdx, i);
    }
  }
  return null;
}

/** トップレベルの引数が何個あるか（呼び出し全体の外側の括弧は数えない）。 */
function countTopLevelArgs(argText: string): number {
  // readArguments は外側の '(' を含み、末尾の ')' を除いて返す。
  // ここでも同じ範囲に揃えるため、先頭の '(' を外して数える。
  let body = argText.trim();
  if (body.startsWith("(")) body = body.slice(1);

  let depth = 0;
  let quote: string | null = null;
  let count = 1;
  let seenNonSpace = false;
  for (let i = 0; i < body.length; i++) {
    const ch = body[i];
    if (quote) {
      if (ch === "\\") {
        i++;
        continue;
      }
      if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") {
      quote = ch;
      seenNonSpace = true;
      continue;
    }
    if ("([{".includes(ch)) depth++;
    if (")]}".includes(ch)) depth--;
    if (ch === "," && depth === 0) {
      count++;
      continue;
    }
    if (!/\s/.test(ch)) seenNonSpace = true;
  }
  return seenNonSpace ? count : 0;
}

function walk(dir: string, out: string[] = []): string[] {
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const entry of entries) {
    const full = join(dir, entry);
    let st;
    try {
      st = statSync(full);
    } catch {
      continue;
    }
    if (st.isDirectory()) {
      if (["node_modules", "dist", "coverage", ".git"].includes(entry)) continue;
      walk(full, out);
    } else if (TEST_FILE_RE.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

function allTestFiles(): string[] {
  const files: string[] = [];
  for (const root of TEST_ROOTS) walk(root, files);
  return files.filter((f) => !f.includes(SELF));
}

describe("apiFetch 契約の archangel", () => {
  it("FE テストは fetch を 1 引数で検査していない（stale 契約の検出）", () => {
    const offenders: string[] = [];
    for (const file of allTestFiles()) {
      const src = readFileSync(file, "utf8");
      for (const at of findCallSites(src)) {
        // 検査対象のオブジェクトが fetch 系かを見る（他の spy は対象外）。
        const before = src.slice(Math.max(0, at - 160), at);
        if (!/\bfetch\b/.test(before)) continue;
        const argText = readArguments(src, at + "toHaveBeenCalledWith".length);
        if (argText === null) continue;
        const args = countTopLevelArgs(argText);
        // 1 引数 = 生 fetch の契約（apiFetch は必ず第 2 引数を付ける）
        if (args === 1) {
          const line = src.slice(0, at).split("\n").length;
          offenders.push(`${file}:${line}: ${argText.replace(/\s+/g, " ").slice(0, 80)}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("検出器は 1 引数と 2 引数を区別できる（自己検証 / P4）", () => {
    const cases: Array<[string, number]> = [
      ['toHaveBeenCalledWith("/api/graph?graph_name=x")', 1],
      ['toHaveBeenCalledWith("/api/graph", expect.objectContaining({ h: expect.any(Headers) }))', 2],
      ['toHaveBeenCalledWith(\n  "/api/graph",\n  expect.objectContaining({ h: 1 })\n)', 2],
    ];
    for (const [src, expected] of cases) {
      const argText = readArguments(src, src.indexOf("toHaveBeenCalledWith(") + "toHaveBeenCalledWith".length);
      expect(argText, `readArguments が null: ${src}`).not.toBeNull();
      expect(countTopLevelArgs(argText as string), src).toBe(expected);
    }
  });

  it("文字列内のカンマ・括弧を引数境界として数えない（自己検証 / P4）", () => {
    const tricky = 'toHaveBeenCalledWith("/api/x?a=1,b=2", { headers: h })';
    const argText = readArguments(
      tricky,
      tricky.indexOf("toHaveBeenCalledWith(") + "toHaveBeenCalledWith".length
    ) as string;
    expect(countTopLevelArgs(argText)).toBe(2);
  });

  it("fetch 以外の spy は対象外になる（偽陽性 prevention / P4）", () => {
    const src = 'expect(spy).toHaveBeenCalledWith(1)';
    const at = src.indexOf("toHaveBeenCalledWith(");
    const before = src.slice(Math.max(0, at - 160), at);
    expect(/\bfetch\b/.test(before)).toBe(false);
  });
});