import { useEffect, useMemo, useState } from 'react';
import type {
  RemoteChildExecution,
  RemoteExecutionAggregate,
} from '../types/execution';

interface UseRemoteChildExecutionsResult {
  remoteChildren: RemoteChildExecution[];
  aggregate: RemoteExecutionAggregate;
  loading: boolean;
}

const EMPTY_AGGREGATE: RemoteExecutionAggregate = {
  totalRemoteChildren: 0,
  replayAttempts: 0,
  supersededByReplay: 0,
  uniqueTargetDevices: [],
};

export function useRemoteChildExecutions(
  executionId: string | null,
  workspaceId: string,
  apiUrl: string,
): UseRemoteChildExecutionsResult {
  const [remoteChildren, setRemoteChildren] = useState<RemoteChildExecution[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!executionId) {
      setRemoteChildren([]);
      setLoading(false);
      return;
    }

    let cancelled = false;

    const loadRemoteChildren = async () => {
      try {
        setLoading(true);
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/executions?parent_execution_id=${encodeURIComponent(executionId)}&limit=100`,
        );
        if (!response.ok || cancelled) {
          return;
        }

        const data = await response.json();
        if (cancelled) {
          return;
        }

        const executions = Array.isArray(data.executions) ? data.executions : [];
        const filtered = executions.filter((item: RemoteChildExecution) => {
          const summary = item?.remote_execution_summary;
          return summary && summary.is_workflow_step_child;
        });
        setRemoteChildren(filtered);
      } catch (error) {
        if (!cancelled) {
          console.error('[useRemoteChildExecutions] Failed to load remote child executions:', error);
          setRemoteChildren([]);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadRemoteChildren();
    return () => {
      cancelled = true;
    };
  }, [executionId, workspaceId, apiUrl]);

  const aggregate = useMemo<RemoteExecutionAggregate>(() => {
    if (remoteChildren.length === 0) {
      return EMPTY_AGGREGATE;
    }

    const uniqueTargetDevices = new Set<string>();
    let replayAttempts = 0;
    let supersededByReplay = 0;

    for (const child of remoteChildren) {
      const summary = child.remote_execution_summary;
      if (!summary) continue;
      if (summary.target_device_id) {
        uniqueTargetDevices.add(summary.target_device_id);
      }
      if (summary.is_replay_attempt) {
        replayAttempts += 1;
      }
      if (summary.is_superseded_by_replay) {
        supersededByReplay += 1;
      }
    }

    return {
      totalRemoteChildren: remoteChildren.length,
      replayAttempts,
      supersededByReplay,
      uniqueTargetDevices: Array.from(uniqueTargetDevices),
    };
  }, [remoteChildren]);

  return {
    remoteChildren,
    aggregate,
    loading,
  };
}
