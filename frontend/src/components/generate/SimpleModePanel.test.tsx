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
  // `lengths` は実データ（config/story_spine/LENGTHS の web_volume）と同じ形にする。
  // chars_per_ep が無いとカードの選択で目標文字数が更新されない
  // （SimpleModePanel.tsx:179-181）。
  lengths: { web_volume: { key: 'web_volume', eps_range: [40, 40], chars_per_ep: [2500, 2500] } },
  genres: {},
};

const setup = (payload: unknown = REAL_API_CARDS, props: Record<string, unknown> = {}) => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => payload })
  );
  return render(<SimpleModePanel {...props} />);
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
    // style_key の 반영先は startGeneration / startStreaming に渡る引数
    // （SimpleModePanel.tsx:451,462）なので、その出力で観測する。
    //
    // なお「文体の雰囲気」select dropdown で hot_blooded を直接見ることはできない。
    // 構造テンプレートの style_key（hot_blooded / romantic / cool_headed / comedy /
    // healing / dark の全 6 種）は src.config.STYLE_DEFINITIONS に存在せず、
    // select の option に無いためブラウザは先頭要素（auto）に丸めてしまう。
    // つまり「画面は AIにおまかせと表示しているのに hot_blooded で生成する」不一致が
    // 現状あり、その食い違いを隠さないために出力側で検証する。
    const startGeneration = vi.fn();
    const startStreaming = vi.fn();
    setup(REAL_API_CARDS, { startGeneration, startStreaming });
    vi.mocked(fetch).mockClear();

    fireEvent.click((await screen.findByText('追放ざまぁ（Web連載・1巻40話）')).closest('div[style]')!);

    // 1話あたりの目標文字数（chars_per_ep: [2500, 2500] の中央値）
    await waitFor(() => {
      expect(screen.getByDisplayValue('2500')).toBeTruthy();
    });

    // 目標話数もカードから入していること（eps_range: [40, 40]）
    expect((screen.getByLabelText(/目標話数/) as HTMLInputElement).value).toBe('40');

    // 執筆ボタンが style_key を持ち去ること
    fireEvent.click(screen.getByTestId('btn-easy-generate'));
    expect(startGeneration).toHaveBeenCalledWith('hot_blooded');
    fireEvent.click(screen.getByTestId('btn-streaming-generate'));
    expect(startStreaming).toHaveBeenCalledWith('hot_blooded');
  });
});
