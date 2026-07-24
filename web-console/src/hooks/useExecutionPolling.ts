'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { useExecutionStream, streamManager } from './useExecutionStream';
import {
    cancelExecutionPoll,
    executionDocumentHidden,
    scheduleExecutionPoll,
} from './executionPollingCoordinator';
import {
    resolveExecutionPollingDelayMs,
    retryAfterMsFromError,
} from './executionPollingPolicy';

let inflightCount = 0;
const MAX_INFLIGHT = 3;
const waitQueue: (() => void)[] = [];
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
    pollFn?: () => Promise<unknown> | unknown;
    abortablePollFn?: (signal: AbortSignal) => Promise<unknown> | unknown;
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
    const consecutiveFailuresRef = useRef(0);
    const retryAfterMsRef = useRef<number | null>(null);
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
            (typeof document !== 'undefined' && document.visibilityState === 'hidden') ||
            (!pollFnRef.current && !abortablePollFnRef.current)
        ) {
            return;
        }

        const controller = new AbortController();
        abortControllerRef.current = controller;
        pollingInFlightRef.current = true;
        try {
            let result: unknown;
            if (abortablePollFnRef.current) {
                result = await abortablePollFnRef.current(controller.signal);
            } else {
                result = await pollFnRef.current?.();
            }
            const status = extractExecutionStatusFromUpdate(result);
            if (isTerminalExecutionStatus(status)) {
                terminalRef.current = true;
            }
            consecutiveFailuresRef.current = 0;
            retryAfterMsRef.current = null;
        } catch (error) {
            consecutiveFailuresRef.current += 1;
            retryAfterMsRef.current = retryAfterMsFromError(error);
            throw error;
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

        if (executionDocumentHidden()) return;
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

    useEffect(() => {
        if (!executionId || !enableSSE || !sseConnected) return;
        const handleVisibility = () => {
            if (executionDocumentHidden()) {
                abortControllerRef.current?.abort();
                return;
            }
            if (!terminalRef.current) runPollSafely();
        };
        document.addEventListener('visibilitychange', handleVisibility);
        return () => document.removeEventListener('visibilitychange', handleVisibility);
    }, [enableSSE, executionId, runPollSafely, sseConnected]);

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
        const clearScheduledPoll = () => {
            cancelExecutionPoll(timer);
            timer = null;
        };

        const scheduleNext = () => {
            if (cancelled || terminalRef.current) return;
            if (executionDocumentHidden()) {
                clearScheduledPoll();
                return;
            }
            const interval = resolveExecutionPollingDelayMs({
                baseIntervalMs: pollIntervalMs,
                consecutiveFailures: consecutiveFailuresRef.current,
                retryAfterMs: retryAfterMsRef.current,
            });
            timer = scheduleExecutionPoll(async () => {
                try {
                    await runPoll();
                } catch (error) {
                    console.warn('[useExecutionPolling] polling fallback failed:', error);
                }
                scheduleNext();
            }, interval);
        };

        const pollAndSchedule = async () => {
            try {
                await runPoll();
            } catch (error) {
                console.warn('[useExecutionPolling] polling fallback failed:', error);
            }
            scheduleNext();
        };

        const resumeVisiblePolling = () => {
            clearScheduledPoll();
            if (executionDocumentHidden()) {
                abortControllerRef.current?.abort();
                return;
            }
            void pollAndSchedule();
        };

        if (!executionDocumentHidden()) {
            void pollAndSchedule();
        }
        document.addEventListener('visibilitychange', resumeVisiblePolling);

        return () => {
            cancelled = true;
            document.removeEventListener('visibilitychange', resumeVisiblePolling);
            clearScheduledPoll();
            abortControllerRef.current?.abort();
        };
    }, [
        executionId,
        sseConnected,
        enableSSE,
        enablePollingFallback,
        pollIntervalMs,
        runPoll,
    ]);

    return { sseConnected, refresh };
}

export { throttledFetch };
