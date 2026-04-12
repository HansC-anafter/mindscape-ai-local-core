/**
 * Hook for execution actions (rerun, cancel)
 */
import { useState, useCallback } from 'react';
import type { ForcedExecution, TabType } from '../types';

interface UseExecutionActionsOptions {
    apiUrl: string;
    workspaceId: string;
    onRefreshRuns?: () => void;
    fetchLatestIGDebug?: () => Promise<void>;
    setActiveTab?: (tab: TabType) => void;
    setForcedExecution?: (forced: ForcedExecution | null) => void;
}

interface UseExecutionActionsReturn {
    // Rerun state
    rerunBusyId: string | null;
    rerunNotice: string | null;
    rerunNeedsTarget: { executionId: string } | null;
    rerunTargetInput: string;
    setRerunTargetInput: (value: string) => void;
    setRerunNeedsTarget: (value: { executionId: string } | null) => void;
    rerunExecution: (executionId: string, overrideInputs?: Record<string, any>) => Promise<void>;

    // Cancel state
    cancelBusyId: string | null;
    cancelNotice: string | null;
    cancelExecution: (executionId: string) => Promise<void>;

    // Helpers
    canRerunStatus: (status: any) => boolean;
}

export function useExecutionActions(options: UseExecutionActionsOptions): UseExecutionActionsReturn {
    const { apiUrl, workspaceId, onRefreshRuns, fetchLatestIGDebug, setActiveTab, setForcedExecution } = options;

    // Rerun state
    const [rerunBusyId, setRerunBusyId] = useState<string | null>(null);
    const [rerunNotice, setRerunNotice] = useState<string | null>(null);
    const [rerunNeedsTarget, setRerunNeedsTarget] = useState<{ executionId: string } | null>(null);
    const [rerunTargetInput, setRerunTargetInput] = useState<string>('');

    // Cancel state
    const [cancelBusyId, setCancelBusyId] = useState<string | null>(null);
    const [cancelNotice, setCancelNotice] = useState<string | null>(null);

    const canRerunStatus = useCallback((status: any) => {
        const s = (status || '').toString();
        return ['failed', 'cancelled_by_user', 'cancelled', 'succeeded', 'completed'].includes(s);
    }, []);

    const cancelExecution = useCallback(async (executionId: string) => {
        setCancelNotice(null);
        setCancelBusyId(executionId);
        try {
            const resp = await fetch(`${apiUrl}/api/v1/playbooks/execute/${executionId}/cancel`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reason: 'user_cancelled_from_execution_debug' }),
            });
            if (!resp.ok) {
                const data = await resp.json().catch(() => ({}));
                const detail = (data.detail || resp.statusText || '').toString();
                setCancelNotice(`Cancel failed: ${detail}`);
                return;
            }
            setCancelNotice('Cancelled');
            onRefreshRuns?.();
            fetchLatestIGDebug?.();
        } catch (e) {
            setCancelNotice(`Cancel failed: ${e instanceof Error ? e.message : 'Unknown error'}`);
        } finally {
            setCancelBusyId(null);
        }
    }, [apiUrl, onRefreshRuns, fetchLatestIGDebug]);

    const rerunExecution = useCallback(async (executionId: string, overrideInputs?: Record<string, any>) => {
        setRerunNotice(null);
        setRerunBusyId(executionId);
        try {
            const resp = await fetch(`${apiUrl}/api/v1/playbooks/execute/${executionId}/rerun`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(overrideInputs ? { override_inputs: overrideInputs } : {}),
            });
            if (!resp.ok) {
                const data = await resp.json().catch(() => ({}));
                const detail = (data.detail || resp.statusText || '').toString();
                if (resp.status === 409 && detail.toLowerCase().includes('missing target_username')) {
                    setRerunNeedsTarget({ executionId });
                    setRerunNotice('Rerun needs target username.');
                } else {
                    setRerunNotice(`Rerun failed: ${detail}`);
                }
                return;
            }
            const data = await resp.json().catch(() => ({}));
            const newId = data.execution_id || data.result?.execution_id;
            if (newId) {
                setRerunNotice(`Rerun started: ${newId}`);
                try {
                    const execId = newId.toString();
                    setActiveTab?.('logs');
                    setForcedExecution?.({
                        executionId: execId,
                        playbookCode: 'ig_analyze_following',
                        startedAt: new Date().toISOString(),
                    });
                    if (typeof window !== 'undefined') {
                        const normalizedInputs = overrideInputs && typeof overrideInputs === 'object'
                            ? overrideInputs
                            : undefined;
                        window.dispatchEvent(
                            new CustomEvent('mindscape:execution_started', {
                                detail: {
                                    workspaceId,
                                    executionId: execId,
                                    playbookCode: 'ig_analyze_following',
                                    startedAt: new Date().toISOString(),
                                    targetUsername: normalizedInputs?.target_username || undefined,
                                    inputs: normalizedInputs,
                                },
                            })
                        );
                    }
                } catch {
                    // ignore
                }
            } else {
                setRerunNotice('Rerun started');
            }
            setRerunNeedsTarget(null);
            setRerunTargetInput('');
            onRefreshRuns?.();
        } catch (e) {
            setRerunNotice(`Rerun failed: ${e instanceof Error ? e.message : 'Unknown error'}`);
        } finally {
            setRerunBusyId(null);
        }
    }, [apiUrl, workspaceId, onRefreshRuns, setActiveTab, setForcedExecution]);

    return {
        rerunBusyId,
        rerunNotice,
        rerunNeedsTarget,
        rerunTargetInput,
        setRerunTargetInput,
        setRerunNeedsTarget,
        rerunExecution,
        cancelBusyId,
        cancelNotice,
        cancelExecution,
        canRerunStatus,
    };
}
