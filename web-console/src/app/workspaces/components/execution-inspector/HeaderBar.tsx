'use client';

import React from 'react';
import ExecutionHeader from '../ExecutionHeader';
import type { ExecutionSession, ExecutionStats } from './types/execution';

export interface HeaderBarProps {
  execution: ExecutionSession;
  playbookTitle?: string;
  workspaceName?: string;
  projectName?: string;
  executionRunNumber: number;
  stats?: ExecutionStats;
  totalSteps: number;
  sandboxId: string | null;
  isStopping: boolean;
  isReloading: boolean;
  onStop?: () => void;
  onReloadPlaybook?: () => void;
  onRestartExecution?: () => void;
  onViewSandbox: () => void;
  t: (key: string, params?: any) => string;
}

export default function HeaderBar({
  execution,
  playbookTitle,
  workspaceName,
  projectName,
  executionRunNumber,
  stats,
  totalSteps,
  sandboxId,
  isStopping,
  isReloading,
  onStop,
  onReloadPlaybook,
  onRestartExecution,
  onViewSandbox,
  t,
}: HeaderBarProps) {
  return (
    <div className="bg-surface-secondary dark:bg-gray-900 border-b border-default dark:border-gray-800">
      <div className="flex items-center justify-between px-6 py-2">
        <div className="flex-1">
          <ExecutionHeader
            execution={{
              ...execution,
              total_steps: totalSteps,
            }}
            playbookTitle={playbookTitle}
            workspaceName={workspaceName}
            projectName={projectName}
            executionRunNumber={executionRunNumber}
            stats={stats}
            onRetry={execution.status === 'failed' ? () => {
              // TODO: Implement retry functionality
            } : undefined}
            isStopping={isStopping}
            onStop={execution.status === 'running' ? onStop : undefined}
            onReloadPlaybook={onReloadPlaybook}
            onRestartExecution={onRestartExecution}
          />
        </div>
        {sandboxId && (
          <button
            onClick={onViewSandbox}
            className="ml-4 px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 whitespace-nowrap"
            title={t('viewSandbox') || 'View Sandbox'}
          >
            {t('viewSandbox') || 'View Sandbox'}
          </button>
        )}
      </div>
    </div>
  );
}
