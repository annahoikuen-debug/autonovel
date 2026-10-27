/**
 * R7/R8 の回帰テスト：ライト/セピアテーマでも UI が追従すること。
 *
 * 以前は入力欄の背景が `rgba(15,23,42,0.8)` でハードコードされ、
 * モバイルナビも `bg-slate-950/95` 固定だったため、
 * テーマを切り替えても入力欄とモバイルナビが黒のままだった。
 */
import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

describe("R7/R8: テーマ対応（CSS変数化）", () => {
  const css = fs.readFileSync(
    path.resolve(process.cwd(), "src/index.css"),
    "utf-8",
  );

  it("入力欄が CSS 変数を使い、ハードコードされた暗色背景を持たない", () => {
    // .input/.textarea/.select 定義部にダーク固定色が残っていないこと
    const inputBlock = /\.input,\s*\.textarea,\s*\.select\s*\{[^}]*\}/s.exec(css);
    expect(inputBlock).not.toBeNull();
    expect(inputBlock![0]).not.toContain("rgba(15, 23, 42");
    expect(inputBlock![0]).toContain("var(--input-bg)");
  });

  it("全 3 テーマに --input-bg が定義されている", () => {
    const definitions = css.match(/--input-bg:/g) ?? [];
    // dark / light / sepia の 3 つ
    expect(definitions.length).toBeGreaterThanOrEqual(3);
  });

  it("モバイルナビが Tailwind のダーク固定色を使っていない", () => {
    const fs2 = fs.readFileSync(
      path.resolve(process.cwd(), "src/components/mobile/MobileBottomNav.tsx"),
      "utf-8",
    );
    // コメントは「もともとこうだったか」を説明しているだけなので、
    // 実際の JSX（className 属性）だけを対象に判定する。
    const jsxOnly = fs2
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\/\/[^\n]*/g, "");
    expect(jsxOnly).not.toContain("bg-slate-950");
    expect(jsxOnly).not.toContain("text-slate-");
    expect(jsxOnly).toContain("var(--surface-2)");
  });

  it("モバイルクイックバーもダーク固定色を使っていない", () => {
    const fs3 = fs.readFileSync(
      path.resolve(process.cwd(), "src/components/mobile/MobileQuickActionBar.tsx"),
      "utf-8",
    );
    const jsxOnly = fs3
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\/\/[^\n]*/g, "");
    expect(jsxOnly).not.toContain("bg-slate-900");
    expect(jsxOnly).not.toContain("bg-slate-800");
  });
});
