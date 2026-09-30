import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BeatSheetViewer } from './BeatSheetViewer';

describe('BeatSheetViewer 構成充足度', () => {
  it('充足度と欠落ビートが提示される', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          pattern_key: 'exile_rise',
          missing_beats: ['midpoint_reversal'],
          climax: { ok: true },
          pacing: { skew: 0.1, ok: true },
          is_healthy: false,
        }),
      })
    );
    render(<BeatSheetViewer bookId={1} patternKey="exile_rise" />);
    await waitFor(() => expect(screen.getByText(/midpoint_reversal/)).toBeTruthy());
  });
});
