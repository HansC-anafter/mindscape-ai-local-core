'use client';

import { useCallback, useEffect, useState } from 'react';

export interface WorkspaceExecutorSurfaceState {
  surface: string;
  enabled: boolean;
  preferred_runtime_id: string | null;
  source: string;
}

export interface WorkspaceExecutorRoutePayload {
  workspace_id: string;
  route_authority: string;
  primary_executor_runtime: string | null;
  resolved_executor_runtime?: string | null;
  allow_runtime_substitution: boolean;
  dispatch_chain: string[];
  surfaces: Record<string, WorkspaceExecutorSurfaceState>;
}

interface UseWorkspaceExecutorRouteResult {
  routeEntries: string[];
  dispatchChain: string[];
  resolvedRuntime: string | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  setPrimaryRuntime: (runtimeId: string) => Promise<boolean>;
  clearPrimaryRuntime: () => Promise<boolean>;
}

function deriveRouteEntries(payload: Partial<WorkspaceExecutorRoutePayload>): string[] {
  const entries = new Set<string>();
  const primaryRuntime = payload.primary_executor_runtime || payload.resolved_executor_runtime;
  if (primaryRuntime) {
    entries.add(primaryRuntime);
  }

  Object.entries(payload.surfaces || {}).forEach(([surface, state]) => {
    if (state?.enabled) {
      entries.add(surface);
    }
    if (state?.preferred_runtime_id) {
      entries.add(state.preferred_runtime_id);
    }
  });

  return Array.from(entries);
}

export function useWorkspaceExecutorRoute(
  workspaceId: string,
  apiUrl: string = '',
): UseWorkspaceExecutorRouteResult {
  const [routeEntries, setRouteEntries] = useState<string[]>([]);
  const [dispatchChain, setDispatchChain] = useState<string[]>([]);
  const [resolvedRuntime, setResolvedRuntime] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const baseUrl = `${apiUrl}/api/v1/settings/model-route-registry/workspace-executor`;

  const refresh = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${baseUrl}?workspace_id=${encodeURIComponent(workspaceId)}`);
      if (!res.ok) throw new Error(`Failed to fetch workspace executor route: ${res.status}`);
      const data: WorkspaceExecutorRoutePayload = await res.json();
      setRouteEntries(deriveRouteEntries(data));
      setDispatchChain(data.dispatch_chain || []);
      setResolvedRuntime(data.primary_executor_runtime || data.resolved_executor_runtime || null);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [workspaceId, baseUrl]);

  const updatePrimaryRuntime = useCallback(async (runtimeId: string | null): Promise<boolean> => {
    setError(null);
    try {
      const res = await fetch(baseUrl, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: workspaceId,
          executor_runtime: runtimeId,
        }),
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
  }, [baseUrl, refresh, workspaceId]);

  const setPrimaryRuntime = useCallback(
    (runtimeId: string): Promise<boolean> => updatePrimaryRuntime(runtimeId),
    [updatePrimaryRuntime],
  );

  const clearPrimaryRuntime = useCallback(
    (): Promise<boolean> => updatePrimaryRuntime(null),
    [updatePrimaryRuntime],
  );

  useEffect(() => {
    if (workspaceId) void refresh();
  }, [workspaceId, refresh]);

  return {
    routeEntries,
    dispatchChain,
    resolvedRuntime,
    loading,
    error,
    refresh,
    setPrimaryRuntime,
    clearPrimaryRuntime,
  };
}
