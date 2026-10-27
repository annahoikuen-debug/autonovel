import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BeatSheetViewer } from './BeatSheetViewer';

/**
 * **実 API のレスポンス形状**（src/services/structure_validator.py:70,80）。
 * 修正前のテストは `missing_beats: ['midpoint_reversal']`（文字列配列）を
 * モックしていたため、**型不一致を検出できていなかった**。
 */
const REAL_API_RESPONSE = {
  pattern_key: 'exile_rise',
  structure_key: 'three_act',
  is_healthy: false,
  alignment: 0.667,
  missing_beats: [
    { key: 'midpoint_reversal', label: '中点反転', present: false, expected_phase: 0.52 },
    { key: 'aftermath', label: 'aftermath', present: false, expected_phase: 0.955 },
  ],
  climax: { ok: true, reason: '', climax_phase: 0.857 },
  pacing: { ok: true, reason: '', skew: 0.05 },
};

const mockFetch = (payload: unknown, ok = true) => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok,
      status: ok ? 200 : 500,
      json: async () => payload,
    })
  );
};

describe('BeatSheetViewer', () => {
  beforeEach(() => vi.unstubAllGlobals());

  it('**実 API 形状（dict 配列）でもクラッシュしない**', async () => {
    // 修正前: 「Objects are not valid as a React child」で落ちる
    mockFetch(REAL_API_RESPONSE);
    expect(() => render(<BeatSheetViewer bookId={1} patternKey="exile_rise" />)).not.toThrow();
    await waitFor(() => expect(screen.getByText(/必須ビートの充足状況/)).toBeTruthy());
  });

  it('欠落ビートをラベルで一覧表示する', async () => {
    mockFetch(REAL_API_RESPONSE);
    render(<BeatSheetViewer bookId={1} patternKey="exile_rise" />);
    await waitFor(() => expect(screen.getByText(/中点反転/)).toBeTruthy());
    expect(screen.getByText(/aftermath/)).toBeTruthy();
  });

  it('**充足度（alignment）を％表示する**（B12 の目的）', async () => {
    mockFetch(REAL_API_RESPONSE);
    render(<BeatSheetViewer bookId={1} patternKey="exile_rise" />);
    await waitFor(() => expect(screen.getByText(/66\.7|67/)).toBeTruthy());
  });

  it('充足 100% のとき「すべての必須ビート…正常」と表示する', async () => {
    mockFetch({ ...REAL_API_RESPONSE, is_healthy: true, alignment: 1, missing_beats: [] });
    render(<BeatSheetViewer bookId={1} />);
    await waitFor(() => expect(screen.getByText(/すべての必須ビート/)).toBeTruthy());
  });
});
