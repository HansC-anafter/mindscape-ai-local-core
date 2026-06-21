import React from 'react';

import { parseServerTimestamp } from '@/lib/time';

import type { ToolCall } from '../types/execution';
import type { Translator } from './stepDetailPanelTypes';

export function ToolCallsSection({
  currentStepToolCalls,
  t,
}: {
  currentStepToolCalls: ToolCall[];
  t: Translator;
}) {
  if (currentStepToolCalls.length === 0) {
    return null;
  }

  return (
    <div className="mb-4">
      <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
        {t('toolCalls' as any)}
      </h4>
      <div className="space-y-2">
        {currentStepToolCalls.map((toolCall) => (
          <div
            key={toolCall.id}
            className="p-3 bg-surface-accent dark:bg-gray-700 rounded border border-default dark:border-gray-600"
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {toolCall.tool_name}
              </span>
              <span
                className={`text-xs px-2 py-0.5 rounded ${toolCall.status === 'completed'
                    ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                    : toolCall.status === 'failed'
                      ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
                      : 'bg-accent-10 dark:bg-blue-900/30 text-accent dark:text-blue-300'
                  }`}
              >
                {toolCall.status}
              </span>
            </div>
            {toolCall.started_at && (
              <div className="text-xs text-gray-500 dark:text-gray-300">
                {parseServerTimestamp(toolCall.started_at)?.toLocaleTimeString(undefined, {
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit',
                })}
                {toolCall.completed_at &&
                  ` - ${parseServerTimestamp(toolCall.completed_at)?.toLocaleTimeString(undefined, {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                  })}`}
              </div>
            )}
            {toolCall.error && (
              <div className="text-xs text-red-600 dark:text-red-400 mt-1">
                {toolCall.error}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
