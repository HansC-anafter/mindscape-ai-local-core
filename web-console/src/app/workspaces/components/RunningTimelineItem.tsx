'use client';

import React, { useEffect, useState } from 'react';
import { useExecutionPolling } from '@/hooks/useExecutionPolling';

interface ExecutionSession {
  execution_id: string;
  workspace_id: string;
  status: string;
  playbook_code?: string;
  trigger_source?: string;
  current_step_index: number;
  total_steps: number;
  paused_at?: string;
  origin_intent_label?: string;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
  [key: string]: any;
}

interface ExecutionStep {
  id: string;
  execution_id: string;
  step_index: number;
  step_name: string;
  status: string;
  agent_type?: string;
  used_tools?: string[];
  log_summary?: string;
  requires_confirmation: boolean;
  [key: string]: any;
}

interface RunningTimelineItemProps {
  execution: ExecutionSession;
  apiUrl: string;
  workspaceId: string;
  currentStep?: ExecutionStep | null;
  onUpdate?: (execution: ExecutionSession, step?: ExecutionStep) => void;
  onClick?: () => void;
}

export default function RunningTimelineItem({
  execution,
  apiUrl,
  workspaceId,
  currentStep,
  onUpdate,
  onClick
}: RunningTimelineItemProps) {
  const [currentExecution, setCurrentExecution] = useState<ExecutionSession>(execution);
  const [latestStep, setLatestStep] = useState<ExecutionStep | null>(currentStep || null);
  const [intentStatus, setIntentStatus] = useState<'confirmed' | 'candidate' | null>(null);

  useEffect(() => {
    if (execution.execution_id === currentExecution.execution_id) {
      if (
        execution.current_step_index !== currentExecution.current_step_index ||
        execution.total_steps !== currentExecution.total_steps ||
        execution.status !== currentExecution.status
      ) {
        setCurrentExecution(execution);
      }
    } else {
      setCurrentExecution(execution);
    }
  }, [execution, currentExecution.execution_id, currentExecution.current_step_index, currentExecution.total_steps, currentExecution.status]);

  useEffect(() => {
    if (currentStep) {
      setLatestStep(currentStep);
    }
  }, [currentStep]);

  useEffect(() => {
    const fetchIntentStatus = async () => {
      if (!currentExecution.origin_intent_id && !currentExecution.origin_intent_label) {
        return;
      }

      try {
        if (currentExecution.origin_intent_id) {
          const response = await fetch(
            `${apiUrl}/api/v1/workspaces/${workspaceId}/intent-tags/${currentExecution.origin_intent_id}`
          );
          if (response.ok) {
            const intentTag = await response.json();
            setIntentStatus(intentTag.status === 'confirmed' ? 'confirmed' : 'candidate');
          } else if (response.status === 404) {
            setIntentStatus('confirmed');
          }
        } else {
          setIntentStatus('candidate');
        }
      } catch (err) {
        console.error('Failed to fetch intent status:', err);
        setIntentStatus('candidate');
      }
    };

    fetchIntentStatus();
  }, [currentExecution.origin_intent_id, currentExecution.origin_intent_label, apiUrl, workspaceId]);

  const handleSSEEvent = (data: any) => {
    switch (data.type) {
      case 'execution_update':
        if (data.execution) {
          const newStatus = data.execution.status;
          const oldStatus = currentExecution?.status;

          if ((newStatus === 'succeeded' || newStatus === 'failed') && oldStatus && oldStatus !== newStatus) {
            window.dispatchEvent(new CustomEvent('workspace-task-updated', {
              detail: {
                execution_id: data.execution.execution_id,
                status: newStatus
              }
            }));
          }

          setCurrentExecution(data.execution);
          if (onUpdate) {
            onUpdate(data.execution, latestStep || undefined);
          }
        }
        break;
      case 'step_update':
        if (data.step) {
          setLatestStep(data.step);
          if (data.current_step_index !== undefined && currentExecution) {
            const updatedExecution = {
              ...currentExecution,
              current_step_index: data.current_step_index
            };
            setCurrentExecution(updatedExecution);
            if (onUpdate) {
              onUpdate(updatedExecution, data.step);
            }
          } else if (onUpdate && currentExecution) {
            onUpdate(currentExecution, data.step);
          }
        }
        break;
      case 'execution_completed':
        window.dispatchEvent(new CustomEvent('workspace-task-updated', {
          detail: {
            execution_id: data.execution_id,
            status: data.status
          }
        }));
        break;
      default:
        break;
    }
  };

  const { sseConnected } = useExecutionPolling({
    executionId: execution.execution_id,
    workspaceId,
    apiUrl,
    onUpdate: handleSSEEvent,
    executionStatus: currentExecution.status,
    enableSSE: true,
    enablePollingFallback: false,
  });

  const isConnecting = !sseConnected;

  const getNarrative = (): string => {
    if (latestStep) {
      const agentLabel = latestStep.agent_type
        ? `${getAgentLabel(latestStep.agent_type)} - `
        : '';
      let totalSteps = currentExecution.total_steps;
      if (!totalSteps || totalSteps === 0) {
        totalSteps = 1;
      }
      const stepIndex = currentExecution.current_step_index;
      const stepInfo = `Step ${stepIndex + 1}/${totalSteps}`;

      if (latestStep.used_tools && latestStep.used_tools.length > 0) {
        const toolsText = latestStep.used_tools.join(' + ');
        return `${agentLabel}${stepInfo}: using ${toolsText} ${latestStep.log_summary || 'running...'}`;
      } else if (latestStep.log_summary) {
        return `${agentLabel}${stepInfo}: ${latestStep.log_summary}`;
      } else {
        return `${agentLabel}${stepInfo}: running...`;
      }
    }
    let totalSteps = currentExecution.total_steps;
    if (!totalSteps || totalSteps === 0) {
      totalSteps = 1;
    }
    return `Step ${currentExecution.current_step_index + 1}/${totalSteps}: running...`;
  };

  const getAgentLabel = (agentType: string): string => {
    const agentLabels: Record<string, string> = {
      'researcher': 'Researcher',
      'editor': 'Editor',
      'engineer': 'Engineer',
      'coordinator': 'Coordinator',
    };
    return agentLabels[agentType] || agentType;
  };

  let totalSteps = currentExecution.total_steps;
  if (!totalSteps || totalSteps === 0) {
    totalSteps = 1;
  }
  const currentStepIndex = currentExecution.current_step_index;
  const progressPercentage = totalSteps > 0
    ? ((currentStepIndex + 1) / totalSteps) * 100
    : 0;

  return (
    <div
      className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded p-2 shadow-sm cursor-pointer hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors"
      onClick={onClick}
    >
      {currentExecution.origin_intent_label && (
        <div className="text-[10px] text-gray-500 dark:text-gray-300 mb-1.5 font-light">
          <span className="text-gray-400 dark:text-gray-400">Intent: </span>
          <span className="text-gray-600 dark:text-gray-200">{currentExecution.origin_intent_label}</span>
          {intentStatus === 'confirmed' && (
            <span className="text-gray-400 dark:text-gray-400 ml-1">(confirmed by you)</span>
          )}
          {(intentStatus === 'candidate' || intentStatus === null) && (
            <span className="text-gray-400 dark:text-gray-400 ml-1">(AI inferred, editable while running)</span>
          )}
        </div>
      )}

      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-blue-900 dark:text-blue-200">
            {currentExecution.playbook_code || 'Playbook Execution'}
          </span>
          {currentExecution.trigger_source && (
            <span className="inline-block px-1.5 py-0.5 text-xs rounded border bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-700">
              {currentExecution.trigger_source}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {isConnecting && (
            <span className="text-xs text-gray-500 dark:text-gray-300">Connecting...</span>
          )}
          <span className="text-xs text-blue-600 dark:text-blue-400 font-medium">
            Step {currentStepIndex + 1}/{totalSteps}
          </span>
        </div>
      </div>

      <div className="mb-2">
        <div className="w-full bg-blue-200 dark:bg-blue-800 rounded-full h-1.5">
          <div
            className="bg-blue-500 dark:bg-blue-600 h-1.5 rounded-full transition-all duration-300"
            style={{ width: `${progressPercentage}%` }}
          ></div>
        </div>
      </div>

      <div className="flex items-start gap-2">
        <div className="flex-shrink-0 mt-0.5">
          <div className="relative w-4 h-4">
            <div className="absolute inset-0 border-2 border-blue-300 dark:border-blue-500 border-t-blue-600 dark:border-t-blue-400 rounded-full animate-spin"></div>
          </div>
        </div>
        <div className="flex-1">
          <p className="text-xs text-blue-800 dark:text-blue-200 leading-relaxed">
            {getNarrative()}
          </p>
        </div>
      </div>
    </div>
  );
}
