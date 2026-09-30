import type { ManuscriptTargetPreset } from '../types/manuscript';
import type { LengthProfile } from '../types/lengthProfile';

export const LEGACY_ID_BY_LENGTH_KEY: Record<string, string> = {
  short: 'shousetsu-gekkan',
  novella: 'shousetsu-subaru',
  single_volume: 'dengeki-bunko',
  web_volume: 'kakuyomu',
  long_serial: 'narou',
  series: 'series',
};

/**
 * ローカルのフォールバック。
 *
 * バックエンド（`config/story_spine/lengths.yaml`）が唯一のソースだが、
 * API が起動していないときエディタが使えなくなるのは望ましくないため、
 * 取得失敗時だけこの値をLocally使う。
 */
const FALLBACK_LENGTH_PROFILES: LengthProfile[] = [
  { key: 'short', label: '単発短編 (400字×30枚)', target_chars: 12000, eps_range: [1, 3], chars_per_ep: [4000, 12000], arc_count: [1, 1], min_beats: 5, hook_window_eps: 1, ending_contract: '閉じた結末。話末の引きは不要' },
  { key: 'novella', label: '中編 (400字×75枚)', target_chars: 30000, eps_range: [4, 10], chars_per_ep: [3000, 4000], arc_count: [1, 1], min_beats: 8, hook_window_eps: 1, ending_contract: '閉じた結末。1部構成' },
  { key: 'single_volume', label: '単行本1巻 (400字×138枚)', target_chars: 55000, eps_range: [15, 20], chars_per_ep: [3000, 4000], arc_count: [2, 3], min_beats: 12, hook_window_eps: 1, ending_contract: '1巻内で長期伏線を回収し、1巻末の引き' },
  { key: 'web_volume', label: 'Web連載1巻 (10万字)', target_chars: 100000, eps_range: [40, 40], chars_per_ep: [2500, 2500], arc_count: [3, 4], min_beats: 18, hook_window_eps: 3, ending_contract: '毎話末尾フック必須。話末の引きで次巻へ' },
  { key: 'long_serial', label: '長編連載 (25万字)', target_chars: 250000, eps_range: [100, 300], chars_per_ep: [2000, 2500], arc_count: [4, 8], min_beats: 24, hook_window_eps: 3, ending_contract: '4部以上。中期伏線を有効化し、巻を跨いで持ち越す' },
  { key: 'series', label: 'シリーズ (100万字〜)', target_chars: 1000000, eps_range: [300, 1000], chars_per_ep: [2000, 2500], arc_count: [5, 12], min_beats: 30, hook_window_eps: 5, ending_contract: '5部以上。巻単位の_goal と持ち越し' },
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
      const id = LEGACY_ID_BY_LENGTH_KEY[p.key] ?? String(p.key);
      return {
        id,
        lengthKey: String(p.key),
        label: p.label,
        targetPages: pages,
        targetChars: p.target_chars,
        warningThreshold: p.target_chars > 0 ? 0.9 : 1,
        ...(p.target_chars > 0 ? { maxPages: pages } : {}),
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

/** localStorage に旧 ID が入っていれば新 ID へ読み替える。 */
export function resolvePresetId(stored: string | null): string {
  if (!stored) return MANUSCRIPT_PRESETS[0].id;
  if (MANUSCRIPT_PRESETS.some((p) => p.id === stored)) return stored;
  const hit = Object.entries(LEGACY_ID_BY_LENGTH_KEY).find(([, legacy]) => legacy === stored);
  if (hit) return LEGACY_ID_BY_LENGTH_KEY[hit[0]];
  // 長さキー自体が入っていた場合（新しい既定）
  const hitByKey = MANUSCRIPT_PRESETS.find((p) => p.lengthKey === stored);
  if (hitByKey) return hitByKey.id;
  return MANUSCRIPT_PRESETS[0].id;
}

