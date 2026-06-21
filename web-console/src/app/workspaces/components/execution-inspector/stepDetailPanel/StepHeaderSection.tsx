import React from 'react';

import { getEffectiveStepStatus, getStepStatusColor } from '../utils/execution-inspector';
import type { ExecutionStep } from '../types/execution';
import type { StepInfo, Translator } from './stepDetailPanelTypes';

export function StepHeaderSection({
  currentStep,
  currentStepIndex,
  currentStepInfo,
  executionStatus,
  t,
}: {
  currentStep?: ExecutionStep;
  currentStepIndex: number;
  currentStepInfo: StepInfo;
  executionStatus?: string;
  t: Translator;
}) {
  return (
    <div className="mb-3 pb-3 border-b border-gray-200 dark:border-gray-700">
      <div className="flex items-center gap-2 mb-1.5">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          {t('stepNumber', { number: currentStepIndex })}: {currentStepInfo.step_name || t('unnamed' as any)}
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
          {t('agent' as any)} <span className="font-medium">{currentStep.agent_type}</span>
        </div>
      )}
      {!currentStep && (
        <p className="text-xs text-gray-500 dark:text-gray-400 italic">
          {t('stepNotExecutedYet' as any) || 'This step has not been executed yet.'}
        </p>
      )}
    </div>
  );
}
