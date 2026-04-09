'use client';

import React, { useState, useEffect } from 'react';
import type { PipelineStage } from '@/hooks/useExecutionState';
import { t } from '@/lib/i18n';

interface ProcessingIndicatorProps {
  visible: boolean;
  isStreaming?: boolean;
  firstChunkReceived?: boolean;
  pipelineStage?: PipelineStage | null;
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

  const pipelineTone =
    pipelineStage?.stage === 'compile_failed' || pipelineStage?.stage === 'execution_error'
      ? 'error'
      : pipelineStage?.stage === 'compile_succeeded'
        ? 'success'
        : 'active';

  const showPipelineStage = Boolean(pipelineStage);
  const pipelineStreaming = pipelineStage?.streaming ?? false;

  const renderIndicator = () => {
    if (showPipelineStage) {
      if (pipelineTone === 'error') {
        return (
          <>
            <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse" />
            <span>
              {pipelineStage?.message}
              {pipelineStreaming ? ` (${seconds.toFixed(1)}s)` : ''}
            </span>
          </>
        );
      }

      if (pipelineTone === 'success') {
        return (
          <>
            <span className="w-2.5 h-2.5 rounded-full bg-green-500" />
            <span>{pipelineStage?.message}</span>
          </>
        );
      }

      return (
        <>
          <div className="w-4 h-4 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
          <span>
            {pipelineStage?.message}
            {pipelineStreaming ? ` (${seconds.toFixed(1)}s)` : ''}
          </span>
        </>
      );
    }

    if (visible && !firstChunkReceived) {
      return (
        <>
          <div className="w-4 h-4 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
          <span>
            {t('thinking' as any)} ({seconds.toFixed(1)}s)
          </span>
        </>
      );
    }

    if (isStreaming) {
      return (
        <>
          <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <span>
            {t('processingMessage' as any)} ({seconds.toFixed(1)}s)
          </span>
        </>
      );
    }

    return (
      <>
        <div
          className="w-4 h-4 border-2 border-gray-400 dark:border-gray-200 border-t-transparent rounded-full"
          style={{ animation: 'spin 1s linear infinite' }}
        />
        <span>Loading older messages...</span>
      </>
    );
  };

  return (
    <div className="flex items-center justify-center py-4">
      <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
        {renderIndicator()}
      </div>
    </div>
  );
}
