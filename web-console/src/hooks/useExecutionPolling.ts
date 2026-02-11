'use client';

/**
 * useExecutionPolling — unified SSE-first + polling fallback hook
 *
 * State machine:
 *   [*] → SSE_Active (hook mount + SSE enabled)
 *   SSE_Active → Polling_Fallback (onerror(CLOSED) or 45s watchdog timeout)
 *   Polling_Fallback → SSE_Active (SSE reconnect succeeds, onopen)
 *   SSE_Active → [*] (hook unmount)
 *   Polling_Fallback → [*] (hook unmount)
 *
 * When SSE is connected, polling is disabled — only SSE-driven refreshes fire.
 * When SSE is disconnected, a setInterval fallback runs at `pollIntervalMs`.
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { useExecutionStream, streamManager } from './useExecutionStream';

// Module-level concurrency limiter for fetch-based polling
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
    /** Execution ID to track — null/undefined = disabled */
    executionId: string | null | undefined;
    /** Workspace ID */
    workspaceId: string;
    /** API base URL (e.g. NEXT_PUBLIC_API_URL) */
    apiUrl: string;
    /** Called on every SSE event or poll result */
    onUpdate: (data: any) => void;
    /** Polling interval in ms when SSE is disconnected. Default: 10_000 */
    pollIntervalMs?: number;
    /** Enable SSE streaming. Default: true */
    enableSSE?: boolean;
    /** Minimum gap between SSE-triggered refreshes (debounce). Default: 1_200 */
    sseDebounceMs?: number;
    /** Custom poll function. If not provided, polling is skipped. */
    pollFn?: () => Promise<void>;
}

export interface UseExecutionPollingReturn {
    /** Whether SSE is currently connected (reactive React state, triggers re-render) */
    sseConnected: boolean;
    /** Manually trigger a refresh */
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
        sseDebounceMs = 1_200,
        pollFn,
    } = options;

    const [sseConnected, setSseConnected] = useState(false);

    // Refs for latest callbacks (avoid unnecessary re-effects)
    const onUpdateRef = useRef(onUpdate);
    const pollFnRef = useRef(pollFn);
    useEffect(() => { onUpdateRef.current = onUpdate; }, [onUpdate]);
    useEffect(() => { pollFnRef.current = pollFn; }, [pollFn]);

    // SSE debounce
    const sseRefreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const lastSseRefreshAtRef = useRef<number>(0);

    // Cleanup debounce timer on unmount
    useEffect(() => {
        return () => {
            if (sseRefreshTimerRef.current) {
                clearTimeout(sseRefreshTimerRef.current);
                sseRefreshTimerRef.current = null;
            }
        };
    }, []);

    // SSE event handler — debounced
    const handleSSEEvent = useCallback((data: any) => {
        // Always call onUpdate for the SSE data
        onUpdateRef.current?.(data);

        // Debounced refresh via pollFn (if provided)
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

    // Wire up SSE stream
    useExecutionStream(
        enableSSE ? executionId : null,
        workspaceId,
        apiUrl,
        handleSSEEvent
    );

    // Reactive SSE connection state via onConnectionChange callback
    useEffect(() => {
        if (!executionId || !enableSSE) {
            setSseConnected(false);
            return;
        }

        // Set initial state from streamManager
        setSseConnected(streamManager.isConnected(executionId));

        // Subscribe to connection state changes
        const unsubscribe = streamManager.onConnectionChange(executionId, (connected) => {
            setSseConnected(connected);
        });

        return unsubscribe;
    }, [executionId, enableSSE]);

    // Manual refresh
    const refresh = useCallback(() => {
        pollFnRef.current?.();
    }, []);

    // Polling fallback — only active when SSE is NOT connected
    useEffect(() => {
        if (!executionId) return;
        if (sseConnected && enableSSE) return; // SSE active, no polling needed

        if (!pollFnRef.current) return;

        // Immediate poll on entering fallback
        pollFnRef.current();

        const t = setInterval(() => {
            pollFnRef.current?.();
        }, pollIntervalMs);

        return () => clearInterval(t);
    }, [executionId, sseConnected, enableSSE, pollIntervalMs]);

    return { sseConnected, refresh };
}

export { throttledFetch };
