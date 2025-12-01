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

interface StepTimelineWithDetailsProps {
  steps: ExecutionStep[];
  currentStepIndex: number;
  onStepSelect: (stepIndex: number) => void;
  currentStepEvents?: StepEvent[];
  currentStepToolCalls?: ToolCall[];
  currentStepCollaborations?: any[];
  executionStatus?: string;
}

export default function StepTimelineWithDetails({
  steps,
  currentStepIndex,
  onStepSelect,
  currentStepEvents = [],
  currentStepToolCalls = [],
  currentStepCollaborations = [],
  executionStatus
}: StepTimelineWithDetailsProps) {
  const t = useT();
  const currentStep = steps.find(s => s.step_index === currentStepIndex);

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
        return 'text-green-600 bg-green-50 border-green-200';
      case 'running':
        return 'text-blue-600 bg-blue-50 border-blue-200';
      case 'waiting_confirmation':
        return 'text-yellow-600 bg-yellow-50 border-yellow-200';
      case 'failed':
      case 'timeout':
        return 'text-red-600 bg-red-50 border-red-200';
      default:
        return 'text-gray-400 bg-gray-50 border-gray-200';
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
    <div className="flex gap-4 h-full">
      {/* Left: Steps Timeline */}
      <div className="w-64 flex-shrink-0 bg-white rounded-lg border border-gray-200 p-3 overflow-y-auto">
        <h3 className="text-xs font-semibold text-gray-900 mb-2">{t('stepsTimeline')}</h3>
        <div className="space-y-1.5">
          {steps.map((step) => {
            const isSelected = step.step_index === currentStepIndex;
            const statusColor = getStepStatusColor(step);
            const statusIcon = getStepStatusIcon(step);

            return (
              <button
                key={step.id}
                onClick={() => onStepSelect(step.step_index)}
                className={`w-full text-left p-2 rounded border transition-all ${
                  isSelected
                    ? 'border-blue-400 bg-blue-50 shadow-sm ring-1 ring-blue-200'
                    : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                }`}
              >
                <div className="flex items-start gap-1.5">
                  <span className={`flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-medium border ${statusColor}`}>
                    {statusIcon}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-semibold text-gray-900 truncate">
                      {t('stepNumber', { number: step.step_index + 1 })}: {step.step_name || t('unnamed')}
                    </div>
                    {step.agent_type && (
                      <div className="text-[10px] text-gray-500 mt-0.5">
                        {step.agent_type}
                        {step.used_tools && step.used_tools.length > 0 && (
                          <span className="ml-1">· {step.used_tools.length} {t('tools')}</span>
                        )}
                      </div>
                    )}
                    <div className="mt-1">
                      <span className={`px-1 py-0.5 rounded text-[10px] font-medium border ${statusColor}`}>
                        {getEffectiveStepStatus(step)}
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
      <div className="flex-1 bg-white rounded-lg border border-gray-200 p-3 overflow-y-auto">
        {currentStep ? (
          <>
            <div className="mb-3 pb-3 border-b border-gray-200">
              <div className="flex items-center gap-2 mb-1.5">
                <h3 className="text-sm font-semibold text-gray-900">
                  {t('stepNumber', { number: currentStep.step_index + 1 })}: {currentStep.step_name || t('unnamed')}
                </h3>
                <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${getStepStatusColor(currentStep)}`}>
                  {getEffectiveStepStatus(currentStep)}
                </span>
              </div>
              {currentStep.description && (
                <p className="text-xs text-gray-600 mb-1.5">{currentStep.description}</p>
              )}
              {currentStep.agent_type && (
                <div className="text-xs text-gray-500">
                  {t('agent')} <span className="font-medium">{currentStep.agent_type}</span>
                </div>
              )}
            </div>

            {/* Event Stream */}
            <div className="mb-3">
              <h4 className="text-xs font-medium text-gray-900 mb-1.5">{t('eventStream')}</h4>
              {currentStepEvents.length > 0 ? (
                <div className="space-y-1.5">
                  {currentStepEvents.map((event) => (
                    <div
                      key={event.id}
                      className="flex gap-2 p-1.5 bg-gray-50 rounded border border-gray-200"
                    >
                      <div className="flex-shrink-0 text-[10px] text-gray-500 w-14">
                        {event.timestamp.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-[10px] text-gray-600">
                          {event.type === 'tool' && event.tool && (
                            <span className="font-medium">{t('tool')} {event.tool}</span>
                          )}
                          {event.type === 'collaboration' && event.agent && (
                            <span className="font-medium">{t('collaboration')} {event.agent}</span>
                          )}
                          {event.type === 'step' && event.agent && (
                            <span className="font-medium">{t('agent')} {event.agent}</span>
                          )}
                        </div>
                        <div className="text-xs text-gray-900 mt-0.5">{event.content}</div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-xs text-gray-500 italic py-3 text-center border border-gray-200 rounded bg-gray-50">
                  {t('noEventsYet')}
                </div>
              )}
            </div>

            {/* Tool Calls */}
            {currentStepToolCalls.length > 0 && (
              <div className="mb-4">
                <h4 className="text-sm font-medium text-gray-900 mb-2">{t('toolCalls')}</h4>
                <div className="space-y-2">
                  {currentStepToolCalls.map((toolCall) => (
                    <div
                      key={toolCall.id}
                      className="p-3 bg-gray-50 rounded border border-gray-200"
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium text-gray-900">{toolCall.tool_name}</span>
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          toolCall.status === 'completed' ? 'bg-green-100 text-green-700' :
                          toolCall.status === 'failed' ? 'bg-red-100 text-red-700' :
                          'bg-blue-100 text-blue-700'
                        }`}>
                          {toolCall.status}
                        </span>
                      </div>
                      {toolCall.started_at && (
                        <div className="text-xs text-gray-500">
                          {formatTime(toolCall.started_at)}
                          {toolCall.completed_at && ` - ${formatTime(toolCall.completed_at)}`}
                        </div>
                      )}
                      {toolCall.error && (
                        <div className="text-xs text-red-600 mt-1">{toolCall.error}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Error */}
            {currentStep.error && (
              <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded">
                <div className="text-sm font-medium text-red-700 mb-1">{t('error')}</div>
                <div className="text-sm text-red-600">{currentStep.error}</div>
              </div>
            )}
          </>
        ) : (
          <div className="text-center py-8 text-gray-500">
            {t('selectStepToViewDetails')}
          </div>
        )}
      </div>
    </div>
  );
}

