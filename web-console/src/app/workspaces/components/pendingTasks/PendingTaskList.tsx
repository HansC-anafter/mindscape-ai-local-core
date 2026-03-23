'use client';

import React from 'react';

import { useT } from '@/lib/i18n';

import {
  formatTaskTime,
  getStatusColor,
  getTaskDisplayTitle,
  groupTasksByPackId,
  isBackgroundTask,
  isSystemTask,
} from './helpers';
import PlaybookIntentSubtitle from './PlaybookIntentSubtitle';
import type { PendingTask, PendingTasksWorkspace } from './types';

interface PendingTaskListProps {
  tasks: PendingTask[];
  workspaceId: string;
  apiUrl: string;
  workspace?: PendingTasksWorkspace;
  executingTaskIds: Set<string>;
  taskStatusMessages: Record<string, string>;
  onExecuteTask: (task: PendingTask) => Promise<void>;
  onRejectTask: (taskId: string) => void;
  onRetryArtifact: (task: PendingTask) => Promise<void>;
  onUpdateAutoExec: (
    task: PendingTask,
    value: string,
    selectElement: HTMLSelectElement
  ) => Promise<void>;
}

interface PendingTaskCardProps {
  task: PendingTask;
  workspaceId: string;
  apiUrl: string;
  workspace?: PendingTasksWorkspace;
  executingTaskIds: Set<string>;
  taskStatusMessages: Record<string, string>;
  onExecuteTask: (task: PendingTask) => Promise<void>;
  onRejectTask: (taskId: string) => void;
  onRetryArtifact: (task: PendingTask) => Promise<void>;
  onUpdateAutoExec: (
    task: PendingTask,
    value: string,
    selectElement: HTMLSelectElement
  ) => Promise<void>;
  t: ReturnType<typeof useT>;
}

