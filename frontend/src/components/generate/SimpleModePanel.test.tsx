import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { SimpleModePanel } from './SimpleModePanel';
import fs from 'fs';
import path from 'path';

const mockCards = [
  {
    card_id: 'tpl_exile_web',
    label: '⚔️ 追放ざまぁ',
    pattern: 'exile_rise',
    length: 'web_volume',
    market: 'web',
    style_key: 'style_web_standard',
  },
  {
    card_id: 'tpl_mystery_short',
    label: '🔍 事件の謎',
    pattern: 'detective_mystery',
    length: 'short',
    market: 'general',
    style_key: 'style_serious_fantasy',
  },
];

describe('SimpleModePanel テンプレートカード', () => {
  it('カードが選択式として表示される', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      json: async () => ({ cards: mockCards, genres: [], lengths: [], markets: [] }),
    }));
    render(<SimpleModePanel />);
    await waitFor(() => expect(screen.getByText('⚔️ 追放ざまぁ')).toBeTruthy());
  });

  it('カードを選ぶと話数が自動入力される', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      json: async () => ({
        cards: mockCards,
        genres: [],
        lengths: [{ key: 'web_volume', eps_range: [40, 40] }],
        markets: [],
      }),
    }));
    render(<SimpleModePanel />);
    await waitFor(() => screen.getByText('⚔️ 追放ざまぁ').click());
    await waitFor(() => expect(screen.getByDisplayValue('40')).toBeTruthy());
  });

  it('カードのハードコード select（fan/sf/...）が消えている', () => {
    const compPath = path.resolve(__dirname, 'SimpleModePanel.tsx');
    const src = fs.readFileSync(compPath, 'utf-8');
    expect(src).not.toContain('value="fan"');
  });
});
