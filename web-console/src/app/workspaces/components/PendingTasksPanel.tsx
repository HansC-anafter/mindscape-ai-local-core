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
import { usePendingTaskActions } from './pendingTasks/usePendingTaskActions';

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
    return splitPendingTaskCollections(allTasks as PendingTask[]).displayTasks;
  }, [allTasks]);

  const pendingBackgroundTasks = useMemo(() => {
    if (contextData) {
      return splitPendingTaskCollections(allTasks as PendingTask[]).backgroundTasks.filter(isPendingTask);
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

  const {
    handleEnableBackgroundRoutine,
    handleRetryArtifact,
    handleUpdateAutoExec,
    handleExecuteTask,
    handleOpenRejectDialog,
    handleCloseRejectDialog,
    handleConfirmReject,
    handleRestoreTask,
  } = usePendingTaskActions({
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
  });

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
