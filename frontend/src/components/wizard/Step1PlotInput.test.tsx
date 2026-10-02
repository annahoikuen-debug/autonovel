import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { Step1PlotInput } from './Step1PlotInput';
import snapshot from '../../../tests/fixtures/planning_options.snapshot.json';

describe('Step1PlotInput GenreRegistry 統合', () => {
  it('growth_curve の選択肢が実在の値だけになる', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        json: async () => ({
          story_archetypes: ['王道ざまぁ（爽快感最大）'],
          growth_curves: ['最初からカンスト(無双)', '徐々に成長(王道)', '条件付き最強(ピーキー)'],
          cards: [],
          genres: [],
          lengths: [],
          markets: [],
        }),
      })
    );
    render(<Step1PlotInput onNext={() => {}} />);
    await waitFor(() => expect(screen.getByText(/徐々に成長\(王道\)/)).toBeTruthy());
    expect(screen.queryByText('段階的覚醒')).toBeNull();
    expect(screen.queryByText('王道ざまぁ（爽快感最大）')).toBeNull();
  });

  it('実 API スナップショットでも growth_curves のみが表示され story_archetypes は現れない', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        json: async () => snapshot,
      })
    );
    render(<Step1PlotInput onNext={() => {}} />);
    await waitFor(() => expect(screen.getByText(/最初からカンスト\(無双\)/)).toBeTruthy());
    expect(screen.queryByText('段階的覚醒')).toBeNull();
    expect(screen.queryByText('王道ざまぁ（爽快感最大）')).toBeNull();
  });
});
