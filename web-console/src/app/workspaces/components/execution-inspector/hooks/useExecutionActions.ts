import { useState, useCallback } from 'react';
import type { ExecutionSession, ExecutionStep } from '../types/execution';
import { convertStepIndexTo1Based } from '../utils/execution-inspector';

export interface UseExecutionActionsResult {
  isStopping: boolean;
  isReloading: boolean;
  isRestarting: boolean;
  confirmStep: (step: ExecutionStep) => Promise<void>;
  rejectStep: (step: ExecutionStep) => Promise<void>;
  cancelExecution: () => Promise<void>;
  reloadPlaybook: () => Promise<void>;
  restartExecution: () => Promise<void>;
}

export interface UseExecutionActionsCallbacks {
  onExecutionUpdate?: (execution: ExecutionSession) => void;
  onStepIndexUpdate?: (stepIndex: number) => void;
  onError?: (error: Error) => void;
  onSuccess?: (message: string) => void;
}

export function useExecutionActions(
  executionId: string | null,
  workspaceId: string,
  apiUrl: string,
  execution: ExecutionSession | null,
  callbacks?: UseExecutionActionsCallbacks
): UseExecutionActionsResult {
  const [isStopping, setIsStopping] = useState(false);
  const [isReloading, setIsReloading] = useState(false);
  const [isRestarting, setIsRestarting] = useState(false);

  const confirmStep = useCallback(async (step: ExecutionStep) => {
    if (!executionId || !step) return;

    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/steps/${step.id}/confirm`,
        { method: 'POST' }
      );

      if (response.ok) {
        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
        const execResponse = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}`
        );
        if (execResponse.ok) {
          const execData = await execResponse.json();
          const validStepIndex = convertStepIndexTo1Based(
            execData.current_step_index || 0,
            execData.total_steps
          );
          callbacks?.onExecutionUpdate?.(execData);
          callbacks?.onStepIndexUpdate?.(validStepIndex);
        }
      } else {
        const error = new Error('Failed to confirm step');
        callbacks?.onError?.(error);
      }
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Unknown error');
      console.error('[useExecutionActions] Failed to confirm step:', err);
      callbacks?.onError?.(error);
    }
  }, [executionId, workspaceId, apiUrl, callbacks]);

  const rejectStep = useCallback(async (step: ExecutionStep) => {
    if (!executionId || !step) return;

    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/steps/${step.id}/reject`,
        { method: 'POST' }
      );

      if (response.ok) {
        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
        const execResponse = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}`
        );
        if (execResponse.ok) {
          const execData = await execResponse.json();
          const validStepIndex = convertStepIndexTo1Based(
            execData.current_step_index || 0,
            execData.total_steps
          );
          callbacks?.onExecutionUpdate?.(execData);
          callbacks?.onStepIndexUpdate?.(validStepIndex);
        }
      } else {
        const error = new Error('Failed to reject step');
        callbacks?.onError?.(error);
      }
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Unknown error');
      console.error('[useExecutionActions] Failed to reject step:', err);
      callbacks?.onError?.(error);
    }
  }, [executionId, workspaceId, apiUrl, callbacks]);

  const cancelExecution = useCallback(async () => {
    if (!executionId || isStopping) return;

    setIsStopping(true);
    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/cancel`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      if (response.ok) {
        const execResponse = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}`
        );
        if (execResponse.ok) {
          const execData = await execResponse.json();
          callbacks?.onExecutionUpdate?.(execData);
          callbacks?.onSuccess?.('Execution cancelled successfully');
        }
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to cancel execution' }));
        const error = new Error(errorData.detail || 'Failed to cancel execution');
        callbacks?.onError?.(error);
      }
    } catch (error) {
      const err = error instanceof Error ? error : new Error('Unknown error');
      console.error('[useExecutionActions] Error cancelling execution:', error);
      callbacks?.onError?.(err);
    } finally {
      setIsStopping(false);
    }
  }, [executionId, workspaceId, apiUrl, isStopping, callbacks]);

  const reloadPlaybook = useCallback(async () => {
    if (!execution?.playbook_code || isReloading) return;

    setIsReloading(true);
    try {
      const response = await fetch(
        `${apiUrl}/api/v1/playbooks/${execution.playbook_code}/reload?locale=zh-TW`,
        { method: 'POST' }
      );

      if (response.ok) {
        window.dispatchEvent(new CustomEvent('playbook-reloaded', {
          detail: { playbookCode: execution.playbook_code }
        }));
        callbacks?.onSuccess?.('Playbook reloaded successfully');
        // Reload the page to reflect changes
        window.location.reload();
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to reload playbook' }));
        const error = new Error(errorData.detail || 'Failed to reload playbook');
        callbacks?.onError?.(error);
      }
    } catch (error) {
      const err = error instanceof Error ? error : new Error('Unknown error');
      console.error('[useExecutionActions] Error reloading playbook:', error);
      callbacks?.onError?.(err);
    } finally {
      setIsReloading(false);
    }
  }, [execution?.playbook_code, apiUrl, isReloading, callbacks]);

  const restartExecution = useCallback(async () => {
    if (!execution?.playbook_code || !executionId || isRestarting) return;

    setIsRestarting(true);
    try {
      // Store restart info in sessionStorage
      const restartInfo = {
        playbook_code: execution.playbook_code,
        workspace_id: workspaceId,
        timestamp: Date.now()
      };
      sessionStorage.setItem('pending_restart', JSON.stringify(restartInfo));
      sessionStorage.setItem('force_refresh_executions', 'true');

      // Navigate to workspace immediately
      window.location.href = `/workspaces/${workspaceId}`;

      // Cancel current execution if running (fire and forget)
      if (execution.status === 'running') {
        fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/cancel`,
          { method: 'POST' }
        ).catch(err => console.warn('[useExecutionActions] Failed to cancel execution:', err));
      }

      // Start new execution
      const inputs = { ...(execution.execution_context || {}) };
      delete inputs.execution_id;
      delete inputs.status;
      delete inputs.current_step_index;

      fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/playbooks/${execution.playbook_code}/execute`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            inputs: inputs,
            execution_mode: 'async'
          })
        }
      )
        .then(async (response) => {
          if (response.ok) {
            const result = await response.json();
            const newExecutionId = result.execution_id || result.result?.execution_id;
            if (newExecutionId) {
              sessionStorage.setItem('restart_success', JSON.stringify({
                execution_id: newExecutionId,
                workspace_id: workspaceId,
                playbook_code: execution.playbook_code,
                timestamp: Date.now()
              }));
              sessionStorage.removeItem('pending_restart');
              window.dispatchEvent(new CustomEvent('execution-restarted', {
                detail: {
                  execution_id: newExecutionId,
                  workspace_id: workspaceId,
                  playbook_code: execution.playbook_code
                }
              }));
            } else {
              sessionStorage.removeItem('pending_restart');
              window.dispatchEvent(new CustomEvent('execution-restart-error', {
                detail: { message: 'Execution started but failed to get execution ID' }
              }));
            }
          } else {
            sessionStorage.removeItem('pending_restart');
            const error = await response.json().catch(() => ({ detail: 'Failed to restart execution' }));
            window.dispatchEvent(new CustomEvent('execution-restart-error', {
              detail: { message: error.detail || 'Failed to restart execution' }
            }));
          }
        })
        .catch((error) => {
          sessionStorage.removeItem('pending_restart');
          console.error('[useExecutionActions] Error restarting execution:', error);
          window.dispatchEvent(new CustomEvent('execution-restart-error', {
            detail: { message: 'Failed to restart execution. Please try again.' }
          }));
        });
    } catch (error) {
      sessionStorage.removeItem('pending_restart');
      const err = error instanceof Error ? error : new Error('Unknown error');
      console.error('[useExecutionActions] Error restarting execution:', error);
      callbacks?.onError?.(err);
    } finally {
      setIsRestarting(false);
    }
  }, [execution, executionId, workspaceId, apiUrl, isRestarting, callbacks]);

  return {
    isStopping,
    isReloading,
    isRestarting,
    confirmStep,
    rejectStep,
    cancelExecution,
    reloadPlaybook,
    restartExecution,
  };
}
