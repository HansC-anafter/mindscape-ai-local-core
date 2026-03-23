'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { t } from '@/lib/i18n';
import StoragePathConfigModal from '@/components/StoragePathConfigModal';
import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { useRouter } from 'next/navigation';

import TimelineExecutionSections from './timeline/TimelineExecutionSections';
import TimelineItemsDrawer from './timeline/TimelineItemsDrawer';
import {
  buildExecutionStepMap,
  upsertExecutionStepMap,
} from './timeline/helpers';
import {
  showExecutionRestartedNotification,
  showExecutionRestartErrorNotification,
} from './timeline/restartNotifications';
import type {
  ExecutionSession,
  ExecutionStep,
  PendingRestartInfo,
  TimelineItem,
  TimelinePanelProps,
} from './timeline/types';

export default function TimelinePanel({
  workspaceId,
  apiUrl,
  focusExecutionId = null,
  onClearFocus,
  showArchivedOnly = false,
  onArtifactClick,
}: TimelinePanelProps) {
  const router = useRouter();
  const contextData = useWorkspaceDataOptional();

  const [timelineItems, setTimelineItems] = useState<TimelineItem[]>([]);
  const [localExecutions, setLocalExecutions] = useState<ExecutionSession[]>([]);
  const [executionSteps, setExecutionSteps] = useState<Map<string, ExecutionStep[]>>(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showStorageConfigModal, setShowStorageConfigModal] = useState(false);
  const [localWorkspace, setLocalWorkspace] = useState<any>(null);
  const [retryTimelineItemId, setRetryTimelineItemId] = useState<string | null>(null);
  const [pendingRestart, setPendingRestart] = useState<PendingRestartInfo | null>(null);
  const timelineScrollContainerRef = useRef<HTMLDivElement>(null);
  const hasLoadedRef = useRef<string | null>(null);
  const executionsLoadedRef = useRef<string | null>(null);
  const hasCheckedRestartRef = useRef<string | null>(null);
  const isFirstLoadRef = useRef(true);
  const prevExecutionsLengthRef = useRef(0);

  const executions = contextData?.executions || localExecutions;
  const workspace = contextData?.workspace || localWorkspace;

  const contextExecutionSteps = useMemo(() => {
    if (!contextData?.executions) {
      return null;
    }
    return buildExecutionStepMap(contextData.executions as ExecutionSession[]);
  }, [contextData?.executions]);

  const effectiveExecutionSteps = contextExecutionSteps || executionSteps;

  const handleExecutionClick = useCallback(
    (executionId: string) => {
      router.push(`/workspaces/${workspaceId}/executions/${executionId}`);
    },
    [router, workspaceId]
  );

  const loadWorkspace = useCallback(async () => {
    if (contextData) {
      return;
    }

    try {
      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}`);
      if (!response.ok) {
        return;
      }
      const workspaceData = await response.json();
      setLocalWorkspace(workspaceData);
    } catch (err) {
      console.error('Failed to load workspace:', err);
    }
  }, [apiUrl, contextData, workspaceId]);

  const loadExecutions = useCallback(async () => {
    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/tasks?limit=100&include_completed=true&task_type=execution`
      );
      if (!response.ok) {
        throw new Error(`Failed to load executions: ${response.status}`);
      }

      const data = await response.json();
      const executionsList: ExecutionSession[] = (data.tasks || []).map((task: any) => ({
        execution_id: task.id,
        status: task.status,
        workspace_id: task.workspace_id,
        project_id: task.project_id,
        playbook_code: task.pack_id,
        created_at: task.created_at,
        started_at: task.started_at,
        completed_at: task.completed_at,
        current_step_index: 0,
        total_steps: 0,
        task,
        steps: [],
      }));

      setLocalExecutions(executionsList);
      setExecutionSteps(buildExecutionStepMap(executionsList));
    } catch (err) {
      console.error('Failed to load executions:', err);
    }
  }, [apiUrl, workspaceId]);

  const loadTimelineItems = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/timeline?limit=50`
      );
      if (!response.ok) {
        throw new Error(`Failed to load timeline: ${response.status}`);
      }

      const data = await response.json();
      setTimelineItems(data.timeline_items || data.events || []);
    } catch (err: any) {
      console.error('Failed to load timeline items:', err);
      setError(err.message || 'Failed to load timeline');
    } finally {
      setLoading(false);
    }
  }, [apiUrl, workspaceId]);

  const handleExecutionUpdate = useCallback(
    (
      previousExecution: ExecutionSession,
      updatedExecution: ExecutionSession,
      updatedStep?: ExecutionStep
    ) => {
      const statusChanged = updatedExecution.status !== previousExecution.status;
      const stepChanged =
        updatedExecution.current_step_index !== previousExecution.current_step_index;
      const totalStepsChanged =
        updatedExecution.total_steps !== previousExecution.total_steps;

      if (contextData) {
        if (statusChanged || stepChanged || totalStepsChanged) {
          contextData.refreshExecutions();
          if (
            updatedExecution.status === 'succeeded' ||
            updatedExecution.status === 'failed'
          ) {
            contextData.refreshTasks();
          }
        }
        return;
      }

      setLocalExecutions((previous) =>
        previous.map((execution) =>
          execution.execution_id === updatedExecution.execution_id
            ? updatedExecution
            : execution
        )
      );

      if (updatedStep) {
        setExecutionSteps((previous) =>
          upsertExecutionStepMap(
            previous,
            previousExecution.execution_id,
            updatedStep
          )
        );
      }

      if (statusChanged || stepChanged || totalStepsChanged) {
        void loadExecutions();
      }
    },
    [contextData, loadExecutions]
  );

  useEffect(() => {
    if (hasCheckedRestartRef.current === workspaceId) {
      return;
    }

    hasCheckedRestartRef.current = workspaceId;

    const forceRefresh = sessionStorage.getItem('force_refresh_executions');
    if (forceRefresh === 'true') {
      sessionStorage.removeItem('force_refresh_executions');
      window.setTimeout(() => {
        if (contextData && typeof contextData.refreshExecutions === 'function') {
          contextData.refreshExecutions();
        } else {
          void loadExecutions();
        }
      }, 100);
    }

    const restartInfo = sessionStorage.getItem('pending_restart');
    if (!restartInfo) {
      return;
    }

    try {
      const info = JSON.parse(restartInfo) as PendingRestartInfo;
      if (Date.now() - info.timestamp < 30000 && info.workspace_id === workspaceId) {
        setPendingRestart(info);
      } else {
        sessionStorage.removeItem('pending_restart');
      }
    } catch (error) {
      sessionStorage.removeItem('pending_restart');
    }
  }, [contextData, loadExecutions, workspaceId]);

  useEffect(() => {
    const handleExecutionRestarted = (event: Event) => {
      const detail = (event as CustomEvent).detail;
      if (detail.workspace_id !== workspaceId) {
        return;
      }

      setPendingRestart(null);
      sessionStorage.removeItem('pending_restart');
      showExecutionRestartedNotification({
        executionId: detail.execution_id,
        workspaceId: detail.workspace_id,
        playbookCode: detail.playbook_code,
      });
    };

    const handleExecutionRestartError = (event: Event) => {
      showExecutionRestartErrorNotification((event as CustomEvent).detail.message);
    };

    window.addEventListener(
      'execution-restarted',
      handleExecutionRestarted as EventListener
    );
    window.addEventListener(
      'execution-restart-error',
      handleExecutionRestartError as EventListener
    );

    return () => {
      window.removeEventListener(
        'execution-restarted',
        handleExecutionRestarted as EventListener
      );
      window.removeEventListener(
        'execution-restart-error',
        handleExecutionRestartError as EventListener
      );
    };
  }, [workspaceId]);

  useEffect(() => {
    const currentExecutionsLength = executions.length;
    if (
      pendingRestart &&
      currentExecutionsLength > 0 &&
      currentExecutionsLength !== prevExecutionsLengthRef.current
    ) {
      const matchingExecution = executions.find(
        (execution) =>
          execution.playbook_code === pendingRestart.playbook_code &&
          execution.created_at &&
          (Date.parse(execution.created_at) || 0) > pendingRestart.timestamp
      );

      if (matchingExecution) {
        setPendingRestart(null);
        sessionStorage.removeItem('pending_restart');
      }
      prevExecutionsLengthRef.current = currentExecutionsLength;
    } else if (currentExecutionsLength !== prevExecutionsLengthRef.current) {
      prevExecutionsLengthRef.current = currentExecutionsLength;
    }
  }, [executions, pendingRestart]);

  useEffect(() => {
    if (hasLoadedRef.current !== workspaceId) {
      void loadTimelineItems();
      hasLoadedRef.current = workspaceId;
    }

    if (executionsLoadedRef.current !== workspaceId) {
      executionsLoadedRef.current = workspaceId;
      if (!contextData) {
        void loadExecutions();
        void loadWorkspace();
      }
    }

    if (contextData) {
      return;
    }

    let debounceTimer: NodeJS.Timeout | null = null;
    let isPending = false;

    const handleChatUpdate = () => {
      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }

      debounceTimer = setTimeout(() => {
        if (isPending) {
          return;
        }
        isPending = true;
        void Promise.all([loadTimelineItems(), loadExecutions()]).finally(() => {
          isPending = false;
        });
      }, 1000);
    };

    window.addEventListener('workspace-chat-updated', handleChatUpdate);
    return () => {
      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }
      window.removeEventListener('workspace-chat-updated', handleChatUpdate);
    };
  }, [contextData, loadExecutions, loadTimelineItems, loadWorkspace, workspaceId]);

  useEffect(() => {
    (window as any).__timelinePanelRefresh = loadTimelineItems;
  }, [loadTimelineItems]);

  useEffect(() => {
    if (timelineItems.length === 0 || loading) {
      return;
    }

    const delay = isFirstLoadRef.current ? 300 : 100;
    const scrollTimer = window.setTimeout(() => {
      if (timelineScrollContainerRef.current) {
        timelineScrollContainerRef.current.scrollTop = 0;
      }
    }, delay);

    isFirstLoadRef.current = false;
    return () => window.clearTimeout(scrollTimer);
  }, [timelineItems, loading]);

  const handleStorageConfigSuccess = useCallback(async () => {
    await loadWorkspace();

    if (retryTimelineItemId) {
      try {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/timeline-items/${retryTimelineItemId}/retry-artifact`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
          }
        );

        if (!response.ok) {
          const error = await response.json();
          alert(
            `${t('configSaved' as any)}, ${t('retryFailed' as any)}: ${
              error.detail || t('unknownError' as any)
            }`
          );
          return;
        }

        const result = await response.json();
        if (!result.success) {
          alert(
            `${t('configSaved' as any)}, ${t('retryFailed' as any)}: ${
              result.error || t('unknownError' as any)
            }`
          );
          return;
        }

        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
        setRetryTimelineItemId(null);
      } catch (err: any) {
        alert(
          `${t('configSaved' as any)}, ${t('retryFailed' as any)}: ${
            err.message || t('unknownError' as any)
          }`
        );
      }
    }

    setShowStorageConfigModal(false);
    setRetryTimelineItemId(null);
  }, [apiUrl, loadWorkspace, retryTimelineItemId, workspaceId]);

  if (loading && timelineItems.length === 0) {
    return (
      <div className="flex h-full flex-col">
        <div className="flex-1 overflow-y-auto px-2 pt-2">
          <div className="text-xs text-secondary dark:text-gray-300">Loading...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full flex-col">
        <div className="flex-1 overflow-y-auto px-2 pt-2">
          <div className="text-xs text-red-600 dark:text-red-400">{error}</div>
          <button
            onClick={() => void loadTimelineItems()}
            className="mt-1 text-xs text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <>
      <StoragePathConfigModal
        isOpen={showStorageConfigModal}
        onClose={() => {
          setShowStorageConfigModal(false);
          setRetryTimelineItemId(null);
        }}
        workspace={workspace}
        workspaceId={workspaceId}
        apiUrl={apiUrl}
        onSuccess={handleStorageConfigSuccess}
      />
      <div className="flex h-full flex-col">
        <div
          ref={timelineScrollContainerRef}
          data-timeline-container
          className="flex-1 overflow-y-auto px-2 pt-2"
        >
          <TimelineExecutionSections
            executions={executions}
            executionSteps={effectiveExecutionSteps}
            focusExecutionId={focusExecutionId}
            onClearFocus={onClearFocus}
            showArchivedOnly={showArchivedOnly}
            onArtifactClick={onArtifactClick}
            onExecutionClick={handleExecutionClick}
            onExecutionUpdate={handleExecutionUpdate}
            onRefreshExecutions={loadExecutions}
            pendingRestart={pendingRestart}
            apiUrl={apiUrl}
            workspaceId={workspaceId}
          />
        </div>

        <TimelineItemsDrawer timelineItems={timelineItems} />
      </div>
    </>
  );
}
