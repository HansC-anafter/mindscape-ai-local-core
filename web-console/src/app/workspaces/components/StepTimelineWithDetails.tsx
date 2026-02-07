'use client';

import React from 'react';
import { useT } from '@/lib/i18n';

interface ExecutionStep {
  id: string;
  step_index: number;
  step_name: string;
  status: string;
  agent_type?: string;
  description?: string;
  log_summary?: string;
  error?: string;
  started_at?: string;
  completed_at?: string;
  used_tools?: string[];
}

interface StepEvent {
  id: string;
  type: 'step' | 'tool' | 'collaboration';
  timestamp: Date;
  agent?: string;
  tool?: string;
  content: string;
}

interface ToolCall {
  id: string;
  tool_name: string;
  status: string;
  started_at?: string;
  completed_at?: string;
  error?: string;
}

interface PlaybookStep {
  step_index: number;
  step_name: string;
  description?: string;
  agent_type?: string;
  used_tools?: string[];
}

interface StepTimelineWithDetailsProps {
  steps: ExecutionStep[];
  currentStepIndex: number;
  onStepSelect: (stepIndex: number) => void;
  currentStepEvents?: StepEvent[];
  currentStepToolCalls?: ToolCall[];
  currentStepCollaborations?: any[];
  executionStatus?: string;
  totalSteps?: number;
  playbookSteps?: PlaybookStep[];
}

