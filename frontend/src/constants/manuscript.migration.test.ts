import { describe, expect, it } from 'vitest';
import {
  LEGACY_ID_BY_LENGTH_KEY,
  MANUSCRIPT_PRESETS,
  resolvePresetId,
  toManuscriptPresets,
} from './manuscript';
import type { LengthProfile } from '../types/lengthProfile';

const LENGTH_PROFILES: LengthProfile[] = [
  { key: 'short', label: '短編', target_chars: 12000, eps_range: [1, 3], chars_per_ep: [4000, 12000], arc_count: [1, 1], min_beats: 5, hook_window_eps: 1, ending_contract: '' },
  { key: 'long_serial', label: '長編', target_chars: 0, eps_range: [100, 300], chars_per_ep: [2000, 2500], arc_count: [4, 8], min_beats: 24, hook_window_eps: 3, ending_contract: '' },
];

describe('字数プリセットの ID 互換', () => {
  it('既存ユーザーの旧 ID が解決できる（localStorage を失効させない）', () => {
    // B9 で旧 ID が全置換され、既存全員の localStorage が無効化された
    expect(resolvePresetId('shousetsu-gekkan')).toBe(MANUSCRIPT_PRESETS[0].id);
    expect(resolvePresetId('shousetsu-subaru')).not.toBe('');
    expect(resolvePresetId('dengeki-bunko')).toBeDefined();
    expect(resolvePresetId('kakuyomu')).toBeDefined();
    expect(resolvePresetId('narou')).toBeDefined();
  });

  it('旧 ID に対応するプリセットが実際に存在する（空白 select にならない）', () => {
    for (const [lengthKey, legacyId] of Object.entries(LEGACY_ID_BY_LENGTH_KEY)) {
      const hit = MANUSCRIPT_PRESETS.find((p) => p.id === legacyId);
      if (lengthKey === 'series') continue; // 既存 localStorage には入らない
      expect(hit, `${lengthKey} の旧 ID ${legacyId} に対応するプリセットが無い`).toBeDefined();
    }
  });

  it('未知 ID は既定にフォールバックする（Undefined を渡さない）', () => {
    expect(resolvePresetId('存在しない')).toBe(MANUSCRIPT_PRESETS[0].id);
    expect(resolvePresetId(null)).toBe(MANUSCRIPT_PRESETS[0].id);
    expect(resolvePresetId('')).toBe(MANUSCRIPT_PRESETS[0].id);
  });

  it('解決結果は必ず実在するプリセットの ID', () => {
    for (const stored of ['shousetsu-gekkan', 'kakuyomu', 'custom', 'garbage', null]) {
      const id = resolvePresetId(stored);
      expect(MANUSCRIPT_PRESETS.some((p) => p.id === id)).toBe(true);
    }
  });
});

describe('maxPages の付与条件', () => {
  it('字数自由（target_chars=0）の長編には上限を付けない', () => {
    const presets = toManuscriptPresets(LENGTH_PROFILES);
    const long = presets.find((p) => p.lengthKey === 'long_serial');
    expect(long).toBeDefined();
    expect(long!.maxPages).toBeUndefined(); // 0 ではなく「付けない」
    expect(long!.warningThreshold).toBe(1);
  });

  it('字数があるプリセットには 400 字詰めの枚数上限を付ける', () => {
    const presets = toManuscriptPresets(LENGTH_PROFILES);
    const short = presets.find((p) => p.lengthKey === 'short');
    expect(short!.maxPages).toBe(30); // 12000 / 400
  });
});

describe('フォールバックプロファイルの整合', () => {
  it('フォールバックは lengths.yaml と乖離しない（series を含む）', () => {
    expect(MANUSCRIPT_PRESETS.some((p) => p.lengthKey === 'series')).toBe(true);
    expect(MANUSCRIPT_PRESETS.some((p) => p.lengthKey === 'long_serial' && p.targetChars === 0)).toBe(false);
  });
});
