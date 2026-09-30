import { describe, expect, it } from 'vitest';
import snapshot from '../../fixtures/planning_options.snapshot.json';
import { toManuscriptPresets } from '../../../src/constants/manuscript';
import type { LengthProfile } from '../../../src/types/lengthProfile';

/**
 * **サーバーが実際に返すレスポンス**（scripts/export_planning_options.py の出力）。
 * FE テストのモックを自分で作らない原則の唯一の例外がこれ。
 */
const raw = snapshot as Record<string, unknown>;

describe('/api/config/planning_options との契約', () => {
  it('スナップショットは cards / lengths / genres を持つ', () => {
    expect(raw).toHaveProperty('cards');
    expect(raw).toHaveProperty('lengths');
    expect(raw).toHaveProperty('genres');
  });

  it('**全カードが card_id を持つ**（Highlight 判定の前提）', () => {
    const cards = raw.cards as Array<Record<string, unknown>>;
    expect(cards.length).toBeGreaterThan(0);
    for (const c of cards) {
      expect(typeof c.card_id).toBe('string');
      expect(c.card_id).not.toBe('');
    }
  });

  it('**growth_curves が存在し非空**（成長曲線 select の唯一の供給元）', () => {
    expect(raw).toHaveProperty('growth_curves');
    const curves = Object.values(raw.growth_curves as Record<string, string>);
    expect(curves.length).toBeGreaterThan(0);
  });

  it('**lengths を FE のプリセットに変換できる**', () => {
    const lengths = Object.values(raw.lengths as Record<string, LengthProfile>);
    const presets = toManuscriptPresets(lengths);
    expect(presets.length).toBeGreaterThanOrEqual(6);
    expect(presets.every((p) => typeof p.id === 'string' && p.id !== '')).toBe(true);
  });

  it('patterns の beat キーがすべて patterns 内で定義されている', () => {
    const patterns = raw.patterns as Record<string, { beats?: Array<{ key: string }> }>;
    const vocab = Object.keys(raw.beat_vocabulary as Record<string, unknown>);
    for (const [pk, pat] of Object.entries(patterns)) {
      for (const b of pat.beats ?? []) {
        expect(vocab, `${pk}.${b.key}`).toContain(b.key);
      }
    }
  });
});
