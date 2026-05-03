'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { useExecutionStream, streamManager } from './useExecutionStream';

let inflightCount = 0;
const MAX_INFLIGHT = 3;
const waitQueue: (() => void)[] = [];

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
    pollIntervalMs?: number;
    enableSSE?: boolean;
    enablePollingFallback?: boolean;
    sseDebounceMs?: number;
    pollFn?: () => Promise<void> | void;
}

export interface UseExecutionPollingReturn {
    sseConnected: boolean;
    refresh: () => void;
}

export function useExecutionPolling(options: UseExecutionPollingOptions): UseExecutionPollingReturn {
    const {
        executionId,
        workspaceId,
        apiUrl,
        onUpdate,
        pollIntervalMs = 10_000,
        enableSSE = true,
        enablePollingFallback = false,
        sseDebounceMs = 1_200,
        pollFn,
    } = options;

    const [sseConnected, setSseConnected] = useState(false);

    const onUpdateRef = useRef(onUpdate);
    const pollFnRef = useRef(pollFn);
    useEffect(() => { onUpdateRef.current = onUpdate; }, [onUpdate]);
    useEffect(() => { pollFnRef.current = pollFn; }, [pollFn]);

    const sseRefreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const lastSseRefreshAtRef = useRef<number>(0);

    useEffect(() => {
        return () => {
            if (sseRefreshTimerRef.current) {
                clearTimeout(sseRefreshTimerRef.current);
                sseRefreshTimerRef.current = null;
            }
        };
    }, []);

    const handleSSEEvent = useCallback((data: any) => {
        onUpdateRef.current?.(data);

        if (!pollFnRef.current) return;

        const now = Date.now();
        const elapsed = now - lastSseRefreshAtRef.current;

        if (elapsed >= sseDebounceMs) {
            lastSseRefreshAtRef.current = now;
            pollFnRef.current();
            return;
        }

        if (sseRefreshTimerRef.current) return;
        const delay = Math.max(0, sseDebounceMs - elapsed);
        sseRefreshTimerRef.current = setTimeout(() => {
            sseRefreshTimerRef.current = null;
            lastSseRefreshAtRef.current = Date.now();
            pollFnRef.current?.();
        }, delay);
    }, [sseDebounceMs]);

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
        pollFnRef.current?.();
    }, []);

    useEffect(() => {
        if (!executionId) return;
        if (!enablePollingFallback) return;
        if (sseConnected && enableSSE) return;

        if (!pollFnRef.current) return;

        pollFnRef.current();

        const t = setInterval(() => {
            pollFnRef.current?.();
        }, pollIntervalMs);

        return () => clearInterval(t);
    }, [executionId, sseConnected, enableSSE, enablePollingFallback, pollIntervalMs]);

    return { sseConnected, refresh };
}

export { throttledFetch };
