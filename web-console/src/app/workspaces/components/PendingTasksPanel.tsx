'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { useT } from '@/lib/i18n';
import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { getApiBaseUrl } from '../../../lib/api-url';

import BackgroundTaskSuggestions from './pendingTasks/BackgroundTaskSuggestions';
import {
  getVisibleBackgroundTasks,
  isPendingTask,
  laserScanStyle,
  splitPendingTaskCollections,
} from './pendingTasks/helpers';
import PendingTaskList from './pendingTasks/PendingTaskList';
import RejectTaskDialog from './pendingTasks/RejectTaskDialog';
import RestoreTaskNotifications from './pendingTasks/RestoreTaskNotifications';
import type {
  BackgroundRoutine,
  PendingTask,
  PendingTasksPanelProps,
  RejectedTaskState,
} from './pendingTasks/types';

export default function PendingTasksPanel({
  workspaceId,
  apiUrl = getApiBaseUrl(),
  workspace: workspaceProp,
  onTaskCountChange,
}: PendingTasksPanelProps) {
  const t = useT();
  const contextData = useWorkspaceDataOptional();

  const [localTasks, setLocalTasks] = useState<PendingTask[]>([]);
  const [backgroundTasks, setBackgroundTasks] = useState<PendingTask[]>([]);
  const [backgroundRoutines, setBackgroundRoutines] = useState<BackgroundRoutine[]>([]);
  const [loading, setLoading] = useState(false);
  const [executingTaskIds, setExecutingTaskIds] = useState<Set<string>>(new Set());
  const [taskStatusMessages, setTaskStatusMessages] = useState<Record<string, string>>({});
  const [rejectedTasks, setRejectedTasks] = useState<Record<string, RejectedTaskState>>({});
  const [showRejectDialog, setShowRejectDialog] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [rejectComment, setRejectComment] = useState('');
  const loadingRef = useRef(false);

  const allTasks = contextData?.tasks || localTasks;
  const workspace = contextData?.workspace || workspaceProp;

  const processedTasks = useMemo(() => {
    if (!allTasks || allTasks.length === 0) {
      return [];
    }
    return splitPendingTaskCollections(allTasks).displayTasks;
  }, [allTasks]);

  const pendingBackgroundTasks = useMemo(() => {
    if (contextData) {
      return splitPendingTaskCollections(allTasks).backgroundTasks.filter(isPendingTask);
    }
    return backgroundTasks;
  }, [allTasks, backgroundTasks, contextData]);

  const visibleBackgroundTasks = useMemo(
    () => getVisibleBackgroundTasks(pendingBackgroundTasks, backgroundRoutines),
    [backgroundRoutines, pendingBackgroundTasks]
  );

  useEffect(() => {
    onTaskCountChange?.(processedTasks.length);
  }, [onTaskCountChange, processedTasks.length]);

  const clearTaskExecutionState = useCallback((taskId: string) => {
    setExecutingTaskIds((previous) => {
      const updated = new Set(previous);
      updated.delete(taskId);
      return updated;
    });
    setTaskStatusMessages((previous) => {
      const updated = { ...previous };
      delete updated[taskId];
      return updated;
    });
  }, []);

  const loadBackgroundRoutines = useCallback(async () => {
    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/background-routines`
      );
      if (!response.ok) {
        return;
      }
      const data = await response.json();
      setBackgroundRoutines(data.routines || []);
    } catch (error) {
      console.error('Failed to load background routines:', error);
    }
  }, [apiUrl, workspaceId]);

  useEffect(() => {
    if (contextData) {
      void loadBackgroundRoutines();
    }
  }, [contextData, loadBackgroundRoutines]);

  const loadTasks = useCallback(async () => {
    if (contextData || loadingRef.current) {
      return;
    }

    try {
      loadingRef.current = true;
      setLoading(true);

      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/tasks?limit=20&include_completed=true`
      );
      if (!response.ok) {
        if (response.status === 429) {
          console.warn('Rate limited when loading tasks, will retry later');
        }
        return;
      }

      const data = await response.json();
      const fetchedTasks = data.tasks || [];
      const { backgroundTasks: fetchedBackgroundTasks } =
        splitPendingTaskCollections(fetchedTasks);

      setLocalTasks(fetchedTasks);
      setBackgroundTasks(fetchedBackgroundTasks.filter(isPendingTask));
      await loadBackgroundRoutines();
    } catch (error) {
      console.error('[PendingTasksPanel] Failed to load tasks:', error);
    } finally {
      loadingRef.current = false;
      setLoading(false);
    }
  }, [apiUrl, contextData, loadBackgroundRoutines, workspaceId]);

  useEffect(() => {
    if (!contextData) {
      void loadTasks();
    }

    if (contextData) {
      return;
    }

    let debounceTimer: NodeJS.Timeout | null = null;
    let isPending = false;

    const scheduleReload = () => {
      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }
      debounceTimer = setTimeout(() => {
        if (isPending || loadingRef.current) {
          return;
        }
        isPending = true;
        void loadTasks().finally(() => {
          isPending = false;
        });
      }, 2000);
    };

    window.addEventListener('workspace-chat-updated', scheduleReload);
    window.addEventListener('workspace-task-updated', scheduleReload);

    return () => {
      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }
      window.removeEventListener('workspace-chat-updated', scheduleReload);
      window.removeEventListener('workspace-task-updated', scheduleReload);
    };
  }, [contextData, loadTasks]);

  const handleEnableBackgroundRoutine = useCallback(
    async (playbookCode: string) => {
      try {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/background-routines`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              playbook_code: playbookCode,
              config: {},
            }),
          }
        );

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        await loadBackgroundRoutines();
        await loadTasks();
        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
      } catch (error) {
        console.error('Failed to enable background routine:', error);
        alert(
          `${t('enableFailed' as any)}: ${
            error instanceof Error ? error.message : t('unknownError' as any)
          }`
        );
      }
    },
    [apiUrl, loadBackgroundRoutines, loadTasks, t, workspaceId]
  );

  const handleRetryArtifact = useCallback(
    async (task: PendingTask) => {
      try {
        const timelineResponse = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/timeline?limit=100`
        );
        if (!timelineResponse.ok) {
          alert(t('timelineItemUnavailable' as any));
          return;
        }

        const timelineData = await timelineResponse.json();
        const timelineItem = timelineData.items?.find((item: any) => item.task_id === task.id);
        if (!timelineItem) {
          alert(t('timelineItemNotFound' as any));
          return;
        }

        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/timeline-items/${timelineItem.id}/retry-artifact`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
          }
        );

        if (!response.ok) {
          const error = await response.json();
          alert(`${t('retryFailed' as any)}: ${error.detail || t('unknownError' as any)}`);
          return;
        }

        const result = await response.json();
        if (!result.success) {
          alert(`${t('retryFailed' as any)}: ${result.error || t('unknownError' as any)}`);
          return;
        }

        await loadTasks();
        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
      } catch (error: any) {
        alert(`${t('retryFailed' as any)}: ${error.message || t('unknownError' as any)}`);
      }
    },
    [apiUrl, loadTasks, t, workspaceId]
  );

  const handleUpdateAutoExec = useCallback(
    async (task: PendingTask, value: string, selectElement: HTMLSelectElement) => {
      if (!task.pack_id) {
        return;
      }

      try {
        if (value === 'none') {
          const response = await fetch(
            `${apiUrl}/api/v1/workspaces/${workspaceId}/playbook-auto-exec-config`,
            {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                playbook_code: task.pack_id,
                auto_execute: false,
              }),
            }
          );

          if (response.ok) {
            window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
          }
          return;
        }

        const threshold = Number.parseFloat(value);
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/playbook-auto-exec-config`,
          {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              playbook_code: task.pack_id,
              confidence_threshold: threshold,
              auto_execute: true,
            }),
          }
        );

        if (!response.ok) {
          console.error('Failed to update auto-exec config:', await response.text());
          return;
        }

        selectElement.style.backgroundColor = '#d1fae5';
        window.setTimeout(() => {
          selectElement.style.backgroundColor = '';
        }, 1000);
        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
      } catch (error) {
        console.error('Failed to update auto-exec config:', error);
      }
    },
    [apiUrl, workspaceId]
  );

  const handleExecuteTask = useCallback(
    async (task: PendingTask) => {
      setExecutingTaskIds((previous) => new Set([...Array.from(previous), task.id]));
      setTaskStatusMessages((previous) => ({
        ...previous,
        [task.id]: t('taskStatusRunning' as any),
      }));

      try {
        const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/chat`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            action: 'execute_pack',
            action_params: {
              pack_id: task.pack_id,
              task_id: task.id,
            },
            message: '',
            files: [],
            mode: 'auto',
          }),
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          setTaskStatusMessages((previous) => ({
            ...previous,
            [task.id]: `${t('executionFailed' as any)}: ${
              errorData.detail || `HTTP ${response.status}`
            }`,
          }));
          await loadTasks();
          window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
          window.setTimeout(() => {
            clearTaskExecutionState(task.id);
          }, 3000);
          return;
        }

        setTaskStatusMessages((previous) => ({
          ...previous,
          [task.id]: t('executionSuccessUpdating' as any),
        }));

        await loadTasks();

        window.setTimeout(async () => {
          try {
            const checkResponse = await fetch(
              `${apiUrl}/api/v1/workspaces/${workspaceId}/tasks?limit=20&include_completed=true`
            );
            if (!checkResponse.ok) {
              return;
            }

            const checkData = await checkResponse.json();
            const executedTask = checkData.tasks?.find((candidate: PendingTask) => candidate.id === task.id);
            if (
              !executedTask ||
              !['PENDING', 'pending'].includes(String(executedTask.status))
            ) {
              return;
            }

            const taskTitle = task.title || task.summary || task.pack_id || 'Task';
            const taskDescription = task.summary || '';
            const descriptionSource = `${taskDescription} ${taskTitle}`.toLowerCase();
            let dataType: 'file' | 'text' | 'both' = 'both';

            if (
              descriptionSource.includes('upload') ||
              descriptionSource.includes('file') ||
              descriptionSource.includes('document') ||
              descriptionSource.includes('上傳') ||
              descriptionSource.includes('檔案') ||
              descriptionSource.includes('文件')
            ) {
              dataType = 'file';
            } else if (
              descriptionSource.includes('text') ||
              descriptionSource.includes('input') ||
              descriptionSource.includes('輸入') ||
              descriptionSource.includes('文字')
            ) {
              dataType = 'text';
            }

            window.dispatchEvent(
              new CustomEvent('continue-conversation', {
                detail: {
                  type: 'continue-conversation',
                  taskId: task.id,
                  context: {
                    topic: taskTitle,
                    requiresData: {
                      type: dataType,
                      description:
                        taskDescription ||
                        `The task "${taskTitle}" requires additional data to continue.`,
                      prompt: `To continue "${taskTitle}", please provide the missing input:`,
                    },
                  },
                },
              })
            );
          } catch (error) {
            console.error(
              '[PendingTasksPanel] Failed to check task status for data supplementation:',
              error
            );
          }
        }, 1000);

        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
        window.setTimeout(() => {
          clearTaskExecutionState(task.id);
        }, 2000);
      } catch (error: any) {
        setTaskStatusMessages((previous) => ({
          ...previous,
          [task.id]: `${t('executionFailed' as any)}: ${
            error.message || t('unknownError' as any)
          }`,
        }));
        await loadTasks();
        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
        window.setTimeout(() => {
          clearTaskExecutionState(task.id);
        }, 3000);
      }
    },
    [apiUrl, clearTaskExecutionState, loadTasks, t, workspaceId]
  );

  const handleOpenRejectDialog = useCallback((taskId: string) => {
    setShowRejectDialog(taskId);
    setRejectReason('');
    setRejectComment('');
  }, []);

  const handleCloseRejectDialog = useCallback(() => {
    setShowRejectDialog(null);
    setRejectReason('');
    setRejectComment('');
  }, []);

  const handleConfirmReject = useCallback(async () => {
    if (!showRejectDialog) {
      return;
    }

    const taskId = showRejectDialog;

    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/tasks/${taskId}/reject`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            reason_code: rejectReason || null,
            comment: rejectComment || null,
          }),
        }
      );

      if (!response.ok) {
        const error = await response.json();
        alert(`${t('rejectTask' as any)} failed: ${error.detail || t('unknownError' as any)}`);
        return;
      }

      setRejectedTasks((previous) => ({
        ...previous,
        [taskId]: {
          timestamp: Date.now(),
          canRestore: true,
        },
      }));

      const restoreInterval = window.setInterval(() => {
        setRejectedTasks((previous) => {
          const taskState = previous[taskId];
          if (!taskState) {
            window.clearInterval(restoreInterval);
            return previous;
          }

          const elapsed = Math.floor((Date.now() - taskState.timestamp) / 1000);
          if (elapsed >= 10) {
            window.clearInterval(restoreInterval);
            return {
              ...previous,
              [taskId]: {
                ...taskState,
                canRestore: false,
              },
            };
          }

          return previous;
        });
      }, 1000);

      window.setTimeout(() => {
        window.clearInterval(restoreInterval);
      }, 10000);

      handleCloseRejectDialog();
      await loadTasks();
      window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
    } catch (error: any) {
      alert(`${t('rejectTask' as any)} failed: ${error.message || t('unknownError' as any)}`);
    }
  }, [
    apiUrl,
    handleCloseRejectDialog,
    loadTasks,
    rejectComment,
    rejectReason,
    showRejectDialog,
    t,
    workspaceId,
  ]);

  const handleRestoreTask = useCallback(
    async (taskId: string) => {
      try {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/tasks/${taskId}/restore`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({}),
          }
        );

        if (!response.ok) {
          const error = await response.json();
          alert(`${t('restoreTask' as any)} failed: ${error.detail || t('unknownError' as any)}`);
          return;
        }

        setRejectedTasks((previous) => {
          const updated = { ...previous };
          delete updated[taskId];
          return updated;
        });
        await loadTasks();
        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
      } catch (error: any) {
        alert(`${t('restoreTask' as any)} failed: ${error.message || t('unknownError' as any)}`);
      }
    },
    [apiUrl, loadTasks, t, workspaceId]
  );

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: laserScanStyle }} />
      <div className="rounded-lg border border-gray-200 bg-white p-2 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        {loading ? (
          <div className="mb-1 flex justify-end">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          </div>
        ) : null}

        <div className="space-y-1.5">
          <BackgroundTaskSuggestions
            backgroundTasks={pendingBackgroundTasks}
            backgroundRoutines={backgroundRoutines}
            onEnableRoutine={handleEnableBackgroundRoutine}
          />

          {processedTasks.length === 0 && visibleBackgroundTasks.length === 0 ? (
            <div className="py-2 text-xs italic text-gray-500 dark:text-gray-400">
              {t('noPendingTasks' as any)}
            </div>
          ) : null}

          {processedTasks.length > 0 ? (
            <PendingTaskList
              tasks={processedTasks}
              workspaceId={workspaceId}
              apiUrl={apiUrl}
              workspace={workspace}
              executingTaskIds={executingTaskIds}
              taskStatusMessages={taskStatusMessages}
              onExecuteTask={handleExecuteTask}
              onRejectTask={handleOpenRejectDialog}
              onRetryArtifact={handleRetryArtifact}
              onUpdateAutoExec={handleUpdateAutoExec}
            />
          ) : null}
        </div>
      </div>

      <RejectTaskDialog
        taskId={showRejectDialog}
        rejectReason={rejectReason}
        rejectComment={rejectComment}
        onRejectReasonChange={setRejectReason}
        onRejectCommentChange={setRejectComment}
        onCancel={handleCloseRejectDialog}
        onConfirm={handleConfirmReject}
      />

      <RestoreTaskNotifications
        rejectedTasks={rejectedTasks}
        onRestoreTask={handleRestoreTask}
      />
    </>
  );
}
