'use client';

import { useCallback, type Dispatch, type SetStateAction } from 'react';

import type { PendingTask, RejectedTaskState } from './types';

type PendingTasksTranslator = (key: any) => string;

interface UsePendingTaskActionsParams {
  apiUrl: string;
  workspaceId: string;
  t: PendingTasksTranslator;
  loadTasks: () => Promise<void>;
  loadBackgroundRoutines: () => Promise<void>;
  showRejectDialog: string | null;
  rejectReason: string;
  rejectComment: string;
  setExecutingTaskIds: Dispatch<SetStateAction<Set<string>>>;
  setTaskStatusMessages: Dispatch<SetStateAction<Record<string, string>>>;
  setRejectedTasks: Dispatch<SetStateAction<Record<string, RejectedTaskState>>>;
  setShowRejectDialog: Dispatch<SetStateAction<string | null>>;
  setRejectReason: Dispatch<SetStateAction<string>>;
  setRejectComment: Dispatch<SetStateAction<string>>;
}

type SupplementationDataType = 'file' | 'text' | 'both';

function getSupplementationDataType(descriptionSource: string): SupplementationDataType {
  if (
    descriptionSource.includes('upload') ||
    descriptionSource.includes('file') ||
    descriptionSource.includes('document') ||
    descriptionSource.includes('\u4e0a\u50b3') ||
    descriptionSource.includes('\u6a94\u6848') ||
    descriptionSource.includes('\u6587\u4ef6')
  ) {
    return 'file';
  }

  if (
    descriptionSource.includes('text') ||
    descriptionSource.includes('input') ||
    descriptionSource.includes('\u8f38\u5165') ||
    descriptionSource.includes('\u6587\u5b57')
  ) {
    return 'text';
  }

  return 'both';
}

export function usePendingTaskActions({
  apiUrl,
  workspaceId,
  t,
  loadTasks,
  loadBackgroundRoutines,
  showRejectDialog,
  rejectReason,
  rejectComment,
  setExecutingTaskIds,
  setTaskStatusMessages,
  setRejectedTasks,
  setShowRejectDialog,
  setRejectReason,
  setRejectComment,
}: UsePendingTaskActionsParams) {
  const clearTaskExecutionState = useCallback(
    (taskId: string) => {
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
    },
    [setExecutingTaskIds, setTaskStatusMessages]
  );

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
            const dataType = getSupplementationDataType(descriptionSource);

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
    [
      apiUrl,
      clearTaskExecutionState,
      loadTasks,
      setExecutingTaskIds,
      setTaskStatusMessages,
      t,
      workspaceId,
    ]
  );

  const handleOpenRejectDialog = useCallback(
    (taskId: string) => {
      setShowRejectDialog(taskId);
      setRejectReason('');
      setRejectComment('');
    },
    [setRejectComment, setRejectReason, setShowRejectDialog]
  );

  const handleCloseRejectDialog = useCallback(() => {
    setShowRejectDialog(null);
    setRejectReason('');
    setRejectComment('');
  }, [setRejectComment, setRejectReason, setShowRejectDialog]);

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
    setRejectedTasks,
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
    [apiUrl, loadTasks, setRejectedTasks, t, workspaceId]
  );

  return {
    handleEnableBackgroundRoutine,
    handleRetryArtifact,
    handleUpdateAutoExec,
    handleExecuteTask,
    handleOpenRejectDialog,
    handleCloseRejectDialog,
    handleConfirmReject,
    handleRestoreTask,
  };
}
