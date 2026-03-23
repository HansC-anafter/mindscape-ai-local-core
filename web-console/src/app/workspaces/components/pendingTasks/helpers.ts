import { getPlaybookMetadata } from '@/lib/i18n/locales/playbooks';
import { parseServerTimestamp, toTimestampMs } from '@/lib/time';

import type { BackgroundRoutine, PendingTask } from './types';

const BACKGROUND_PLAYBOOK_CODES = new Set(['habit_learning']);
const SYSTEM_PLAYBOOK_CODES = new Set(['execution_status_query']);
const RECENT_COMPLETED_WINDOW_MS = 5 * 60 * 1000;

export const laserScanStyle = `
  @keyframes laser-scan {
    0% {
      transform: translateX(-100%);
    }
    100% {
      transform: translateX(300%);
    }
  }

  .laser-scan-text {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: rgb(37, 99, 235);
    overflow: hidden;
    line-height: 1;
  }

  .laser-scan-text::after {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    width: 30%;
    height: 100%;
    background: linear-gradient(
      90deg,
      transparent,
      rgba(255, 255, 255, 0.8),
      rgba(255, 255, 255, 1),
      rgba(255, 255, 255, 0.8),
      transparent
    );
    animation: laser-scan 2.5s linear infinite;
    pointer-events: none;
    mix-blend-mode: overlay;
  }
`;

export function isBackgroundTask(task: PendingTask): boolean {
  const playbookCode = (task.pack_id || task.playbook_id || '').toLowerCase();
  return (
    BACKGROUND_PLAYBOOK_CODES.has(playbookCode) ||
    task.result?.llm_analysis?.is_background === true ||
    task.data?.execution_context?.run_mode === 'background'
  );
}

export function isSystemTask(task: PendingTask): boolean {
  const playbookCode = task.pack_id || task.playbook_id || '';
  return SYSTEM_PLAYBOOK_CODES.has(playbookCode);
}

export function isPendingTask(task: PendingTask): boolean {
  return task.status?.toUpperCase() === 'PENDING';
}

export function getStatusColor(status?: string): string {
  switch (status?.toUpperCase()) {
    case 'RUNNING':
      return 'bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300 border-blue-300 dark:border-blue-700';
    case 'PENDING':
      return 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300 border-yellow-300 dark:border-yellow-700';
    case 'SUCCEEDED':
      return 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 border-green-300 dark:border-green-700';
    case 'FAILED':
      return 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300 border-red-300 dark:border-red-700';
    default:
      return 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-300 border-gray-300 dark:border-gray-600';
  }
}

export function formatTaskTime(timestamp: string): string {
  const date = parseServerTimestamp(timestamp);
  if (!date) {
    return '';
  }
  return date.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  });
}

export function getTaskDisplayTitle(task: PendingTask): string {
  if (task.title) {
    return task.title;
  }
  if (task.summary) {
    return task.summary;
  }

  const playbookCode = task.pack_id || task.playbook_id;
  if (playbookCode) {
    return (
      getPlaybookMetadata(playbookCode, 'name', 'en') ||
      getPlaybookMetadata(playbookCode, 'name', 'zh-TW') ||
      playbookCode
    );
  }

  return task.task_type || 'Task';
}

export function shouldShowTaskForDecision(task: PendingTask): boolean {
  if (isBackgroundTask(task) || isSystemTask(task)) {
    return false;
  }

  if (task.task_type === 'auto_intent_extraction') {
    return false;
  }

  if (
    (task.pack_id === 'intent_extraction' || task.playbook_id === 'intent_extraction') &&
    task.status?.toUpperCase() === 'SUCCEEDED' &&
    (task.params?.auto_executed || task.result?.auto_executed)
  ) {
    return false;
  }

  return true;
}

export function isRecentlyCompletedTask(task: PendingTask, nowMs = Date.now()): boolean {
  if (task.status?.toUpperCase() !== 'SUCCEEDED') {
    return false;
  }

  const completedAt = task.completed_at || task.updated_at || task.created_at;
  const completedTime = completedAt ? toTimestampMs(completedAt) : null;
  if (completedTime === null) {
    return false;
  }

  return completedTime > nowMs - RECENT_COMPLETED_WINDOW_MS;
}

export function splitPendingTaskCollections(allTasks: PendingTask[], nowMs = Date.now()) {
  const backgroundTasks = allTasks.filter(isBackgroundTask);
  const tasksNeedingDecision = allTasks.filter(shouldShowTaskForDecision);
  const activeTasks = tasksNeedingDecision.filter(isPendingTask);
  const recentCompletedTasks = tasksNeedingDecision.filter((task) =>
    isRecentlyCompletedTask(task, nowMs)
  );

  return {
    backgroundTasks,
    tasksNeedingDecision,
    activeTasks,
    recentCompletedTasks,
    displayTasks: [...activeTasks, ...recentCompletedTasks],
  };
}

export function getVisibleBackgroundTasks(
  backgroundTasks: PendingTask[],
  backgroundRoutines: BackgroundRoutine[]
): PendingTask[] {
  return backgroundTasks.filter((task) => {
    const playbookCode = (task.pack_id || task.playbook_id || '').toLowerCase().trim();
    if (!playbookCode) {
      return false;
    }

    const existingRoutine = backgroundRoutines.find((routine) => {
      const routineCode = (routine.playbook_code || '').toLowerCase().trim();
      return routineCode === playbookCode;
    });

    return !(existingRoutine && existingRoutine.enabled);
  });
}

export function groupTasksByPackId(tasks: PendingTask[]): Record<string, PendingTask[]> {
  return tasks.reduce<Record<string, PendingTask[]>>((accumulator, task) => {
    const packId = task.pack_id || 'unknown';
    if (!accumulator[packId]) {
      accumulator[packId] = [];
    }
    accumulator[packId].push(task);
    return accumulator;
  }, {});
}
