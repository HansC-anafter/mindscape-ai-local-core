'use client';

import React from 'react';
import { t } from '@/lib/i18n';

interface ProcessingIndicatorProps {
  visible: boolean;
  isStreaming?: boolean;
  pipelineStage?: string | null;
}

/**
 * ProcessingIndicator Component
 * Displays a processing indicator when messages are being loaded or streamed.
 *
 * @param visible Whether the indicator should be visible.
 * @param isStreaming Whether the message is currently streaming.
 * @param pipelineStage Optional pipeline stage information.
 */
export function ProcessingIndicator({
  visible,
  isStreaming,
  pipelineStage,
}: ProcessingIndicatorProps) {
  if (!visible) {
    return null;
  }

  return (
    <div className="flex items-center justify-center py-4">
      <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
        {isStreaming ? (
          <>
            <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <span>{t('processingMessage')}</span>
          </>
        ) : (
          <>
            <div
              className="w-4 h-4 border-2 border-gray-400 dark:border-gray-200 border-t-transparent rounded-full"
              style={{ animation: 'spin 1s linear infinite' }}
            />
            <span>Loading older messages...</span>
          </>
        )}
        {pipelineStage && (
          <div className="ml-2 flex items-center gap-1">
            <span className="w-1.5 h-1.5 bg-orange-500 rounded-full animate-pulse" />
            <span className="text-xs">{t('executing')}</span>
          </div>
        )}
      </div>
    </div>
  );
}

