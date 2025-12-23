import { useState, useEffect, useCallback } from 'react';
import { useExecutionStream } from '@/hooks/useExecutionStream';
import type { ExecutionSession, ExecutionStats } from '../types/execution';
import { formatDuration, convertStepIndexTo1Based } from '../utils/execution-inspector';
import { getSandboxByProject } from '@/lib/sandbox-api';

export interface UseExecutionCoreResult {
  execution: ExecutionSession | null;
  loading: boolean;
  error: Error | null;
  duration: string;
  projectId: string | null;
  sandboxId: string | null;
  workspaceName: string | undefined;
  projectName: string | undefined;
  executionStats: ExecutionStats | undefined;
  currentStepIndex: number;
  setCurrentStepIndex: (index: number) => void;
}

export function useExecutionCore(
  executionId: string | null,
  workspaceId: string,
  apiUrl: string,
  workspaceData?: { workspace?: { title?: string } }
): UseExecutionCoreResult {
  const [execution, setExecution] = useState<ExecutionSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [duration, setDuration] = useState<string>('');
  const [projectId, setProjectId] = useState<string | null>(null);
  const [sandboxId, setSandboxId] = useState<string | null>(null);
  const [workspaceName, setWorkspaceName] = useState<string | undefined>();
  const [projectName, setProjectName] = useState<string | undefined>();
  const [executionStats, setExecutionStats] = useState<ExecutionStats | undefined>();
  const [currentStepIndex, setCurrentStepIndex] = useState<number>(1);

  // Load execution details
  useEffect(() => {
    // Reset state immediately when executionId changes
    if (!executionId) {
      setExecution(null);
      setLoading(false);
      setCurrentStepIndex(1);
      setProjectId(null);
      setSandboxId(null);
      setWorkspaceName(undefined);
      setProjectName(undefined);
      setExecutionStats(undefined);
      setDuration('');
      setError(null);
      return;
    }

    let cancelled = false;

    const loadExecution = async () => {
      const currentExecutionId = executionId;

      try {
        setError(null);
        setLoading(true);
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${currentExecutionId}`
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

          if (data.execution_id !== currentExecutionId) {
            console.error('[useExecutionCore] Execution ID mismatch!', {
              requested: currentExecutionId,
              received: data.execution_id
            });
          }

          setExecution(data);
          const validStepIndex = convertStepIndexTo1Based(
            data.current_step_index || 0,
            data.total_steps
          );
          setCurrentStepIndex(validStepIndex);

          // Extract sandbox_id directly from execution response (preferred)
          // Also extract project_id for fallback query
          const execProjectId = data.project_id
            || data.execution_context?.project_id
            || data.task?.project_id;

          if (data.sandbox_id) {
            console.log('[useExecutionCore] Found sandbox_id in execution response:', data.sandbox_id);
            setSandboxId(data.sandbox_id);
            // Still set projectId for reference
            if (execProjectId) {
              setProjectId(execProjectId);
            }
          } else {
            // Fallback: Extract project_id and query sandbox
            console.log('[useExecutionCore] No sandbox_id in execution response, project_id:', execProjectId);
            if (execProjectId) {
              setProjectId(execProjectId);
              // sandboxId will be set by useEffect when projectId changes
            } else {
              setProjectId(null);
              setSandboxId(null);
            }
          }
        } else {
          // Check again after async operation
          if (cancelled || executionId !== currentExecutionId) {
            return;
          }
          const error = new Error(`Failed to load execution: ${response.status}`);
          setError(error);
          console.error('[useExecutionCore] Failed to load execution:', response.status, 'for executionId:', currentExecutionId);
        }
      } catch (err) {
        // Check again after async operation
        if (cancelled || executionId !== currentExecutionId) {
          return;
        }
        const error = err instanceof Error ? err : new Error('Unknown error');
        setError(error);
        console.error('[useExecutionCore] Failed to load execution:', err, 'for executionId:', currentExecutionId);
      } finally {
        if (!cancelled && executionId === currentExecutionId) {
          setLoading(false);
        }
      }
    };

    loadExecution();

    // Cleanup function
    return () => {
      cancelled = true;
    };
  }, [executionId, workspaceId, apiUrl]);

  // Calculate and update duration
  useEffect(() => {
    if (!execution?.started_at) {
      setDuration('');
      return;
    }

    const updateDuration = () => {
      const formatted = formatDuration(execution.started_at, execution.completed_at);
      setDuration(formatted);
    };

    updateDuration();

    if (execution.status === 'running') {
      const interval = setInterval(updateDuration, 1000);
      return () => clearInterval(interval);
    }
  }, [execution?.started_at, execution?.status, execution?.completed_at]);

  // Load workspace name
  useEffect(() => {
    if (workspaceData?.workspace?.title) {
      setWorkspaceName(workspaceData.workspace.title);
    } else {
      const loadWorkspace = async () => {
        try {
          const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}`);
          if (response.ok) {
            const data = await response.json();
            setWorkspaceName(data.title || data.name);
          }
        } catch (err) {
          console.error('[useExecutionCore] Failed to load workspace:', err);
        }
      };
      loadWorkspace();
    }
  }, [workspaceId, apiUrl, workspaceData]);

  // Load project name
  useEffect(() => {
    if (!projectId) {
      setProjectName(undefined);
      return;
    }
    const loadProject = async () => {
      try {
        const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/projects/${projectId}`);
        if (response.ok) {
          const data = await response.json();
          setProjectName(data.name || data.title);
        }
      } catch (err) {
        console.error('[useExecutionCore] Failed to load project:', err);
      }
    };
    loadProject();
  }, [projectId, workspaceId, apiUrl]);

  // Calculate execution stats
  useEffect(() => {
    if (!projectId) {
      setExecutionStats(undefined);
      return;
    }
    const loadStats = async () => {
      try {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/projects/${projectId}/execution-tree`
        );
        if (response.ok) {
          const data = await response.json();
          let concurrent = 0;
          let waitingConfirmation = 0;
          let completed = 0;

          if (data.playbookGroups) {
            data.playbookGroups.forEach((group: any) => {
              if (group.executions) {
                group.executions.forEach((exec: any) => {
                  if (exec.status === 'running') {
                    concurrent++;
                  } else if (exec.status === 'paused' || exec.currentStep?.status === 'waiting_confirmation') {
                    waitingConfirmation++;
                  } else if (exec.status === 'completed' || exec.status === 'succeeded') {
                    completed++;
                  }
                });
              }
            });
          }

          setExecutionStats({
            concurrent,
            waitingConfirmation,
            completed
          });
        } else if (response.status === 404) {
          // Endpoint not available, silently ignore
          setExecutionStats(undefined);
        }
      } catch (err) {
        // Silently ignore errors for optional endpoint
        setExecutionStats(undefined);
      }
    };
    loadStats();
  }, [projectId, workspaceId, apiUrl]);

  // Load sandbox ID
  useEffect(() => {
    if (!projectId) {
      setSandboxId(null);
      return;
    }
    const loadSandbox = async () => {
      try {
        console.log('[useExecutionCore] Loading sandbox for project:', projectId);
        const sandbox = await getSandboxByProject(workspaceId, projectId);
        if (sandbox?.sandbox_id) {
          console.log('[useExecutionCore] Found sandbox_id:', sandbox.sandbox_id);
          setSandboxId(sandbox.sandbox_id);
        } else {
          console.log('[useExecutionCore] No sandbox found for project:', projectId);
          setSandboxId(null);
        }
      } catch (err) {
        console.error('[useExecutionCore] Failed to load sandbox:', err);
        setSandboxId(null);
      }
    };
    if (projectId) {
      loadSandbox();
    }
  }, [projectId, workspaceId]);

  // Connect to SSE stream for execution updates
  useExecutionStream(
    executionId,
    workspaceId,
    apiUrl,
    useCallback((update) => {
      if (update.type === 'execution_update') {
        setExecution(update.execution);
        if (update.execution) {
          const validStepIndex = convertStepIndexTo1Based(
            update.execution.current_step_index || 0,
            update.execution.total_steps
          );
          setCurrentStepIndex(validStepIndex);
        } else {
          setCurrentStepIndex(1);
        }
      }
    }, [])
  );

  return {
    execution,
    loading,
    error,
    duration,
    projectId,
    sandboxId,
    workspaceName,
    projectName,
    executionStats,
    currentStepIndex,
    setCurrentStepIndex,
  };
}
