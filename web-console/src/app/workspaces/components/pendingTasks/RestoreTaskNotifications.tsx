'use client';

import React from 'react';

import { useT } from '@/lib/i18n';

import type { RejectedTaskState } from './types';

interface RestoreTaskNotificationsProps {
  rejectedTasks: Record<string, RejectedTaskState>;
  onRestoreTask: (taskId: string) => Promise<void>;
}

export default function RestoreTaskNotifications({
  rejectedTasks,
  onRestoreTask,
}: RestoreTaskNotificationsProps) {
  const t = useT();

  return (
    <>
      {Object.entries(rejectedTasks).map(([taskId, taskInfo]) => {
        if (!taskInfo.canRestore) {
          return null;
        }

        const elapsed = Math.floor((Date.now() - taskInfo.timestamp) / 1000);
        const remaining = 10 - elapsed;
        if (remaining <= 0) {
          return null;
        }

        return (
          <div
            key={taskId}
            className="fixed bottom-4 right-4 z-50 flex items-center gap-3 rounded-lg bg-blue-500 px-4 py-3 text-white shadow-lg dark:bg-blue-600"
          >
            <span>{t('taskRejected' as any)}</span>
            <span className="text-sm opacity-90">
              {t('restoreAvailable', { seconds: String(remaining) })}
            </span>
            <button
              onClick={() => void onRestoreTask(taskId)}
              className="rounded bg-white px-3 py-1 text-sm font-medium text-blue-600 transition-colors hover:bg-blue-50 dark:bg-gray-800 dark:text-blue-400 dark:hover:bg-gray-700"
            >
              {t('restoreTask' as any)}
            </button>
          </div>
        );
      })}
    </>
  );
}
