'use client';

import React from 'react';
import { t } from '@/lib/i18n';

type ExecutionMode = 'qa' | 'execution' | 'hybrid';

interface ExecutionModeNoticeProps {
  executionMode: ExecutionMode;
  expectedArtifacts?: string[];
}

/**
 * ExecutionModeNotice Component
 * Displays a notice about the current execution mode.
 *
 * @param executionMode The current execution mode.
 * @param expectedArtifacts Optional array of expected artifact types.
 */
export function ExecutionModeNotice({
  executionMode,
  expectedArtifacts,
}: ExecutionModeNoticeProps) {
  if (executionMode === 'qa') {
    return null;
  }

  return (
    <div
      className={`
        mx-4 mb-4 p-3 rounded-lg border text-sm
        ${executionMode === 'execution'
          ? 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-200'
          : 'bg-violet-50 dark:bg-violet-900/20 border-violet-200 dark:border-violet-800 text-violet-800 dark:text-violet-200'
        }
      `}
    >
      <div className="flex items-center gap-2">
        <div>
          <span className="font-medium">
            {executionMode === 'execution' ? 'Execution mode enabled' : 'Hybrid mode enabled'}
          </span>
          <span className="mx-2">·</span>
          <span className="opacity-80">
            {executionMode === 'execution'
              ? 'AI will prioritize executing actions and producing artifacts, rather than just conversing'
              : 'AI will balance between conversation and execution'
            }
          </span>
          {expectedArtifacts && expectedArtifacts.length > 0 && (
            <>
              <span className="mx-2">·</span>
              <span className="opacity-80">Expected artifacts: {expectedArtifacts.join(', ').toUpperCase()}</span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

