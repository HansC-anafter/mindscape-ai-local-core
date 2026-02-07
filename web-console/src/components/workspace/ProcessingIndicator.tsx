'use client';

import React, { useState, useEffect } from 'react';
import { t } from '@/lib/i18n';

interface ProcessingIndicatorProps {
  visible: boolean;
  isStreaming?: boolean;
  firstChunkReceived?: boolean;
  pipelineStage?: string | null;
}

/**
 * ProcessingIndicator Component
 * Displays a processing indicator when messages are being loaded or streamed.
 *
 * @param visible Whether the indicator should be visible.
 * @param isStreaming Whether the message is currently streaming.
 * @param firstChunkReceived Whether the first chunk of the streaming message has been received.
 * @param pipelineStage Optional pipeline stage information string.
 */
export function ProcessingIndicator({
  visible,
  isStreaming,
  firstChunkReceived,
  pipelineStage,
}: ProcessingIndicatorProps) {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    let interval: NodeJS.Timeout | null = null;
    if (visible) {
      setSeconds(0);
      interval = setInterval(() => {
        setSeconds((prev) => prev + 0.1);
      }, 100);
    } else {
      setSeconds(0);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [visible]);

  if (!visible) {
    return null;
  }

  return (
    <div className="flex items-center justify-center py-4">
      <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
        {visible && !firstChunkReceived ? (
          <>
            <div className="w-4 h-4 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
            <span>
              {t('thinking' as any)} ({seconds.toFixed(1)}s)
            </span>
          </>
        ) : isStreaming ? (
          <>
            <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <span>
              {t('processingMessage' as any)} ({seconds.toFixed(1)}s)
            </span>
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
            <span className="text-xs">{pipelineStage}</span>
          </div>
        )}
      </div>
    </div>
  );
}

