import { useState, useEffect } from 'react';
import type { WorkflowData } from '../types/execution';

export interface UseWorkflowDataResult {
  workflowData: WorkflowData | null;
  loading: boolean;
  error: Error | null;
}

export function useWorkflowData(
  executionId: string | null,
  workspaceId: string,
  apiUrl: string
): UseWorkflowDataResult {
  const [workflowData, setWorkflowData] = useState<WorkflowData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    // Reset state immediately when executionId changes
    if (!executionId) {
      setWorkflowData(null);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    const currentExecutionId = executionId;

    const loadWorkflowData = async () => {
      try {
        setError(null);
        setLoading(true);
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${currentExecutionId}/workflow`
        );

        // Check if component was unmounted or executionId changed
        if (cancelled || executionId !== currentExecutionId) {
          return;
        }

        if (response.ok) {
          const data = await response.json();

          // Check again after async operation
          if (cancelled || executionId !== currentExecutionId) {
            return;
          }

          if (data.workflow_result || data.handoff_plan) {
            setWorkflowData(data);
          } else {
            setWorkflowData(null);
          }
        } else if (response.status === 404) {
          // Check again after async operation
          if (cancelled || executionId !== currentExecutionId) {
            return;
          }
          setWorkflowData(null);
        } else {
          // Check again after async operation
          if (cancelled || executionId !== currentExecutionId) {
            return;
          }
          const error = new Error(`Failed to load workflow data: ${response.status}`);
          setError(error);
          setWorkflowData(null);
        }
      } catch (err) {
        // Check again after async operation
        if (cancelled || executionId !== currentExecutionId) {
          return;
        }
        const error = err instanceof Error ? err : new Error('Unknown error');
        setError(error);
        setWorkflowData(null);
      } finally {
        if (!cancelled && executionId === currentExecutionId) {
          setLoading(false);
        }
      }
    };

    loadWorkflowData();

    // Cleanup function
    return () => {
      cancelled = true;
    };
  }, [executionId, workspaceId, apiUrl]);

  return {
    workflowData,
    loading,
    error,
  };
}
