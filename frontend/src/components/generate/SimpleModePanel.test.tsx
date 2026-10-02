import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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

/**
 * **サーバーが実際に返す形**（src/backend/routers/misc.py:F1 で `card_id` を付与したもの）。
 * 修正前のテストは `card_id: 'tpl_exile_web'` を捏造して渡していたため、
 * 実データでハイライトが無効になることに気づけなかった。
 */
const REAL_API_CARDS = {
  cards: [
    {
      card_id: 'tpl_exile_web',
      label: '追放ざまぁ（Web連載・1巻40話）',
      blurb: '...',
      pattern: 'exile_rise',
      length: 'web_volume',
      market: 'web',
      style_key: 'hot_blooded',
      source: 'existing',
    },
    {
      card_id: 'tpl_mystery_short',
      label: '密室殺人（短編）',
      blurb: '...',
      pattern: 'detective_mystery',
      length: 'short',
      market: 'single_shot',
      style_key: 'restrained',
      source: 'existing',
    },
  ],
  lengths: { web_volume: { key: 'web_volume', eps_range: [40, 40] } },
  genres: {},
};

const setup = (payload: unknown = REAL_API_CARDS) => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => payload })
  );
  return render(<SimpleModePanel />);
};

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

describe('SimpleModePanel カード選択', () => {
  beforeEach(() => vi.unstubAllGlobals());

  it('**カードを選ぶと選択ハイライトが付く**（実 API 形状で検証）', async () => {
    setup();
    const card = await screen.findByText('追放ざまぁ（Web連載・1巻40話）');
    const tile = card.closest('div[style]')!;
    fireEvent.click(tile);
    await waitFor(() => {
      expect(tile.getAttribute('style')).toContain('2px solid'); // 選択枠
    });
  });

  it('**異なるカードを選ぶと前のカードのハイライトが消える**', async () => {
    setup();
    const a = (await screen.findByText('追放ざまぁ（Web連載・1巻40話）')).closest('div[style]')!;
    const b = (await screen.findByText('密室殺人（短編）')).closest('div[style]')!;
    fireEvent.click(a);
    fireEvent.click(b);
    await waitFor(() => {
      expect(b.getAttribute('style')).toContain('2px solid');
      expect(a.getAttribute('style')).toContain('1px solid');
    });
  });

  it('**カード選択で話数が length.eps_range から自動入力される**', async () => {
    setup();
    fireEvent.click((await screen.findByText('追放ざまぁ（Web連載・1巻40話）')).closest('div[style]')!);
    const eps = await screen.findByLabelText(/目標話数/);
    await waitFor(() => expect((eps as HTMLInputElement).value).toBe('40'));
  });

  it('カード選択で style_key と chars_per_ep が反映される', async () => {
    setup();
    fireEvent.click((await screen.findByText('追放ざまぁ（Web連載・1巻40話）')).closest('div[style]')!);
    await waitFor(() => {
      expect(screen.getByDisplayValue('hot_blooded')).toBeTruthy();
      expect(screen.getByDisplayValue('2500')).toBeTruthy();
    });
  });
});
