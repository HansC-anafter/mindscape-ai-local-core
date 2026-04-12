/**
 * Hook for managing execution state (forcedExecution, igExecutionId, igPinnedRun)
 */
import { useState, useEffect, useMemo } from 'react';
import type { RunInfo, ForcedExecution, TabType } from '../types';
import { parseTimestamp } from '../utils/formatters';
import { useIGWorkspaceEvents } from '../../../../hooks/useIGWorkspaceEvents';

interface UseExecutionStateOptions {
    recentRuns: RunInfo[];
    workspaceId: string;
    apiUrl?: string;
    onRefreshRuns?: () => void;
}

interface UseExecutionStateReturn {
    activeTab: TabType;
    setActiveTab: (tab: TabType) => void;
    forcedExecution: ForcedExecution | null;
    setForcedExecution: (forced: ForcedExecution | null) => void;
    latestIGRun: RunInfo | null;
    igExecutionId: string | null;
    igPinnedRun: RunInfo | null;
}

export function useExecutionState(options: UseExecutionStateOptions): UseExecutionStateReturn {
    const { recentRuns, workspaceId, apiUrl = '', onRefreshRuns } = options;

    const [activeTab, setActiveTab] = useState<TabType>('logs');
    const [forcedExecution, setForcedExecution] = useState<ForcedExecution | null>(null);

    // Find the latest IG run
    const latestIGRun = useMemo(() => {
        const runs = Array.isArray(recentRuns) ? recentRuns : [];
        const igRuns = runs.filter(
            (r) => (r?.playbook_code || '').toString() === 'ig_analyze_following' && (r?.execution_id || r?.id)
        );

        const toTs = (r: any) => {
            const v = r?.created_at || r?.started_at || r?.task?.created_at || r?.task?.started_at || null;
            const d = parseTimestamp(v);
            return d ? d.getTime() : 0;
        };

        const getPriority = (r: any) => {
            const s = (r?.status || '').toString().toLowerCase();
            if (s === 'running') return 2;
            if (['pending', 'queued', 'paused'].includes(s)) return 1;
            return 0;
        };

        igRuns.sort((a, b) => {
            const pa = getPriority(a);
            const pb = getPriority(b);
            if (pa !== pb) return pb - pa;
            return toTs(b) - toTs(a);
        });

        return igRuns[0] || null;
    }, [recentRuns]);

    // Determine which execution ID to display
    const igExecutionId = useMemo(() => {
        const runs = Array.isArray(recentRuns) ? recentRuns : [];

        // Priority 1: Currently running IG task
        const runningIG = runs.find((r) =>
            (r?.playbook_code || '').toString() === 'ig_analyze_following' &&
            (r?.status || '').toString().toLowerCase() === 'running'
        );
        if (runningIG) {
            return (runningIG.execution_id || runningIG.id || '').toString();
        }

        // Priority 2: Forced execution (from rerun click)
        const forced = (forcedExecution?.executionId || '').toString().trim();
        if (forced) return forced;

        // Priority 3: Latest IG run
        return (latestIGRun?.execution_id || latestIGRun?.id || '').toString() || null;
    }, [recentRuns, forcedExecution?.executionId, latestIGRun?.execution_id, latestIGRun?.id]);

    // Find the pinned run object
    const igPinnedRun = useMemo(() => {
        const runs = Array.isArray(recentRuns) ? recentRuns : [];
        const execId = (igExecutionId || '').toString();
        if (!execId) return null;

        const found = runs.find((r) => (r?.execution_id || r?.id || '').toString() === execId);
        if (found) return found;

        // If forcedExecution exists but not yet in recentRuns, create a temporary pending run object
        if (forcedExecution?.executionId === execId) {
            return {
                execution_id: execId,
                id: execId,
                status: 'pending',
                playbook_code: forcedExecution.playbookCode || 'ig_analyze_following',
                started_at: forcedExecution.startedAt || new Date().toISOString(),
            } as RunInfo;
        }
        return null;
    }, [recentRuns, igExecutionId, forcedExecution]);

    // Clear forced execution when task completes
    useEffect(() => {
        const forcedId = (forcedExecution?.executionId || '').toString().trim();
        if (!forcedId) return;

        const pinnedStatus = (igPinnedRun?.status || '').toString();
        const isTerminal = ['completed', 'failed', 'cancelled_by_user', 'cancelled'].includes(pinnedStatus);
        if (!isTerminal) return;

        const latestId = (latestIGRun?.execution_id || latestIGRun?.id || '').toString();
        if (!latestId || latestId === forcedId) return;

        setForcedExecution(null);
    }, [forcedExecution?.executionId, igPinnedRun?.status, latestIGRun?.execution_id, latestIGRun?.id]);

    useIGWorkspaceEvents({
        workspaceId,
        apiUrl,
        onEvent: (_event, metadata) => {
            const execId = (metadata.executionId || '').toString().trim();
            const code = (metadata.playbookCode || '').toString();
            const lifecycleState = (metadata.lifecycleState || '').toString().toUpperCase();

            if (!execId) return;

            if (lifecycleState === 'READY') {
                setActiveTab('logs');
                onRefreshRuns?.();

                if (code === 'ig_analyze_following') {
                    setForcedExecution({
                        executionId: execId,
                        playbookCode: code,
                        startedAt: new Date().toISOString(),
                    });
                }
                return;
            }

            if (metadata.terminal) {
                onRefreshRuns?.();
            }
        },
    });

    return {
        activeTab,
        setActiveTab,
        forcedExecution,
        setForcedExecution,
        latestIGRun,
        igExecutionId,
        igPinnedRun,
    };
}
