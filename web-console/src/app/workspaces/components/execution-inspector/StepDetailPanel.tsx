'use client';

import React from 'react';
import type { ExecutionStep, ToolCall, StepEvent, PlaybookStepDefinition, Artifact } from './types/execution';
import { deriveAllSteps } from './utils/execution-inspector';
import { getStepStatusColor, getEffectiveStepStatus } from './utils/execution-inspector';

export interface StepDetailPanelProps {
  steps: ExecutionStep[];
  playbookStepDefinitions?: PlaybookStepDefinition[];
  totalSteps?: number;
  currentStepIndex: number;
  currentStepToolCalls: ToolCall[];
  stepEvents: StepEvent[];
  executionStatus?: string;
  artifacts?: Artifact[];
  onViewArtifact?: (artifact: Artifact) => void;
  t: (key: string, params?: any) => string;
}

export default function StepDetailPanel({
  steps,
  playbookStepDefinitions,
  totalSteps,
  currentStepIndex,
  currentStepToolCalls,
  stepEvents,
  executionStatus,
  artifacts = [],
  onViewArtifact,
  t,
}: StepDetailPanelProps) {
  const allSteps = deriveAllSteps({
    playbookStepDefinitions,
    totalSteps,
    steps,
  });

  const executedStepsMap = new Map(steps.map(s => [s.step_index, s]));
  const currentStep = executedStepsMap.get(currentStepIndex) || allSteps.find(s => s.step_index === currentStepIndex)?.executed;
  const currentStepInfo = allSteps.find(s => s.step_index === currentStepIndex);

  if (!currentStepInfo) {
    return (
      <div className="h-full overflow-y-auto bg-white dark:bg-gray-800 p-3 min-w-0">
        <div className="text-center py-8 text-gray-500 dark:text-gray-300">
          {t('selectStepToViewDetails') || '請選擇步驟以查看詳情'}
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-white dark:bg-gray-800 p-3 min-w-0">
      <div className="mb-3 pb-3 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-2 mb-1.5">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            {t('stepNumber', { number: currentStepIndex })}: {currentStepInfo.step_name || t('unnamed')}
          </h3>
          {currentStep && (
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${getStepStatusColor(currentStep)}`}
            >
              {getEffectiveStepStatus(currentStep, executionStatus)}
            </span>
          )}
        </div>
        {(currentStep?.description || currentStep?.log_summary || currentStepInfo?.description) && (
          <p className="text-xs text-gray-600 dark:text-gray-300 mb-1.5 whitespace-pre-wrap">
            {currentStep?.description || currentStep?.log_summary || currentStepInfo?.description}
          </p>
        )}
        {currentStep?.agent_type && (
          <div className="text-xs text-gray-500 dark:text-gray-300">
            {t('agent')} <span className="font-medium">{currentStep.agent_type}</span>
          </div>
        )}
        {!currentStep && (
          <p className="text-xs text-gray-500 dark:text-gray-400 italic">
            {t('stepNotExecutedYet') || 'This step has not been executed yet.'}
          </p>
        )}
      </div>

      {/* Event Stream - Only show if there are events */}
      {stepEvents.length > 0 && (
        <div className="mb-3">
          <h4 className="text-xs font-medium text-gray-900 dark:text-gray-100 mb-1.5">
            {t('eventStream')}
          </h4>
          <div className="space-y-1.5">
            {stepEvents.map((event) => (
              <div
                key={event.id}
                className="flex gap-2 p-1.5 bg-gray-50 dark:bg-gray-700 rounded border border-gray-200 dark:border-gray-600"
              >
                <div className="flex-shrink-0 text-[10px] text-gray-500 dark:text-gray-300 w-14">
                  {event.timestamp.toLocaleTimeString(undefined, {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                  })}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-[10px] text-gray-600 dark:text-gray-300">
                    {event.type === 'tool' && event.tool && (
                      <span className="font-medium">
                        {t('tool')} {event.tool}
                      </span>
                    )}
                    {event.type === 'collaboration' && event.agent && (
                      <span className="font-medium">
                        {t('collaboration')} {event.agent}
                      </span>
                    )}
                    {event.type === 'step' && event.agent && (
                      <span className="font-medium">
                        {t('agent')} {event.agent}
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-gray-900 dark:text-gray-100 mt-0.5">
                    {event.content}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tool Calls */}
      {currentStepToolCalls.length > 0 && (
        <div className="mb-4">
          <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
            {t('toolCalls')}
          </h4>
          <div className="space-y-2">
            {currentStepToolCalls.map((toolCall) => (
              <div
                key={toolCall.id}
                className="p-3 bg-gray-50 dark:bg-gray-700 rounded border border-gray-200 dark:border-gray-600"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {toolCall.tool_name}
                  </span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded ${
                      toolCall.status === 'completed'
                        ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                        : toolCall.status === 'failed'
                        ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
                        : 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                    }`}
                  >
                    {toolCall.status}
                  </span>
                </div>
                {toolCall.started_at && (
                  <div className="text-xs text-gray-500 dark:text-gray-300">
                    {new Date(toolCall.started_at).toLocaleTimeString(undefined, {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })}
                    {toolCall.completed_at &&
                      ` - ${new Date(toolCall.completed_at).toLocaleTimeString(undefined, {
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
      )}

      {/* Error */}
      {currentStep?.error && (
        <div className="mt-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded">
          <div className="text-sm font-medium text-red-700 dark:text-red-300 mb-1">
            {t('error')}
          </div>
          <div className="text-sm text-red-600 dark:text-red-400">{currentStep?.error}</div>
        </div>
      )}

      {/* Artifacts for this step */}
      <div className="mt-4">
        <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
          {t('artifacts' as any) || '產出'}
        </h4>
        {artifacts.length === 0 ? (
          <div className="p-4 rounded border border-dashed border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-center text-xs text-gray-500 dark:text-gray-400">
            <div className="text-lg mb-1">🗂️</div>
            <div>{t('noArtifacts' as any) || '此步驟尚未產出檔案'}</div>
          </div>
        ) : (
          <div className="space-y-2">
            {artifacts.map((artifact) => (
              <button
                key={artifact.id}
                onClick={() => onViewArtifact?.(artifact)}
                className="w-full text-left p-3 rounded border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                    {artifact.name || artifact.id}
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">
                    {artifact.type || 'file'}
                  </span>
                </div>
                {artifact.createdAt && (
                  <div className="text-[11px] text-gray-500 dark:text-gray-400 mt-1">
                    {new Date(artifact.createdAt).toLocaleTimeString()}
                  </div>
                )}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