export default function StepTimelineWithDetails({
  steps,
  currentStepIndex,
  onStepSelect,
  currentStepEvents = [],
  currentStepToolCalls = [],
  currentStepCollaborations = [],
  executionStatus,
  totalSteps,
  playbookSteps,
  className = ''
}: StepTimelineWithDetailsProps & { className?: string }) {
  const t = useT();

  // Create a map of executed steps by step_index (1-based)
  const executedStepsMap = new Map(steps.map(s => [s.step_index, s]));

  // Debug: Log received props
  console.log('[StepTimelineWithDetails] Received props:', {
    steps_count: steps.length,
    steps_step_indices: steps.map(s => s.step_index),
    totalSteps: totalSteps,
    playbookSteps_count: playbookSteps?.length || 0,
    playbookSteps: playbookSteps ? playbookSteps.slice(0, 5).map(s => ({ step_index: s.step_index, step_name: s.step_name })) : null
  });

  // Generate all steps: use playbookSteps if available, otherwise generate from totalSteps
  const allSteps: Array<{ step_index: number; step_name: string; description?: string; executed?: ExecutionStep }> = [];

  if (playbookSteps && playbookSteps.length > 0) {
    // Use playbook step definitions
    console.log('[StepTimelineWithDetails] Using playbookSteps, count:', playbookSteps.length);
    console.log('[StepTimelineWithDetails] playbookSteps step_indices (first 10):', playbookSteps.slice(0, 10).map(s => s.step_index));
    console.log('[StepTimelineWithDetails] playbookSteps step_indices (all):', playbookSteps.map(s => s.step_index));
    playbookSteps.forEach((playbookStep, index) => {
      // Use array index + 1 as step_index to ensure uniqueness
      // The original step_index from playbookStep might have duplicates
      const uniqueStepIndex = index + 1;
      allSteps.push({
        step_index: uniqueStepIndex,
        step_name: playbookStep.step_name,
        description: playbookStep.description,
        executed: executedStepsMap.get(playbookStep.step_index) || executedStepsMap.get(uniqueStepIndex)
      });
    });
    console.log('[StepTimelineWithDetails] Final allSteps count:', allSteps.length);
    console.log('[StepTimelineWithDetails] allSteps step_indices:', allSteps.map(s => s.step_index));
    console.log('[StepTimelineWithDetails] allSteps will render:', allSteps.length, 'steps');
    console.log('[StepTimelineWithDetails] Generated allSteps from playbookSteps (first 10):', allSteps.slice(0, 10).map(s => ({ step_index: s.step_index, step_name: s.step_name, hasExecuted: !!s.executed })));
    if (allSteps.length > 10) {
      console.log('[StepTimelineWithDetails] Generated allSteps from playbookSteps (last 10):', allSteps.slice(-10).map(s => ({ step_index: s.step_index, step_name: s.step_name, hasExecuted: !!s.executed })));
    }
  } else if (totalSteps && totalSteps > 0) {
    // Generate steps from totalSteps
    for (let i = 1; i <= totalSteps; i++) {
      const executed = executedStepsMap.get(i);
      allSteps.push({
        step_index: i,
        step_name: executed?.step_name || `Step ${i}`,
        executed
      });
    }
  } else {
    // Fallback: only show executed steps
    steps.forEach(step => {
      allSteps.push({
        step_index: step.step_index,
        step_name: step.step_name,
        executed: step
      });
    });
  }

  const currentStep = executedStepsMap.get(currentStepIndex) || allSteps.find(s => s.step_index === currentStepIndex)?.executed;
  const currentStepInfo = allSteps.find(s => s.step_index === currentStepIndex);

  const getEffectiveStepStatus = (step: ExecutionStep): string => {
    if (executionStatus?.toLowerCase() === 'failed' && step.status === 'running') {
      return 'timeout'; // Show timeout instead of running when execution failed
    }
    return step.status;
  };

  const getStepStatusIcon = (step: ExecutionStep) => {
    const effectiveStatus = getEffectiveStepStatus(step);
    switch (effectiveStatus) {
      case 'completed':
        return '✓';
      case 'running':
        return '⟳';
      case 'waiting_confirmation':
        return '⏸';
      case 'failed':
      case 'timeout':
        return '✗';
      default:
        return '○';
    }
  };

  const getStepStatusColor = (step: ExecutionStep) => {
    const effectiveStatus = getEffectiveStepStatus(step);
    switch (effectiveStatus) {
      case 'completed':
        return 'text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/30 border-green-200 dark:border-green-700';
      case 'running':
        return 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30 border-blue-200 dark:border-blue-700';
      case 'waiting_confirmation':
        return 'text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900/30 border-yellow-200 dark:border-yellow-700';
      case 'failed':
      case 'timeout':
        return 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/30 border-red-200 dark:border-red-700';
      default:
        return 'text-gray-400 dark:text-gray-500 bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700';
    }
  };

  const formatTime = (timeStr?: string) => {
    if (!timeStr) return '';
    try {
      const date = new Date(timeStr);
      return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return '';
    }
  };

  return (
    <div className={`flex gap-0 h-full w-full ${className}`}>
      {/* Left: Steps Timeline */}
      <div className="w-[280px] h-full flex-shrink-0 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 p-3 overflow-y-auto">
        <h3 className="text-xs font-semibold text-gray-900 dark:text-gray-100 mb-2">{t('stepsTimeline' as any)}</h3>
        <div className="space-y-1.5">
          {allSteps.map((stepInfo, renderIndex) => {
            const step = stepInfo.executed;
            const isSelected = stepInfo.step_index === currentStepIndex;
            // If step not executed yet, show as pending
            const statusColor = step ? getStepStatusColor(step) : 'text-gray-400 dark:text-gray-500 bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700';
            const statusIcon = step ? getStepStatusIcon(step) : '○';

            return (
              <button
                key={`step-${stepInfo.step_index}-${stepInfo.step_name}`}
                onClick={() => onStepSelect(stepInfo.step_index)}
                disabled={!step}
                className={`w-full text-left p-2 rounded border transition-all ${!step
                  ? 'opacity-50 cursor-not-allowed'
                  : isSelected
                    ? 'border-blue-400 dark:border-blue-600 bg-blue-50 dark:bg-blue-900/20 shadow-sm ring-1 ring-blue-200 dark:ring-blue-800'
                    : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700'
                  }`}
              >
                <div className="flex items-start gap-1.5">
                  <span className={`flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-medium border ${statusColor}`}>
                    {statusIcon}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-semibold text-gray-900 dark:text-gray-100 truncate">
                      {t('stepNumber', { number: String(stepInfo.step_index) })}: {stepInfo.step_name || t('unnamed' as any)}
                    </div>
                    {step?.agent_type && (
                      <div className="text-[10px] text-gray-500 dark:text-gray-300 mt-0.5">
                        {step.agent_type}
                        {step.used_tools && step.used_tools.length > 0 && (
                          <span className="ml-1">· {step.used_tools.length} {t('tools' as any)}</span>
                        )}
                      </div>
                    )}
                    <div className="mt-1">
                      <span className={`px-1 py-0.5 rounded text-[10px] font-medium border ${statusColor}`}>
                        {step ? getEffectiveStepStatus(step) : 'pending'}
                      </span>
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Right: Current Step Details */}
      <div className="flex-1 bg-white dark:bg-gray-800 p-3 overflow-y-auto min-w-0">
        {currentStepInfo ? (
          <>
            <div className="mb-3 pb-3 border-b border-gray-200 dark:border-gray-700">
              <div className="flex items-center gap-2 mb-1.5">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                  {t('stepNumber', { number: String(currentStepIndex) })}: {currentStepInfo.step_name || t('unnamed' as any)}
                </h3>
                {currentStep && (
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${getStepStatusColor(currentStep)}`}>
                    {getEffectiveStepStatus(currentStep)}
                  </span>
                )}
              </div>
              {/* Priority: Show executed step description if available, otherwise show playbook step description */}
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
                <p className="text-xs text-gray-500 dark:text-gray-400 italic">{t('stepNotExecutedYet' as any) || 'This step has not been executed yet.'}</p>
              )}
            </div>

            {/* Event Stream */}
            <div className="mb-3">
              <h4 className="text-xs font-medium text-gray-900 dark:text-gray-100 mb-1.5">{t('eventStream' as any)}</h4>
              {currentStepEvents.length > 0 ? (
                <div className="space-y-1.5">
                  {currentStepEvents.map((event) => (
                    <div
                      key={event.id}
                      className="flex gap-2 p-1.5 bg-gray-50 dark:bg-gray-700 rounded border border-gray-200 dark:border-gray-600"
                    >
                      <div className="flex-shrink-0 text-[10px] text-gray-500 dark:text-gray-300 w-14">
                        {event.timestamp.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-[10px] text-gray-600 dark:text-gray-300">
                          {event.type === 'tool' && event.tool && (
                            <span className="font-medium">{t('tool' as any)} {event.tool}</span>
                          )}
                          {event.type === 'collaboration' && event.agent && (
                            <span className="font-medium">{t('collaboration' as any)} {event.agent}</span>
                          )}
                          {event.type === 'step' && event.agent && (
                            <span className="font-medium">{t('agent' as any)} {event.agent}</span>
                          )}
                        </div>
                        <div className="text-xs text-gray-900 dark:text-gray-100 mt-0.5">{event.content}</div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-xs text-gray-500 dark:text-gray-300 italic py-3 text-center border border-gray-200 dark:border-gray-700 rounded bg-gray-50 dark:bg-gray-700">
                  {t('noEventsYet' as any)}
                </div>
              )}
            </div>

            {/* Tool Calls */}
            {currentStepToolCalls.length > 0 && (
              <div className="mb-4">
                <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">{t('toolCalls' as any)}</h4>
                <div className="space-y-2">
                  {currentStepToolCalls.map((toolCall) => (
                    <div
                      key={toolCall.id}
                      className="p-3 bg-gray-50 dark:bg-gray-700 rounded border border-gray-200 dark:border-gray-600"
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{toolCall.tool_name}</span>
                        <span className={`text-xs px-2 py-0.5 rounded ${toolCall.status === 'completed' ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300' :
                          toolCall.status === 'failed' ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300' :
                            'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                          }`}>
                          {toolCall.status}
                        </span>
                      </div>
                      {toolCall.started_at && (
                        <div className="text-xs text-gray-500 dark:text-gray-300">
                          {formatTime(toolCall.started_at)}
                          {toolCall.completed_at && ` - ${formatTime(toolCall.completed_at)}`}
                        </div>
                      )}
                      {toolCall.error && (
                        <div className="text-xs text-red-600 dark:text-red-400 mt-1">{toolCall.error}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Error */}
            {currentStep?.error && (
              <div className="mt-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded">
                <div className="text-sm font-medium text-red-700 dark:text-red-300 mb-1">{t('error' as any)}</div>
                <div className="text-sm text-red-600 dark:text-red-400">{currentStep?.error}</div>
              </div>
            )}
          </>
        ) : (
          <div className="text-center py-8 text-gray-500 dark:text-gray-300">
            {t('selectStepToViewDetails' as any) || '請選擇步驟以查看詳情'}
          </div>
        )}
      </div>
    </div>
  );
}

