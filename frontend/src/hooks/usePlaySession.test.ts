/**
 * usePlaySession の単体テスト(Phase 0 S05)
 *
 * API 層(api/branches)はモックし、フックの状態遷移だけを検証する。
 * 完了条件: npm run test:ci の失敗数が現状の 9 から増えないこと(Q5)。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { usePlaySession } from './usePlaySession';
import * as branchesApi from '../api/branches';
import {
  BranchPlaySessionResponse,
  BranchPlayStateResponse,
  BranchPlayPlaythroughResponse,
} from '../types/branches';

vi.mock('../api/branches', () => ({
  startPlaySession: vi.fn(),
  fetchPlayState: vi.fn(),
  choosePlayChoice: vi.fn(),
  savePlayPoint: vi.fn(),
  loadPlayPoint: vi.fn(),
  endPlaySession: vi.fn(),
  fetchPlaythrough: vi.fn(),
}));

const mockStart = vi.mocked(branchesApi.startPlaySession);
const mockState = vi.mocked(branchesApi.fetchPlayState);
const mockChoose = vi.mocked(branchesApi.choosePlayChoice);
const mockSave = vi.mocked(branchesApi.savePlayPoint);
const mockLoad = vi.mocked(branchesApi.loadPlayPoint);
const mockEnd = vi.mocked(branchesApi.endPlaySession);
const mockHistory = vi.mocked(branchesApi.fetchPlaythrough);

const SESSION: BranchPlaySessionResponse = {
  session_id: '11111111-1111-1111-1111-111111111111',
  book_id: 1,
  branch_id: 1,
  current_node_id: 'node_1',
  status: 'active',
  updated_at: '2026-11-23T00:00:00Z',
};

const STATE_A: BranchPlayStateResponse = {
  session_id: SESSION.session_id,
  book_id: 1,
  branch_id: 1,
  current_node: {
    id: 'node_1',
    episode_num: 1,
    content: '最初のシーン',
    branch_type: 'choice',
    choices: [
      { id: 'c1', text: '剣を取る', conditions: [], target_node_id: 'node_2', effects: {}, priority: 0 },
      { id: 'c2', text: '逃げる', conditions: [], target_node_id: 'node_3', effects: {}, priority: 0 },
    ],
  },
  current_node_id: 'node_1',
  context: {},
  available_choices: [
    { id: 'c1', text: '剣を取る', conditions: [], target_node_id: 'node_2', effects: {}, priority: 0 },
    { id: 'c2', text: '逃げる', conditions: [], target_node_id: 'node_3', effects: {}, priority: 0 },
  ],
  save_points_count: 0,
  status: 'active',
  updated_at: '2026-11-23T00:00:00Z',
};

const STATE_B: BranchPlayStateResponse = {
  ...STATE_A,
  current_node_id: 'node_2',
  current_node: {
    id: 'node_2',
    episode_num: 2,
    content: '剣を取った後のシーン',
    branch_type: 'merge',
    choices: [],
  },
  available_choices: [],
  save_points_count: 1,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('usePlaySession', () => {
  it('start: セッション作成と状態取得が成功すると playing になる', async () => {
    mockStart.mockResolvedValue(SESSION);
    mockState.mockResolvedValue(STATE_A);

    const { result } = renderHook(() => usePlaySession());
    expect(result.current.phase).toBe('idle');

    await act(async () => {
      await result.current.start(1, 1);
    });

    expect(mockStart).toHaveBeenCalledWith({ book_id: 1, branch_id: 1 });
    expect(mockState).toHaveBeenCalledWith(SESSION.session_id);
    expect(result.current.phase).toBe('playing');
    expect(result.current.session).toEqual(SESSION);
    expect(result.current.state?.current_node_id).toBe('node_1');
    expect(result.current.busy).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('start: 失敗時は idle に戻り error が設定される', async () => {
    mockStart.mockRejectedValue(new Error('Branch not found for book'));

    const { result } = renderHook(() => usePlaySession());
    await act(async () => {
      await result.current.start(1, 999);
    });

    expect(result.current.phase).toBe('idle');
    expect(result.current.session).toBeNull();
    expect(result.current.error).toBe('Branch not found for book');
  });

  it('choose: 選択肢を実行すると状態が遷移する', async () => {
    mockStart.mockResolvedValue(SESSION);
    mockState.mockResolvedValue(STATE_A);
    mockChoose.mockResolvedValue(STATE_B);

    const { result } = renderHook(() => usePlaySession());
    await act(async () => {
      await result.current.start(1, 1);
    });

    await act(async () => {
      await result.current.choose('c1');
    });

    expect(mockChoose).toHaveBeenCalledWith(SESSION.session_id, 'c1');
    expect(result.current.state?.current_node_id).toBe('node_2');
    expect(result.current.phase).toBe('playing');
  });

  it('save / load: セーブポイントの保存と復元ができる', async () => {
    mockStart.mockResolvedValue(SESSION);
    mockState.mockResolvedValue(STATE_A);
    mockSave.mockResolvedValue({ ...STATE_A, save_points_count: 1 });
    mockLoad.mockResolvedValue(STATE_B);

    const { result } = renderHook(() => usePlaySession());
    await act(async () => {
      await result.current.start(1, 1);
    });

    await act(async () => {
      await result.current.save();
    });
    expect(result.current.state?.save_points_count).toBe(1);

    await act(async () => {
      await result.current.load(0);
    });
    expect(mockLoad).toHaveBeenCalledWith(SESSION.session_id, 0);
    expect(result.current.state?.current_node_id).toBe('node_2');
  });

  it('end: セッションを終了すると ended になる', async () => {
    mockStart.mockResolvedValue(SESSION);
    mockState.mockResolvedValue(STATE_A);
    mockEnd.mockResolvedValue({ ...SESSION, status: 'completed' });

    const { result } = renderHook(() => usePlaySession());
    await act(async () => {
      await result.current.start(1, 1);
    });

    await act(async () => {
      await result.current.end();
    });

    expect(mockEnd).toHaveBeenCalledWith(SESSION.session_id);
    expect(result.current.phase).toBe('ended');
    expect(result.current.session?.status).toBe('completed');
  });

  it('end: 失敗時は playing に戻る', async () => {
    mockStart.mockResolvedValue(SESSION);
    mockState.mockResolvedValue(STATE_A);
    mockEnd.mockRejectedValue(new Error('network'));

    const { result } = renderHook(() => usePlaySession());
    await act(async () => {
      await result.current.start(1, 1);
    });

    await act(async () => {
      await result.current.end();
    });

    expect(result.current.phase).toBe('playing');
    expect(result.current.error).toBe('network');
  });

  it('loadHistory: プレイスルー記録を取得できる', async () => {
    mockStart.mockResolvedValue(SESSION);
    mockState.mockResolvedValue(STATE_A);
    const playthrough: BranchPlayPlaythroughResponse = {
      session_id: SESSION.session_id,
      book_id: 1,
      branch_id: 1,
      history: [{ node_id: 'node_1' }],
      flags: { has_sword: true },
      variables: {},
      final_ending: null,
      saved_at: '2026-11-23T00:00:00Z',
    };
    mockHistory.mockResolvedValue(playthrough);

    const { result } = renderHook(() => usePlaySession());
    await act(async () => {
      await result.current.start(1, 1);
    });

    await act(async () => {
      await result.current.loadHistory();
    });

    expect(result.current.playthrough?.history).toHaveLength(1);
    expect(result.current.playthrough?.flags).toEqual({ has_sword: true });
  });

  it('reset: idle に戻り全状態がクリアされる', async () => {
    mockStart.mockResolvedValue(SESSION);
    mockState.mockResolvedValue(STATE_A);

    const { result } = renderHook(() => usePlaySession());
    await act(async () => {
      await result.current.start(1, 1);
    });
    await act(async () => {
      await result.current.reset();
    });

    expect(result.current.phase).toBe('idle');
    expect(result.current.session).toBeNull();
    expect(result.current.state).toBeNull();
    expect(result.current.playthrough).toBeNull();
  });

  it('セッション未開始での choose / save / load は API を呼ばない', async () => {
    const { result } = renderHook(() => usePlaySession());

    await act(async () => {
      await result.current.choose('c1');
      await result.current.save();
      await result.current.load(0);
    });

    expect(mockChoose).not.toHaveBeenCalled();
    expect(mockSave).not.toHaveBeenCalled();
    expect(mockLoad).not.toHaveBeenCalled();
  });

  it('choose 失敗時も状態と playing は維持される', async () => {
    mockStart.mockResolvedValue(SESSION);
    mockState.mockResolvedValue(STATE_A);
    mockChoose.mockRejectedValue(new Error('Invalid choice'));

    const { result } = renderHook(() => usePlaySession());
    await act(async () => {
      await result.current.start(1, 1);
    });

    await act(async () => {
      await result.current.choose('bad');
    });

    expect(result.current.state?.current_node_id).toBe('node_1');
    expect(result.current.phase).toBe('playing');
    expect(result.current.error).toBe('Invalid choice');
    // 次の操作成功でエラーが消える
    mockChoose.mockResolvedValue(STATE_B);
    await act(async () => {
      await result.current.choose('c1');
    });
    expect(result.current.error).toBeNull();
  });
});
