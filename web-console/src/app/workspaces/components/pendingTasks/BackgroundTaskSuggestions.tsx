'use client';

import React, { useMemo } from 'react';

import { useT } from '@/lib/i18n';

import { getVisibleBackgroundTasks } from './helpers';
import type { BackgroundRoutine, PendingTask } from './types';

interface BackgroundTaskSuggestionsProps {
  backgroundTasks: PendingTask[];
  backgroundRoutines: BackgroundRoutine[];
  onEnableRoutine: (playbookCode: string) => Promise<void>;
}

export default function BackgroundTaskSuggestions({
  backgroundTasks,
  backgroundRoutines,
  onEnableRoutine,
}: BackgroundTaskSuggestionsProps) {
  const t = useT();
  const visibleBackgroundTasks = useMemo(
    () => getVisibleBackgroundTasks(backgroundTasks, backgroundRoutines),
    [backgroundRoutines, backgroundTasks]
  );

  if (visibleBackgroundTasks.length === 0) {
    return null;
  }

  return (
    <>
      {visibleBackgroundTasks.map((task) => {
        const playbookCode = task.pack_id || task.playbook_id || '';

        return (
          <div
            key={`bg-${task.id}`}
            className="rounded border border-gray-200 bg-gray-50 p-2 dark:border-gray-700 dark:bg-gray-800"
          >
            <div className="mb-1.5 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="rounded border border-gray-300 bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-300">
                  {t('backgroundExecution' as any)}
                </span>
                <span className="text-xs font-medium text-gray-900 dark:text-gray-100">
                  {playbookCode}
                </span>
              </div>
            </div>
            <div className="mb-2 text-xs text-gray-600 dark:text-gray-400">
              {t('backgroundExecutionDescription' as any)}
            </div>
            <button
              onClick={() => void onEnableRoutine(playbookCode)}
              className="w-full rounded bg-blue-600 px-2 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-700 dark:bg-blue-700 dark:hover:bg-blue-600"
            >
              {t('enableBackgroundTask' as any)}
            </button>
          </div>
        );
      })}
    </>
  );
}
