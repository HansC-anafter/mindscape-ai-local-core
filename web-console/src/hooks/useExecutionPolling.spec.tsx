import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  extractExecutionStatusFromUpdate,
  isTerminalExecutionStatus,
  useExecutionPolling,
} from './useExecutionPolling';
import { resolveExecutionPollingDelayMs } from './executionPollingPolicy';


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
  it('uses 10/20/30 second failure backoff and honors longer Retry-After', () => {
    expect(resolveExecutionPollingDelayMs({ baseIntervalMs: 1000, consecutiveFailures: 1 })).toBe(10000);
    expect(resolveExecutionPollingDelayMs({ baseIntervalMs: 1000, consecutiveFailures: 2 })).toBe(20000);
    expect(resolveExecutionPollingDelayMs({ baseIntervalMs: 1000, consecutiveFailures: 4 })).toBe(30000);
    expect(resolveExecutionPollingDelayMs({
      baseIntervalMs: 1000,
      consecutiveFailures: 2,
      retryAfterMs: 45000,
    })).toBe(45000);
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

  it('stops fallback polling when the poll result reports terminal status', async () => {
    const pollFn = vi.fn(async () => ({ status: 'completed' }));

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

    await act(async () => Promise.resolve());
    await act(async () => vi.advanceTimersByTimeAsync(60_000));
    expect(pollFn).toHaveBeenCalledTimes(1);
  });

  it('does not dispatch while hidden and refreshes immediately on visibility resume', async () => {
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

    expect(pollFn).toHaveBeenCalledTimes(0);
    await act(async () => vi.advanceTimersByTimeAsync(60_000));
    expect(pollFn).toHaveBeenCalledTimes(0);

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    });
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    expect(pollFn).toHaveBeenCalledTimes(1);

    await act(async () => vi.advanceTimersByTimeAsync(1000));
    expect(pollFn).toHaveBeenCalledTimes(2);

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: originalVisibilityState,
    });
  });

  it('aborts an in-flight fallback poll when the page becomes hidden', () => {
    const originalVisibilityState = document.visibilityState;
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    });
    const observed: AbortSignal[] = [];
    const abortablePollFn = vi.fn((signal: AbortSignal): Promise<void> => {
      observed.push(signal);
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
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
    });
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    expect(observed[0]?.aborted).toBe(true);

    unmount();
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
