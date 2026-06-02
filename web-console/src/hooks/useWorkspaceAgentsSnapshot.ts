'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { isDocumentHidden, onDocumentVisible } from '@/lib/page-visibility';
import { sharedGetFetch } from '@/lib/resilient-fetch';
import type { WorkspaceExecutorAgentInfo } from '@/components/workspace/workspaceExecutorRuntimeViewModel';

interface UseWorkspaceAgentsSnapshotResult {
  agents: WorkspaceExecutorAgentInfo[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useWorkspaceAgentsSnapshot(
  workspaceId: string,
  apiUrl: string = '',
): UseWorkspaceAgentsSnapshotResult {
  const [agents, setAgents] = useState<WorkspaceExecutorAgentInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    if (!workspaceId || isDocumentHidden()) {
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = await sharedGetFetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/agents`,
        { method: 'GET' },
        { dedupKey: `workspace-agents:${workspaceId}` },
      );
      if (!response.ok) {
        throw new Error(`Failed to fetch workspace agents: ${response.status}`);
      }
      const data = await response.json();
      if (mountedRef.current) {
        setAgents(Array.isArray(data?.agents) ? data.agents : []);
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : 'Failed to fetch workspace agents');
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, [apiUrl, workspaceId]);

  useEffect(() => {
    void refresh();
    return onDocumentVisible(() => {
      void refresh();
    });
  }, [refresh]);

  return {
    agents,
    loading,
    error,
    refresh,
  };
}
