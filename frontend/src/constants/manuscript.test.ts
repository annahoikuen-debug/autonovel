import { describe, expect, it } from 'vitest';
import { toManuscriptPresets, MANUSCRIPT_PRESETS, DEFAULT_LENGTH_PROFILES } from './manuscript';
import type { LengthProfile } from '../types/lengthProfile';

const profiles: LengthProfile[] = [
  { key: 'short', label: '短編', target_chars: 12000, eps_range: [1, 3], chars_per_ep: [4000, 12000], arc_count: [1, 1], min_beats: 5, hook_window_eps: 1, ending_contract: '' },
  { key: 'web_volume', label: 'Web1巻', target_chars: 100000, eps_range: [40, 40], chars_per_ep: [2500, 2500], arc_count: [3, 4], min_beats: 18, hook_window_eps: 3, ending_contract: '' },
];

describe('長さプロファイル → manuscript プリセット', () => {
  it('数値を落とさない（400字詰めの換算も行う）', () => {
    const presets = toManuscriptPresets(profiles);
    expect(presets[0]?.targetChars).toBe(12000);
    expect(presets[0]?.targetPages).toBe(30);
    expect(presets[1]?.targetChars).toBe(100000);
    expect(presets[1]?.targetPages).toBe(250);
  });

  it('custom は常に1枚だけ入る', () => {
    const presets = toManuscriptPresets(profiles);
    expect(presets.filter((p) => p.id === 'custom')).toHaveLength(1);
    expect(presets[presets.length - 1]?.id).toBe('custom');
  });

  it('lengthKey が保持される（構造テンプレートの選択に渡すため）', () => {
    const presets = toManuscriptPresets(profiles);
    expect(presets[0]?.lengthKey).toBe('short');
    expect(presets[1]?.lengthKey).toBe('web_volume');
  });

  it('空を渡すとローカルのフォールバックになる（API 未起動でもエディタが壊れない）', () => {
    const presets = toManuscriptPresets([]);
    expect(presets.length).toBe(DEFAULT_LENGTH_PROFILES.length + 1);
    expect(presets.some((p) => p.lengthKey === 'web_volume')).toBe(true);
  });

  it('文字数0の長編は警告閾値を1にして上限を外す', () => {
    const presets = toManuscriptPresets([
      { key: 'long_serial', label: '長編', target_chars: 0, eps_range: [100, 300], chars_per_ep: [2000, 2500], arc_count: [4, 8], min_beats: 24, hook_window_eps: 3, ending_contract: '' },
    ]);
    expect(presets[0]?.warningThreshold).toBe(1);
    expect(presets[0]?.maxPages).toBeUndefined();
  });

  it('既定エクスポートは custom を含む', () => {
    expect(MANUSCRIPT_PRESETS.some((p) => p.id === 'custom')).toBe(true);
  });
});
