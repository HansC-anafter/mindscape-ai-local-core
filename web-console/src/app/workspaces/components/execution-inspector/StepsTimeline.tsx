'use client';

import React from 'react';
import type { ExecutionStep, PlaybookStepDefinition } from './types/execution';
import { deriveAllSteps } from './utils/execution-inspector';
import { getStepStatusColor, getStepStatusIcon, getEffectiveStepStatus } from './utils/execution-inspector';

export interface StepsTimelineProps {
  steps: ExecutionStep[];
  playbookStepDefinitions?: PlaybookStepDefinition[];
  totalSteps?: number;
  currentStepIndex: number;
  executionStatus?: string;
  onStepSelect: (stepIndex: number) => void;
  t: (key: string, params?: any) => string;
}

export default function StepsTimeline({
  steps,
  playbookStepDefinitions,
  totalSteps,
  currentStepIndex,
  executionStatus,
  onStepSelect,
  t,
}: StepsTimelineProps) {
  const allSteps = deriveAllSteps({
    playbookStepDefinitions,
    totalSteps,
    steps,
  });

  return (
    <div className="h-full overflow-y-auto bg-surface-secondary dark:bg-gray-800 border-r border-default dark:border-gray-700 p-3">
      <h3 className="text-xs font-semibold text-gray-900 dark:text-gray-100 mb-2">
        {t('stepsTimeline')}
      </h3>
      <div className="space-y-1.5">
        {allSteps.map((stepInfo) => {
          const step = stepInfo.executed;
          const isSelected = stepInfo.step_index === currentStepIndex;
          const statusColor = step
            ? getStepStatusColor(step)
            : 'text-gray-400 dark:text-gray-500 bg-surface-accent dark:bg-gray-800 border-default dark:border-gray-700';
          const statusIcon = step
            ? getStepStatusIcon(step, executionStatus)
            : '○';

          return (
            <button
              key={`step-${stepInfo.step_index}-${stepInfo.step_name}`}
              onClick={() => onStepSelect(stepInfo.step_index)}
              disabled={!step}
              className={`w-full text-left p-2 rounded border transition-all ${
                !step
                  ? 'opacity-50 cursor-not-allowed'
                  : isSelected
                  ? 'border-accent dark:border-blue-600 bg-accent-10 dark:bg-blue-900/20 shadow-sm ring-1 ring-accent/30 dark:ring-blue-800'
                  : 'border-default dark:border-gray-700 hover:border-default dark:hover:border-gray-600 hover:bg-tertiary dark:hover:bg-gray-700'
              }`}
            >
              <div className="flex items-start gap-1.5">
                <span
                  className={`flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-medium border ${statusColor}`}
                >
                  {statusIcon}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-semibold text-gray-900 dark:text-gray-100 truncate">
                    {t('stepNumber', { number: stepInfo.step_index })}: {stepInfo.step_name || t('unnamed')}
                  </div>
                  {step?.agent_type && (
                    <div className="text-[10px] text-gray-500 dark:text-gray-300 mt-0.5">
                      {step.agent_type}
                      {step.used_tools && step.used_tools.length > 0 && (
                        <span className="ml-1">
                          · {step.used_tools.length} {t('tools')}
                        </span>
                      )}
                    </div>
                  )}
                  <div className="mt-1">
                    <span
                      className={`px-1 py-0.5 rounded text-[10px] font-medium border ${statusColor}`}
                    >
                      {step ? getEffectiveStepStatus(step, executionStatus) : 'pending'}
                    </span>
                  </div>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
