import { useEffect, useState } from 'react';

import type { InspectorTab, RuntimeInspectorSnapshot } from './meetingWorkbenchTypes';

interface UseRuntimeInspectorSnapshotArgs {
  workspaceId: string;
  apiUrl: string;
  activeInspector: InspectorTab | null;
}

export function useRuntimeInspectorSnapshot({
  workspaceId,
  apiUrl,
  activeInspector,
}: UseRuntimeInspectorSnapshotArgs): RuntimeInspectorSnapshot {
  const [runtimeSnapshot, setRuntimeSnapshot] = useState<RuntimeInspectorSnapshot>({
    resolvedRuntime: null,
    dispatchChain: [],
    boundRuntimeIds: [],
    agents: [],
    loading: false,
    error: null,
  });

  useEffect(() => {
    if (activeInspector !== 'runtime') {
      return;
    }

    let cancelled = false;

    async function fetchRuntimeState() {
      setRuntimeSnapshot((current) => ({
        ...current,
        loading: true,
        error: null,
      }));

      try {
        const [agentsResponse, specsResponse] = await Promise.all([
          fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/agents`),
          fetch(
            `${apiUrl}/api/v1/settings/model-route-registry/workspace-executor?workspace_id=${encodeURIComponent(
              workspaceId,
            )}`,
          ),
        ]);

        if (!agentsResponse.ok) {
          throw new Error(`Failed to fetch agents: ${agentsResponse.status}`);
        }
        if (!specsResponse.ok) {
          throw new Error(`Failed to fetch executor route policy: ${specsResponse.status}`);
        }

        const [agentsData, specsData] = await Promise.all([agentsResponse.json(), specsResponse.json()]);
        if (!cancelled) {
          const boundRuntimeIds = new Set<string>();
          const primaryRuntime = specsData.primary_executor_runtime || specsData.resolved_executor_runtime;
          if (primaryRuntime) {
            boundRuntimeIds.add(primaryRuntime);
          }
          Object.entries(specsData.surfaces || {}).forEach(([surface, state]) => {
            const surfaceState = state as { enabled?: boolean; preferred_runtime_id?: string | null };
            if (surfaceState.enabled) {
              boundRuntimeIds.add(surface);
            }
            if (surfaceState.preferred_runtime_id) {
              boundRuntimeIds.add(surfaceState.preferred_runtime_id);
            }
          });
          setRuntimeSnapshot({
            resolvedRuntime: primaryRuntime || null,
            dispatchChain: Array.isArray(specsData.dispatch_chain) ? specsData.dispatch_chain : [],
            boundRuntimeIds: Array.from(boundRuntimeIds),
            agents: Array.isArray(agentsData.agents) ? agentsData.agents : [],
            loading: false,
            error: null,
          });
        }
      } catch (error) {
        if (!cancelled) {
          setRuntimeSnapshot((current) => ({
            ...current,
            loading: false,
            error: error instanceof Error ? error.message : 'Failed to fetch runtime state.',
          }));
        }
      }
    }

    void fetchRuntimeState();

    return () => {
      cancelled = true;
    };
  }, [activeInspector, apiUrl, workspaceId]);

  return runtimeSnapshot;
}
