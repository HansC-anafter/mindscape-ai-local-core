'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { useExecutionStream, streamManager } from './useExecutionStream';

let inflightCount = 0;
const MAX_INFLIGHT = 3;
const waitQueue: (() => void)[] = [];
const HIDDEN_POLLING_MULTIPLIER = 3;
const MIN_HIDDEN_POLLING_INTERVAL_MS = 30_000;
const TERMINAL_EXECUTION_STATUSES = new Set([
    'aborted',
    'cancelled',
    'cancelled_by_user',
    'canceled',
    'completed',
    'done',
    'error',
    'failed',
    'succeeded',
    'success',
    'timeout',
]);

async function throttledFetch(url: string, init?: RequestInit): Promise<Response> {
    while (inflightCount >= MAX_INFLIGHT) {
        await new Promise<void>(resolve => waitQueue.push(resolve));
    }
    inflightCount++;
    try {
        return await fetch(url, init);
    } finally {
        inflightCount--;
        waitQueue.shift()?.();
    }
}

export interface UseExecutionPollingOptions {
    executionId: string | null | undefined;
    workspaceId: string;
    apiUrl: string;
    onUpdate: (data: any) => void;
    executionStatus?: string | null;
    pollIntervalMs?: number;
    enableSSE?: boolean;
    enablePollingFallback?: boolean;
    sseDebounceMs?: number;
    pollFn?: () => Promise<void> | void;
    abortablePollFn?: (signal: AbortSignal) => Promise<void> | void;
}

export interface UseExecutionPollingReturn {
    sseConnected: boolean;
    refresh: () => void;
}

export function isTerminalExecutionStatus(status: unknown): boolean {
    if (typeof status !== 'string') return false;
    return TERMINAL_EXECUTION_STATUSES.has(status.trim().toLowerCase());
}

export function extractExecutionStatusFromUpdate(data: any): string | null {
    if (!data || typeof data !== 'object') return null;
    const candidates = [
        data.execution?.lifecycle_summary?.status,
        data.execution?.status,
        data.lifecycle_summary?.status,
        data.status,
        data.type === 'execution_completed' ? 'completed' : null,
        data.type === 'execution_complete' ? 'completed' : null,
        data.type === 'execution_error' ? 'failed' : null,
    ];
    const match = candidates.find(value => typeof value === 'string' && value.trim());
    return typeof match === 'string' ? match : null;
}

export function resolveExecutionPollingIntervalMs(
    baseIntervalMs: number,
    hidden: boolean,
): number {
    const safeBase = Math.max(500, Number.isFinite(baseIntervalMs) ? baseIntervalMs : 10_000);
    if (!hidden) return safeBase;
    return Math.max(safeBase * HIDDEN_POLLING_MULTIPLIER, MIN_HIDDEN_POLLING_INTERVAL_MS);
}

