import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { CompositionGraphRun } from '@/lib/composition-graph';
import { useCompositionGraphRunMonitor } from './useCompositionGraphRunMonitor';


function buildRun(status: CompositionGraphRun['status']): CompositionGraphRun {
  return {
    id: 'run-1',
    graph_id: 'graph-1',
    workspace_id: 'workspace-1',
    status,
    schema_version: 'composition_graph_run.v1',
    nodes: [],
    edges: [],
    node_states: {},
    diagnostics: [],
    created_at: '2026-06-13T00:00:00Z',
    updated_at: '2026-06-13T00:00:00Z',
  };
}


describe('useCompositionGraphRunMonitor', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('does not poll a terminal run', async () => {
    const fetchRun = vi.fn();
    const onRun = vi.fn();
    const { result } = renderHook(() =>
      useCompositionGraphRunMonitor({
        apiUrl: '',
        workspaceId: 'workspace-1',
        onRun,
        onError: vi.fn(),
        fetchRun,
      }),
    );

    act(() => result.current.subscribe(buildRun('succeeded')));
    await act(async () => vi.advanceTimersByTimeAsync(20000));

    expect(onRun).toHaveBeenCalledTimes(1);
    expect(fetchRun).not.toHaveBeenCalled();
  });

  it('uses bounded polling fallback and stops at terminal state', async () => {
    const fetchRun = vi.fn().mockResolvedValue({ run: buildRun('succeeded') });
    const onRun = vi.fn();
    const { result } = renderHook(() =>
      useCompositionGraphRunMonitor({
        apiUrl: '',
        workspaceId: 'workspace-1',
        onRun,
        onError: vi.fn(),
        fetchRun,
      }),
    );

    act(() => result.current.subscribe(buildRun('running')));
    await act(async () => vi.advanceTimersByTimeAsync(2000));
    await act(async () => vi.advanceTimersByTimeAsync(20000));

    expect(fetchRun).toHaveBeenCalledTimes(1);
    expect(onRun).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'succeeded' }));
  });

  it('prefers a stream connector before polling', async () => {
    const fetchRun = vi.fn();
    const disconnect = vi.fn();
    const streamConnector = vi.fn(() => disconnect);
    const { result } = renderHook(() =>
      useCompositionGraphRunMonitor({
        apiUrl: '',
        workspaceId: 'workspace-1',
        onRun: vi.fn(),
        onError: vi.fn(),
        fetchRun,
        streamConnector,
      }),
    );

    act(() => result.current.subscribe(buildRun('running')));
    await act(async () => vi.advanceTimersByTimeAsync(20000));

    expect(streamConnector).toHaveBeenCalledTimes(1);
    expect(fetchRun).not.toHaveBeenCalled();
  });

  it('aborts an in-flight poll when replacing the monitored run', async () => {
    const observed: { firstSignal?: AbortSignal } = {};
    const fetchRun = vi.fn(
      (
        _apiUrl: string,
        _workspaceId: string,
        _runId: string,
        signal?: AbortSignal,
      ): Promise<{ run: CompositionGraphRun }> => {
        observed.firstSignal = signal;
        return new Promise(() => undefined);
      },
    );
    const { result } = renderHook(() =>
      useCompositionGraphRunMonitor({
        apiUrl: '',
        workspaceId: 'workspace-1',
        onRun: vi.fn(),
        onError: vi.fn(),
        fetchRun,
      }),
    );

    act(() => result.current.subscribe(buildRun('running')));
    await act(async () => vi.advanceTimersByTimeAsync(2000));
    act(() => result.current.subscribe({ ...buildRun('running'), id: 'run-2' }));

    expect(observed.firstSignal?.aborted).toBe(true);
  });

  it('backs off polling while the page is hidden', async () => {
    const originalVisibilityState = document.visibilityState;
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
    });
    const fetchRun = vi.fn().mockResolvedValue({ run: buildRun('running') });
    const { result } = renderHook(() =>
      useCompositionGraphRunMonitor({
        apiUrl: '',
        workspaceId: 'workspace-1',
        onRun: vi.fn(),
        onError: vi.fn(),
        fetchRun,
      }),
    );

    act(() => result.current.subscribe(buildRun('running')));
    await act(async () => vi.advanceTimersByTimeAsync(2000));
    await act(async () => vi.advanceTimersByTimeAsync(9000));
    expect(fetchRun).toHaveBeenCalledTimes(1);

    await act(async () => vi.advanceTimersByTimeAsync(1000));
    expect(fetchRun).toHaveBeenCalledTimes(2);

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: originalVisibilityState,
    });
  });
});
