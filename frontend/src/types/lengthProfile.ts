/**
 * 構造テンプレート（STORY_SPINE）の長さ階層の型定義。
 *
 * 実体はバックエンド（`config/story_spine/lengths.yaml`）が単一のソース。
 * フロントは取得結果を受け取るだけで、数値をハードコードしない。
 */

export type LengthKey =
  | 'short'
  | 'novella'
  | 'single_volume'
  | 'web_volume'
  | 'long_serial'
  | 'series';

export interface LengthProfile {
  key: LengthKey | string;
  label: string;
  target_chars: number;
  eps_range: [number, number];
  chars_per_ep: [number, number];
  arc_count: [number, number];
  min_beats: number;
  hook_window_eps: number;
  ending_contract: string;
}