export function useExecutionPolling(options: UseExecutionPollingOptions): UseExecutionPollingReturn {
    const {
        executionId,
        workspaceId,
        apiUrl,
        onUpdate,
        executionStatus,
        pollIntervalMs = 10_000,
        enableSSE = true,
        enablePollingFallback = false,
        sseDebounceMs = 1_200,
        pollFn,
        abortablePollFn,
    } = options;

    const [sseConnected, setSseConnected] = useState(false);

    const onUpdateRef = useRef(onUpdate);
    const pollFnRef = useRef(pollFn);
    const abortablePollFnRef = useRef(abortablePollFn);
    const terminalRef = useRef(isTerminalExecutionStatus(executionStatus));
    const pollingInFlightRef = useRef(false);
    const abortControllerRef = useRef<AbortController | null>(null);
    useEffect(() => { onUpdateRef.current = onUpdate; }, [onUpdate]);
    useEffect(() => { pollFnRef.current = pollFn; }, [pollFn]);
    useEffect(() => { abortablePollFnRef.current = abortablePollFn; }, [abortablePollFn]);
    useEffect(() => {
        terminalRef.current = isTerminalExecutionStatus(executionStatus);
        if (terminalRef.current) {
            abortControllerRef.current?.abort();
        }
    }, [executionId, executionStatus]);

    const sseRefreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const lastSseRefreshAtRef = useRef<number>(0);

    useEffect(() => {
        return () => {
            if (sseRefreshTimerRef.current) {
                clearTimeout(sseRefreshTimerRef.current);
                sseRefreshTimerRef.current = null;
            }
            abortControllerRef.current?.abort();
            abortControllerRef.current = null;
        };
    }, []);

    const runPoll = useCallback(async () => {
        if (
            terminalRef.current ||
            pollingInFlightRef.current ||
            (!pollFnRef.current && !abortablePollFnRef.current)
        ) {
            return;
        }

        const controller = new AbortController();
        abortControllerRef.current = controller;
        pollingInFlightRef.current = true;
        try {
            if (abortablePollFnRef.current) {
                await abortablePollFnRef.current(controller.signal);
            } else {
                await pollFnRef.current?.();
            }
        } finally {
            if (abortControllerRef.current === controller) {
                abortControllerRef.current = null;
            }
            pollingInFlightRef.current = false;
        }
    }, []);

    const runPollSafely = useCallback(() => {
        runPoll().catch(error => {
            console.warn('[useExecutionPolling] polling fallback failed:', error);
        });
    }, [runPoll]);

    const handleSSEEvent = useCallback((data: any) => {
        onUpdateRef.current?.(data);
        const status = extractExecutionStatusFromUpdate(data);
        if (isTerminalExecutionStatus(status)) {
            terminalRef.current = true;
            abortControllerRef.current?.abort();
            return;
        }

        if (!pollFnRef.current && !abortablePollFnRef.current) return;

        const now = Date.now();
        const elapsed = now - lastSseRefreshAtRef.current;

        if (elapsed >= sseDebounceMs) {
            lastSseRefreshAtRef.current = now;
            runPollSafely();
            return;
        }

        if (sseRefreshTimerRef.current) return;
        const delay = Math.max(0, sseDebounceMs - elapsed);
        sseRefreshTimerRef.current = setTimeout(() => {
            sseRefreshTimerRef.current = null;
            lastSseRefreshAtRef.current = Date.now();
            runPollSafely();
        }, delay);
    }, [runPollSafely, sseDebounceMs]);

    useExecutionStream(
        enableSSE ? executionId : null,
        workspaceId,
        apiUrl,
        handleSSEEvent
    );

    useEffect(() => {
        if (!executionId || !enableSSE) {
            setSseConnected(false);
            return;
        }

        setSseConnected(streamManager.isConnected(executionId));

        const unsubscribe = streamManager.onConnectionChange(executionId, (connected) => {
            setSseConnected(connected);
        });

        return unsubscribe;
    }, [executionId, enableSSE]);

    const refresh = useCallback(() => {
        runPollSafely();
    }, [runPollSafely]);

    useEffect(() => {
        if (!executionId) return;
        if (!enablePollingFallback) return;
        if (sseConnected && enableSSE) return;
        if (terminalRef.current) return;

        if (!pollFnRef.current && !abortablePollFnRef.current) return;

        let cancelled = false;
        let timer: ReturnType<typeof setTimeout> | null = null;

        const scheduleNext = () => {
            if (cancelled || terminalRef.current) return;
            const hidden = typeof document !== 'undefined' && document.visibilityState === 'hidden';
            const interval = resolveExecutionPollingIntervalMs(pollIntervalMs, hidden);
            timer = setTimeout(async () => {
                try {
                    await runPoll();
                } catch (error) {
                    console.warn('[useExecutionPolling] polling fallback failed:', error);
                }
                scheduleNext();
            }, interval);
        };

        runPollSafely();
        scheduleNext();

        return () => {
            cancelled = true;
            if (timer) clearTimeout(timer);
            abortControllerRef.current?.abort();
        };
    }, [
        executionId,
        sseConnected,
        enableSSE,
        enablePollingFallback,
        pollIntervalMs,
        runPoll,
        runPollSafely,
    ]);

    return { sseConnected, refresh };
}

export { throttledFetch };
