'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import type { CurrentExecution } from '@/components/workspace/CurrentExecutionBar';

interface ExecutionStartedEvent {
  type: 'execution_started';
  data: {
    executionId: string;
    playbookCode: string;
    playbookName?: string;
    runNumber: number;
  };
}

interface ExecutionConcurrentUpdateEvent {
  type: 'execution_concurrent_update';
  data: {
    playbookCode: string;
    executions: Array<{
      executionId: string;
      runNumber: number;
      status: string;
      progress?: number;
    }>;
  };
}

interface ExecutionCompletedEvent {
  type: 'execution_completed';
  data: {
    executionId: string;
  };
}

interface ExecutionFailedEvent {
  type: 'execution_failed';
  data: {
    executionId: string;
    error?: string;
  };
}

type ExecutionSSEEvent =
  | ExecutionStartedEvent
  | ExecutionConcurrentUpdateEvent
  | ExecutionCompletedEvent
  | ExecutionFailedEvent;

export function useCurrentExecution(workspaceId: string, apiUrl: string = '') {
  const [currentExecution, setCurrentExecution] = useState<CurrentExecution | null>(null);
  const executionTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const handleExecutionEvent = useCallback((event: ExecutionSSEEvent) => {
    switch (event.type) {
      case 'execution_started':
        setCurrentExecution({
          executionId: event.data.executionId,
          playbookCode: event.data.playbookCode,
          playbookName: event.data.playbookName || event.data.playbookCode,
          runNumber: event.data.runNumber,
          progress: 0,
          status: 'running',
        });
        break;

      case 'execution_concurrent_update':
        const latestExecution = event.data.executions[0];
        if (latestExecution) {
          setCurrentExecution(prev => {
            if (!prev || prev.executionId === latestExecution.executionId) {
              return {
                executionId: latestExecution.executionId,
                playbookCode: event.data.playbookCode,
                playbookName: prev?.playbookName || event.data.playbookCode,
                runNumber: latestExecution.runNumber,
                progress: latestExecution.progress || prev?.progress || 0,
                status: latestExecution.status as CurrentExecution['status'] || 'running',
              };
            }
            return prev;
          });
        }
        break;

      case 'execution_completed':
        setCurrentExecution(prev => {
          if (prev && prev.executionId === event.data.executionId) {
            return {
              ...prev,
              status: 'completed',
              progress: 100,
            };
          }
          return prev;
        });
        if (executionTimeoutRef.current) {
          clearTimeout(executionTimeoutRef.current);
        }
        executionTimeoutRef.current = setTimeout(() => {
          setCurrentExecution(null);
        }, 3000);
        break;

      case 'execution_failed':
        setCurrentExecution(prev => {
          if (prev && prev.executionId === event.data.executionId) {
            return {
              ...prev,
              status: 'failed',
            };
          }
          return prev;
        });
        if (executionTimeoutRef.current) {
          clearTimeout(executionTimeoutRef.current);
        }
        executionTimeoutRef.current = setTimeout(() => {
          setCurrentExecution(null);
        }, 5000);
        break;
    }
  }, []);

  useEffect(() => {
    const handleCustomEvent = (e: CustomEvent) => {
      if (e.detail && e.detail.type) {
        handleExecutionEvent(e.detail as ExecutionSSEEvent);
      }
    };

    window.addEventListener('execution-event', handleCustomEvent as EventListener);
    return () => {
      window.removeEventListener('execution-event', handleCustomEvent as EventListener);
      if (executionTimeoutRef.current) {
        clearTimeout(executionTimeoutRef.current);
      }
    };
  }, [handleExecutionEvent]);

  const handleViewDetail = useCallback(() => {
    if (currentExecution) {
      window.dispatchEvent(new CustomEvent('open-execution-inspector', {
        detail: {
          executionId: currentExecution.executionId,
          workspaceId,
        },
      }));
    }
  }, [currentExecution, workspaceId]);

  const handlePause = useCallback(async () => {
    if (!currentExecution || !apiUrl) return;

    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${currentExecution.executionId}/pause`,
        { method: 'POST' }
      );
      if (!response.ok) {
        console.error('Failed to pause execution');
      }
    } catch (err) {
      console.error('Error pausing execution:', err);
    }
  }, [currentExecution, workspaceId, apiUrl]);

  const handleCancel = useCallback(async () => {
    if (!currentExecution || !apiUrl) return;

    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${currentExecution.executionId}/cancel`,
        { method: 'POST' }
      );
      if (!response.ok) {
        console.error('Failed to cancel execution');
      } else {
        setCurrentExecution(null);
      }
    } catch (err) {
      console.error('Error canceling execution:', err);
    }
  }, [currentExecution, workspaceId, apiUrl]);

  return {
    currentExecution,
    handleViewDetail,
    handlePause,
    handleCancel,
  };
}

