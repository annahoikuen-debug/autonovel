/**
 * 改善案1・2・4: SimpleModePanel のメトリクス表示連携テスト。
 *
 * 生成タスク完了結果（useNovelGeneration.extractTaskMetrics）から
 * SimpleModePanel へ渡されたメトリクスが、意図どおり表示 / 非表示になることを検証する。
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SimpleModePanel, {
  type HookMetricsUI,
  type CTRMetricsUI,
} from "../../src/components/generate/SimpleModePanel";

vi.mock("../../src/api/styleApi", () => ({
  fetchStylePresets: vi.fn().mockResolvedValue([]),
  distillStyleFromText: vi.fn(),
}));

// SimpleModePanel 内の planning_options fetch（jsdom には fetch 環境が無い場合があるためスタブ）
beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ cards: [], lengths: [], genres: [] }),
    }),
  );
});

const crisisHook: HookMetricsUI = {
  ep_num: 1,
  hook_type: "crisis",
  score: 90,
  requires_rewrite: false,
  reason: "危機で締められています",
  tail_sentence: "背後から刃が振り下ろされた！",
};

const peacefulHook: HookMetricsUI = {
  ep_num: 1,
  hook_type: "peaceful",
  score: 35,
  requires_rewrite: true,
  reason: "平穏な就寝で終了しています",
  tail_sentence: "おやすみ。",
};

const goodCtr: CTRMetricsUI = {
  title_score: 80,
  catchphrase_score: 70,
  title_needs_improvement: false,
  catchphrase_needs_improvement: false,
  syntax_type: "追放ざまぁ",
};

const weakCtr: CTRMetricsUI = {
  title_score: 25,
  catchphrase_score: 30,
  title_needs_improvement: true,
  catchphrase_needs_improvement: true,
  syntax_type: "一般",
};

describe("SimpleModePanel メトリクス連携", () => {
  it("hookMetrics=null ではフックパネルを表示しない（フラグOFF契約）", () => {
    render(<SimpleModePanel hookMetrics={null} />);
    expect(screen.queryByText(/序盤フック・章末引き診断/)).toBeNull();
  });

  it("hookMetrics あり・引きOK のときスコアとバッジを表示する", () => {
    render(<SimpleModePanel hookMetrics={crisisHook} />);
    expect(screen.getByText(/序盤フック・章末引き診断（第1話）/)).toBeDefined();
    expect(screen.getByText("引き OK")).toBeDefined();
    expect(screen.getByText("90 点")).toBeDefined();
  });

  it("requires_rewrite=true のとき「引き要改善」と改善案を表示する", () => {
    render(<SimpleModePanel hookMetrics={peacefulHook} />);
    expect(screen.getByText("引き要改善")).toBeDefined();
    expect(screen.getByText(/危機 \/ 衝撃の真実 \/ 反撃の狼煙/)).toBeDefined();
  });

  it("ctrMetrics=null では CTR パネルを表示しない（フラグOFF契約）", () => {
    render(<SimpleModePanel ctrMetrics={null} />);
    expect(screen.queryByText(/タイトル・キャッチコピーCTR診断/)).toBeNull();
  });

  it("ctrMetrics あり・スコア良好のとき構文タイプを表示し改善案は出さない", () => {
    render(<SimpleModePanel ctrMetrics={goodCtr} ctrSuggestions={[]} />);
    expect(screen.getByText(/タイトル・キャッチコピーCTR診断/)).toBeDefined();
    expect(screen.getByText("追放ざまぁ")).toBeDefined();
    expect(screen.queryByText(/クリックで適用/)).toBeNull();
  });

  it("title_needs_improvement=true で改善案を表示し、クリックでコールバックが呼ばれる", async () => {
    const user = userEvent.setup();
    const onApply = vi.fn();
    render(
      <SimpleModePanel
        ctrMetrics={weakCtr}
        ctrSuggestions={["案A", "案B", "案C"]}
        onApplyCtrSuggestion={onApply}
      />,
    );
    expect(screen.getByText(/クリックで適用/)).toBeDefined();
    await user.click(screen.getByText("案A"));
    expect(onApply).toHaveBeenCalledWith("案A");
  });

  it("tagSuggestions=[] ではタグパネルを表示しない（フラグOFF契約）", () => {
    render(<SimpleModePanel tagSuggestions={[]} />);
    expect(screen.queryByText(/カクヨム推奨タグ/)).toBeNull();
  });

  it("tagSuggestions ありのときタグチップを表示する", () => {
    render(<SimpleModePanel tagSuggestions={["異世界転生", "チート", "ざまぁ"]} />);
    expect(screen.getByText(/カクヨム推奨タグ/)).toBeDefined();
    expect(screen.getByText("異世界転生")).toBeDefined();
    expect(screen.getByText("チート")).toBeDefined();
    expect(screen.getByText("ざまぁ")).toBeDefined();
  });
});
