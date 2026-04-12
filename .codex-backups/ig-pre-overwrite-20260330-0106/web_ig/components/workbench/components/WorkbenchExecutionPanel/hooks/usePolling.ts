/**
 * Hook for auto-polling and SSE refresh logic — migrated to unified useExecutionPolling.
 *
 * This thin wrapper adapts the IG-specific shape (activeTab, igPinnedRun, etc.)
 * to the generic useExecutionPolling hook.
 */
import { useCallback } from 'react';
import type { TabType, RunInfo } from '../types';
import { useExecutionPolling } from '@/hooks/useExecutionPolling';

interface UsePollingOptions {
    activeTab: TabType;
    igExecutionId: string | null;
    igPinnedRun: RunInfo | null;
    workspaceId: string;
    apiUrl: string;
    fetchLatestIGDebug: () => Promise<void>;
    enableDebugRefresh?: boolean;
}

export function usePolling(options: UsePollingOptions): void {
    const {
        activeTab,
        igExecutionId,
        igPinnedRun,
        workspaceId,
        apiUrl,
        fetchLatestIGDebug,
        enableDebugRefresh = true,
    } = options;

    // Only poll when on logs tab with an active execution
    const status = (igPinnedRun?.status || '').toString();
    const isActive = !status || ['running', 'queued', 'pending', 'paused'].includes(status);
    const shouldPoll = activeTab === 'logs' && !!igExecutionId && isActive;

    const pollFn = useCallback(async () => {
        if (enableDebugRefresh) {
            await fetchLatestIGDebug();
        }
    }, [enableDebugRefresh, fetchLatestIGDebug]);

    useExecutionPolling({
        executionId: shouldPoll ? igExecutionId : null,
        workspaceId,
        apiUrl,
        onUpdate: () => {
            // SSE events trigger debounced pollFn automatically
        },
        pollIntervalMs: 10_000,
        enableSSE: true,
        sseDebounceMs: 1_200,
        pollFn,
    });
}
