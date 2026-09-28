import { describe, expect, it } from "vitest";
import {
  looksLikeTaigenStop,
  measureStyleMetrics,
  splitSentences,
  toPercent,
} from "../../../src/utils/styleMetrics";

describe("splitSentences", () => {
  it("splits on Japanese sentence enders", () => {
    const result = splitSentences("彼は剣を抜いた。彼女は笑った！ETER");
    expect(result).toEqual(["彼は剣を抜いた。", "彼女は笑った！", "ETER"]);
  });

  it("keeps punctuation inside quotes together", () => {
    const result = splitSentences("彼は言った。「やあ。よろしく！」");
    expect(result.length).toBeGreaterThanOrEqual(1);
    expect(result.join("")).toContain("やあ。");
  });

  it("returns empty for blank input", () => {
    expect(splitSentences("")).toEqual([]);
    expect(splitSentences("   \n  ")).toEqual([]);
  });
});

describe("looksLikeTaigenStop", () => {
  it("treats verb-ending sentences as not taigen", () => {
    expect(looksLikeTaigenStop("彼は剣を抜いた。")).toBe(false);
    expect(looksLikeTaigenStop("雨が止んだ。")).toBe(false);
  });

  it("treats bare noun-ending sentences as taigen candidates", () => {
    expect(looksLikeTaigenStop("十字架。")).toBe(true);
    expect(looksLikeTaigenStop("静寂。")).toBe(true);
  });
});

describe("measureStyleMetrics", () => {
  it("returns zeroed metrics for empty text", () => {
    const m = measureStyleMetrics("");
    expect(m.sentenceCount).toBe(0);
    expect(m.averageSentenceLength).toBe(0);
    expect(m.dialogueRatio).toBe(0);
    expect(m.taigenStopRatio).toBe(0);
    expect(m.charCount).toBe(0);
  });

  it("measures sentence count and average length", () => {
    const m = measureStyleMetrics("あいうえお。かきくけこ。さしすせそ。");
    expect(m.sentenceCount).toBe(3);
    expect(m.averageSentenceLength).toBeCloseTo(5, 5);
  });

  it("computes dialogue ratio from quoted sentences", () => {
    const m = measureStyleMetrics("彼は笑った。「やあ」と彼は言った。");
    expect(m.dialogueRatio).toBeGreaterThan(0);
    expect(m.dialogueRatio).toBeLessThanOrEqual(1);
  });

  it("keeps every ratio within 0..1", () => {
    const samples = [
      "「こんにちは。」彼は言った。",
      "静寂。重い。赤い血が空に散った。",
      "走れ！",
      "あ" + "い".repeat(500) + "。",
    ];
    for (const s of samples) {
      const m = measureStyleMetrics(s);
      expect(m.dialogueRatio).toBeGreaterThanOrEqual(0);
      expect(m.dialogueRatio).toBeLessThanOrEqual(1);
      expect(m.taigenStopRatio).toBeGreaterThanOrEqual(0);
      expect(m.taigenStopRatio).toBeLessThanOrEqual(1);
    }
  });

  it("handles non-string input without throwing", () => {
    expect(() => measureStyleMetrics(undefined as unknown as string)).not.toThrow();
  });
});

describe("toPercent", () => {
  it("rounds a ratio to a percentage", () => {
    expect(toPercent(0.3456)).toBe(35);
    expect(toPercent(0)).toBe(0);
    expect(toPercent(1)).toBe(100);
  });
});