function PendingTaskCard({
  task,
  workspaceId,
  apiUrl,
  workspace,
  executingTaskIds,
  taskStatusMessages,
  onExecuteTask,
  onRejectTask,
  onRetryArtifact,
  onUpdateAutoExec,
  t,
}: PendingTaskCardProps) {
  if (isBackgroundTask(task) || isSystemTask(task) || task.status?.toUpperCase() === 'RUNNING') {
    return null;
  }

  const isSucceeded = task.status?.toUpperCase() === 'SUCCEEDED';
  const confidence = task.result?.llm_analysis?.confidence;
  const autoExecutionConfig =
    task.pack_id && workspace?.playbook_auto_execution_config?.[task.pack_id];

  return (
    <div
      className={`rounded border p-1.5 transition-colors ${
        isSucceeded
          ? 'border-green-200 bg-green-50 hover:bg-green-100 dark:border-green-800 dark:bg-green-900/20 dark:hover:bg-green-900/30'
          : 'border-gray-200 bg-gray-50 hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700'
      }`}
    >
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center justify-between gap-1.5">
          <div className="flex min-w-0 flex-1 items-center gap-1.5">
            <div
              className="truncate text-xs font-medium text-gray-900 dark:text-gray-100"
              title={task.title || task.summary || task.pack_id || task.playbook_id || task.task_type}
            >
              {getTaskDisplayTitle(task)}
            </div>
            {task.result?.llm_analysis?.is_background ||
            task.pack_id?.toLowerCase() === 'habit_learning' ? (
              <span
                className="flex-shrink-0 rounded border border-gray-300 bg-gray-100 px-1 py-0.5 text-xs text-gray-600 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-300"
                title={t('backgroundExecutionDescription' as any)}
              >
                {t('backgroundExecution' as any)}
              </span>
            ) : confidence !== undefined ? (
              <span
                className="flex-shrink-0 rounded border border-gray-400 bg-gray-100 px-1 py-0.5 text-xs text-gray-700 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-300"
                title={t('llmConfidenceScore', { confidence: confidence.toFixed(2) })}
              >
                {t('confidence' as any)}
                {confidence.toFixed(2)}
              </span>
            ) : null}
          </div>
          {task.created_at ? (
            <div className="flex-shrink-0 text-xs text-gray-400 dark:text-gray-500">
              {formatTaskTime(task.created_at)}
            </div>
          ) : null}
        </div>

        {task.task_type === 'suggestion' && task.message_id ? (
          <PlaybookIntentSubtitle
            workspaceId={workspaceId}
            apiUrl={apiUrl}
            messageId={task.message_id}
          />
        ) : null}

        {task.result?.llm_analysis?.content_tags &&
        Array.isArray(task.result.llm_analysis.content_tags) &&
        task.result.llm_analysis.content_tags.length > 0 ? (
          <div className="mb-1 flex flex-wrap gap-1">
            {task.result.llm_analysis.content_tags.slice(0, 3).map((tag: string, index: number) => (
              <span
                key={`${task.id}-tag-${index}`}
                className="rounded border border-blue-200 bg-blue-50 px-1 py-0.5 text-xs text-blue-700 dark:border-blue-700 dark:bg-blue-900/30 dark:text-blue-300"
              >
                {tag}
              </span>
            ))}
            {task.result.llm_analysis.content_tags.length > 3 ? (
              <span className="text-xs text-gray-500 dark:text-gray-400">
                +{task.result.llm_analysis.content_tags.length - 3}
              </span>
            ) : null}
          </div>
        ) : null}

        {task.result?.llm_analysis?.reason && task.result.llm_analysis.reason.trim() ? (
          <div className="mb-1 line-clamp-2 text-xs text-gray-600 dark:text-gray-400">
            {task.result.llm_analysis.reason}
          </div>
        ) : null}

        {isSucceeded && task.artifact_creation_failed && task.artifact_warning ? (
          <div className="mt-1 mb-1 rounded border border-yellow-200 bg-yellow-50 p-1.5 text-xs dark:border-yellow-800 dark:bg-yellow-900/20">
            <div className="flex items-start gap-1.5">
              <svg
                className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-yellow-600 dark:text-yellow-400"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                  clipRule="evenodd"
                />
              </svg>
              <div className="min-w-0 flex-1">
                <div className="mb-0.5 font-medium text-yellow-800 dark:text-yellow-300">
                  Storage location missing
                </div>
                <div className="mb-0.5 text-[10px] text-yellow-700 dark:text-yellow-400">
                  {task.artifact_warning.message}
                </div>
                {task.artifact_warning.action_required ? (
                  <div className="mb-1 text-[10px] text-yellow-600 dark:text-yellow-500">
                    {task.artifact_warning.action_required}
                  </div>
                ) : null}
                <button
                  onClick={() => void onRetryArtifact(task)}
                  className="flex w-full items-center justify-center gap-1 rounded border border-yellow-300 px-1.5 py-0.5 text-[10px] font-medium text-yellow-700 transition-all hover:bg-yellow-100 hover:text-yellow-800 dark:border-yellow-700 dark:text-yellow-400 dark:hover:bg-yellow-900/30 dark:hover:text-yellow-300"
                >
                  <span>{t('retry' as any)}</span>
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {task.pack_id && !isSucceeded ? (
          <div className="flex flex-col gap-1">
            {taskStatusMessages[task.id] ? (
              <div className="px-1 text-[10px] text-blue-600 dark:text-blue-400">
                {taskStatusMessages[task.id]}
              </div>
            ) : null}
            <div className="flex items-center gap-1">
              <span
                className={`flex-shrink-0 rounded border px-1 py-0.5 text-xs ${getStatusColor(
                  task.status
                )}`}
              >
                {t('taskStatusPending' as any)}
              </span>
              <button
                onClick={() => void onExecuteTask(task)}
                disabled={executingTaskIds.has(task.id)}
                className={`relative flex flex-1 items-center justify-center gap-1 rounded border px-2 py-1 text-xs font-medium shadow-sm transition-all hover:shadow-md ${
                  executingTaskIds.has(task.id)
                    ? 'cursor-not-allowed border-blue-500 bg-blue-400 text-white opacity-75 dark:border-blue-700 dark:bg-blue-600'
                    : 'border-blue-300 text-blue-600 hover:bg-blue-50 hover:text-blue-700 dark:border-blue-700 dark:text-blue-400 dark:hover:bg-blue-900/30 dark:hover:text-blue-300'
                }`}
              >
                {executingTaskIds.has(task.id) ? (
                  <>
                    <div className="h-3 w-3 rounded-full border-2 border-white border-t-transparent animate-spin" />
                    <span>{t('executing' as any)}</span>
                  </>
                ) : (
                  <span className="laser-scan-text" data-text={t('execute' as any)}>
                    {t('execute' as any)}
                  </span>
                )}
              </button>

              <button
                onClick={() => onRejectTask(task.id)}
                className="flex flex-shrink-0 items-center justify-center gap-1 rounded border border-red-300 px-2 py-1 text-xs font-medium text-red-600 transition-all hover:bg-red-50 hover:text-red-700 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-900/30 dark:hover:text-red-300"
                title={t('rejectTask' as any)}
              >
                <span>{t('reject' as any)}</span>
              </button>

              {confidence !== undefined && confidence >= 0.7 ? (
                <select
                  onChange={(event) =>
                    void onUpdateAutoExec(task, event.target.value, event.target)
                  }
                  value={
                    autoExecutionConfig?.auto_execute
                      ? String(autoExecutionConfig.confidence_threshold || 0.8)
                      : 'none'
                  }
                  className="flex-shrink-0 rounded border border-gray-300 bg-white px-1.5 py-1 text-[10px] text-gray-600 transition-colors hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
                  title="Auto-execution threshold for the current workspace"
                >
                  <option value="none">auto</option>
                  <option value="0.9">≥0.9</option>
                  <option value="0.8">≥0.8</option>
                  <option value="0.7">≥0.7</option>
                </select>
              ) : (
                <span
                  className="cursor-not-allowed flex-shrink-0 rounded border border-gray-200 bg-gray-50 px-1.5 py-1 text-[10px] text-gray-400 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-500"
                  title="Available when the confidence score reaches 0.70"
                >
                  auto
                </span>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default function PendingTaskList({
  tasks,
  workspaceId,
  apiUrl,
  workspace,
  executingTaskIds,
  taskStatusMessages,
  onExecuteTask,
  onRejectTask,
  onRetryArtifact,
  onUpdateAutoExec,
}: PendingTaskListProps) {
  const t = useT();
  const groupedTasks = groupTasksByPackId(tasks);
  const taskElements: React.ReactNode[] = [];

  Object.entries(groupedTasks).forEach(([packId, packTasks]) => {
    if (packTasks.length > 1) {
      taskElements.push(
        <div key={`group-${packId}`} className="px-1 py-0.5 text-xs font-medium text-gray-500">
          {packId}: {packTasks.length} {t('pendingTasks' as any) || 'tasks'}
        </div>
      );
    }

    packTasks.forEach((task) => {
      taskElements.push(
        <PendingTaskCard
          key={task.id}
          task={task}
          workspaceId={workspaceId}
          apiUrl={apiUrl}
          workspace={workspace}
          executingTaskIds={executingTaskIds}
          taskStatusMessages={taskStatusMessages}
          onExecuteTask={onExecuteTask}
          onRejectTask={onRejectTask}
          onRetryArtifact={onRetryArtifact}
          onUpdateAutoExec={onUpdateAutoExec}
          t={t}
        />
      );
    });
  });

  return <>{taskElements}</>;
}
