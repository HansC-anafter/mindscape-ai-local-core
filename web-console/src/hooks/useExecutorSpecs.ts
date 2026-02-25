'use client';

import { useState, useCallback, useEffect } from 'react';

export interface ExecutorSpec {
    runtime_id: string;
    display_name: string;
    is_primary: boolean;
    config: Record<string, any>;
    priority: number;
}

interface UseExecutorSpecsResult {
    specs: ExecutorSpec[];
    dispatchChain: string[];
    resolvedRuntime: string | null;
    loading: boolean;
    error: string | null;
    refresh: () => Promise<void>;
    addSpec: (spec: Omit<ExecutorSpec, 'config'> & { config?: Record<string, any> }) => Promise<boolean>;
    removeSpec: (runtimeId: string) => Promise<boolean>;
    setPrimary: (runtimeId: string) => Promise<boolean>;
}

/**
 * useExecutorSpecs Hook
 * CRUD wrapper for /api/v1/workspaces/{workspaceId}/executor-specs
 */
export function useExecutorSpecs(
    workspaceId: string,
    apiUrl: string = ''
): UseExecutorSpecsResult {
    const [specs, setSpecs] = useState<ExecutorSpec[]>([]);
    const [dispatchChain, setDispatchChain] = useState<string[]>([]);
    const [resolvedRuntime, setResolvedRuntime] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const baseUrl = `${apiUrl}/api/v1/workspaces/${workspaceId}/executor-specs`;

    const refresh = useCallback(async () => {
        if (!workspaceId) return;
        setLoading(true);
        setError(null);
        try {
            const res = await fetch(baseUrl);
            if (!res.ok) throw new Error(`Failed to fetch specs: ${res.status}`);
            const data = await res.json();
            setSpecs(data.executor_specs || []);
            setDispatchChain(data.dispatch_chain || []);
            setResolvedRuntime(data.resolved_executor_runtime || null);
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }, [workspaceId, baseUrl]);

    const addSpec = useCallback(async (
        spec: Omit<ExecutorSpec, 'config'> & { config?: Record<string, any> }
    ): Promise<boolean> => {
        setError(null);
        try {
            const res = await fetch(baseUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(spec),
            });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail || `Failed: ${res.status}`);
            }
            await refresh();
            return true;
        } catch (err: any) {
            setError(err.message);
            return false;
        }
    }, [baseUrl, refresh]);

    const removeSpec = useCallback(async (runtimeId: string): Promise<boolean> => {
        setError(null);
        try {
            const res = await fetch(`${baseUrl}/${runtimeId}`, { method: 'DELETE' });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail || `Failed: ${res.status}`);
            }
            await refresh();
            return true;
        } catch (err: any) {
            setError(err.message);
            return false;
        }
    }, [baseUrl, refresh]);

    const setPrimary = useCallback(async (runtimeId: string): Promise<boolean> => {
        setError(null);
        try {
            const res = await fetch(`${baseUrl}/${runtimeId}/primary`, { method: 'PATCH' });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail || `Failed: ${res.status}`);
            }
            await refresh();
            return true;
        } catch (err: any) {
            setError(err.message);
            return false;
        }
    }, [baseUrl, refresh]);

    // Initial load
    useEffect(() => {
        if (workspaceId) refresh();
    }, [workspaceId, refresh]);

    return {
        specs,
        dispatchChain,
        resolvedRuntime,
        loading,
        error,
        refresh,
        addSpec,
        removeSpec,
        setPrimary,
    };
}
