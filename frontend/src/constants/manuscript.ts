import type { ManuscriptTargetPreset } from '../types/manuscript';
import type { LengthProfile } from '../types/lengthProfile';

/**
 * ローカルのフォールバック。
 *
 * バックエンド（`config/story_spine/lengths.yaml`）が唯一のソースだが、
 * API が起動していないときエディタが使えなくなるのは望ましくないため、
 * 取得失敗時だけこの値をLocally使う。
 */
const FALLBACK_LENGTH_PROFILES: LengthProfile[] = [
  { key: 'short', label: '小説現代・新人賞 (400字×30枚)', target_chars: 12000, eps_range: [1, 3], chars_per_ep: [4000, 12000], arc_count: [1, 1], min_beats: 5, hook_window_eps: 1, ending_contract: '' },
  { key: 'novella', label: '小説すばる・新人賞 (400字×50枚)', target_chars: 20000, eps_range: [4, 10], chars_per_ep: [3000, 4000], arc_count: [1, 1], min_beats: 8, hook_window_eps: 1, ending_contract: '' },
  { key: 'single_volume', label: '電撃文庫・大賞 (400字×100枚)', target_chars: 40000, eps_range: [15, 20], chars_per_ep: [3000, 4000], arc_count: [2, 3], min_beats: 12, hook_window_eps: 1, ending_contract: '' },
  { key: 'web_volume', label: 'カクヨム・コンテスト (10万字以内)', target_chars: 100000, eps_range: [40, 40], chars_per_ep: [2500, 2500], arc_count: [3, 4], min_beats: 18, hook_window_eps: 3, ending_contract: '' },
  { key: 'long_serial', label: '小説家になろう・長編 (文字数自由)', target_chars: 0, eps_range: [100, 300], chars_per_ep: [2000, 2500], arc_count: [4, 8], min_beats: 24, hook_window_eps: 3, ending_contract: '' },
];

const CHARS_PER_PAGE = 400;

/** 400字詰めのページ数を求める。 */
const toPages = (chars: number): number =>
  chars > 0 ? Math.round(chars / CHARS_PER_PAGE) : 0;

/**
 * 長さプロファイル（バックエンド由来）をエディタのプリセットに変換する。
 * `custom`（サーバー設定ではないユーザー設定）は常に1枚だけ末尾に足す。
 */
export function toManuscriptPresets(profiles: LengthProfile[]): ManuscriptTargetPreset[] {
  const source = profiles && profiles.length > 0 ? profiles : FALLBACK_LENGTH_PROFILES;
  const presets: ManuscriptTargetPreset[] = source
    .filter((p) => p.key !== 'custom')
    .map((p) => {
      const pages = toPages(p.target_chars);
      return {
        id: String(p.key),
        lengthKey: String(p.key),
        label: p.label,
        targetPages: pages,
        targetChars: p.target_chars,
        warningThreshold: p.target_chars > 0 ? 0.9 : 1,
        ...(p.eps_range[1] > 0 ? { maxPages: toPages(p.target_chars) } : {}),
      };
    });

  presets.push({
    id: 'custom',
    label: 'カスタム設定…',
    targetPages: 0,
    targetChars: 0,
    warningThreshold: 0.9,
  });
  return presets;
}

/**
 * バックエンドから長さプロファイルを取得する。
 * 失敗時はローカルのフォールバックを返す（エディタを壊さない）。
 */
export async function fetchLengthProfiles(): Promise<LengthProfile[]> {
  try {
    const res = await fetch('/api/config/planning_options');
    if (!res.ok) return FALLBACK_LENGTH_PROFILES;
    const data = (await res.json()) as { lengths?: Record<string, LengthProfile> };
    const lengths = data.lengths ? Object.values(data.lengths) : [];
    return lengths.length > 0 ? lengths : FALLBACK_LENGTH_PROFILES;
  } catch {
    return FALLBACK_LENGTH_PROFILES;
  }
}

/** 同期的に参照する既定値（UI の初期描画用）。 */
export const DEFAULT_LENGTH_PROFILES: LengthProfile[] = FALLBACK_LENGTH_PROFILES;

export const MANUSCRIPT_PRESETS: ManuscriptTargetPreset[] =
  toManuscriptPresets(FALLBACK_LENGTH_PROFILES);

