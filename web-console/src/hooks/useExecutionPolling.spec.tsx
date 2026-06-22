import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  extractExecutionStatusFromUpdate,
  isTerminalExecutionStatus,
  resolveExecutionPollingIntervalMs,
  useExecutionPolling,
} from './useExecutionPolling';


describe('useExecutionPolling helpers', () => {
  it('classifies terminal execution statuses', () => {
    expect(isTerminalExecutionStatus('completed')).toBe(true);
    expect(isTerminalExecutionStatus('cancelled_by_user')).toBe(true);
    expect(isTerminalExecutionStatus('running')).toBe(false);
  });

  it('extracts execution status from SSE update shapes', () => {
    expect(extractExecutionStatusFromUpdate({
      execution: { lifecycle_summary: { status: 'done' } },
    })).toBe('done');
    expect(extractExecutionStatusFromUpdate({ type: 'execution_error' })).toBe('failed');
  });

  it('backs off the fallback interval while the page is hidden', () => {
    expect(resolveExecutionPollingIntervalMs(1000, false)).toBe(1000);
    expect(resolveExecutionPollingIntervalMs(1000, true)).toBe(30000);
  });
});


describe('useExecutionPolling', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('stops fallback polling when execution status becomes terminal', async () => {
    const pollFn = vi.fn();
    const { rerender } = renderHook(
      ({ status }) => useExecutionPolling({
        executionId: 'exec-1',
        workspaceId: 'workspace-1',
        apiUrl: '',
        onUpdate: vi.fn(),
        executionStatus: status,
        pollIntervalMs: 1000,
        enableSSE: false,
        enablePollingFallback: true,
        pollFn,
      }),
      { initialProps: { status: 'running' } },
    );

    expect(pollFn).toHaveBeenCalledTimes(1);
    await act(async () => vi.advanceTimersByTimeAsync(1000));
    expect(pollFn).toHaveBeenCalledTimes(2);

    rerender({ status: 'completed' });
    await act(async () => vi.advanceTimersByTimeAsync(5000));

    expect(pollFn).toHaveBeenCalledTimes(2);
  });

  it('uses hidden-page backoff for fallback polling', async () => {
    const originalVisibilityState = document.visibilityState;
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
    });
    const pollFn = vi.fn();

    renderHook(() => useExecutionPolling({
      executionId: 'exec-1',
      workspaceId: 'workspace-1',
      apiUrl: '',
      onUpdate: vi.fn(),
      executionStatus: 'running',
      pollIntervalMs: 1000,
      enableSSE: false,
      enablePollingFallback: true,
      pollFn,
    }));

    expect(pollFn).toHaveBeenCalledTimes(1);
    await act(async () => vi.advanceTimersByTimeAsync(29999));
    expect(pollFn).toHaveBeenCalledTimes(1);

    await act(async () => vi.advanceTimersByTimeAsync(1));
    expect(pollFn).toHaveBeenCalledTimes(2);

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: originalVisibilityState,
    });
  });

  it('aborts an in-flight fallback poll on cleanup', () => {
    const observed: AbortSignal[] = [];
    const abortablePollFn = vi.fn((signal: AbortSignal): Promise<void> => {
      if (signal) observed.push(signal);
      return new Promise(() => undefined);
    });
    const { unmount } = renderHook(() => useExecutionPolling({
      executionId: 'exec-1',
      workspaceId: 'workspace-1',
      apiUrl: '',
      onUpdate: vi.fn(),
      executionStatus: 'running',
      pollIntervalMs: 1000,
      enableSSE: false,
      enablePollingFallback: true,
      abortablePollFn,
    }));

    expect(observed[0]?.aborted).toBe(false);
    unmount();

    expect(observed[0]?.aborted).toBe(true);
  });
});
