'use client';

import React, { useEffect, useState, useRef } from 'react';

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
  const [isConnecting, setIsConnecting] = useState(true);
  const [intentStatus, setIntentStatus] = useState<'confirmed' | 'candidate' | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Sync execution prop changes to internal state
  useEffect(() => {
    if (execution.execution_id === currentExecution.execution_id) {
      // Only update if execution_id matches (same execution)
      // Update if current_step_index or total_steps changed
      if (
        execution.current_step_index !== currentExecution.current_step_index ||
        execution.total_steps !== currentExecution.total_steps ||
        execution.status !== currentExecution.status
      ) {
        setCurrentExecution(execution);
      }
    } else {
      // Different execution, update immediately
      setCurrentExecution(execution);
    }
  }, [execution, currentExecution.execution_id, currentExecution.current_step_index, currentExecution.total_steps, currentExecution.status]);

  // Sync currentStep prop changes to internal state
  useEffect(() => {
    if (currentStep) {
      setLatestStep(currentStep);
    }
  }, [currentStep]);

  // Debug: Log execution total_steps
  if (process.env.NODE_ENV === 'development') {
    console.log(`[RunningTimelineItem] Execution ${execution.execution_id.substring(0, 8)}... total_steps: ${execution.total_steps}, current_step_index: ${execution.current_step_index}`);
    console.log(`[RunningTimelineItem] Initial execution object:`, JSON.stringify(execution, null, 2));
  }

  // Fetch intent tag status
  useEffect(() => {
    const fetchIntentStatus = async () => {
      if (!currentExecution.origin_intent_id && !currentExecution.origin_intent_label) {
        return;
      }

      try {
        // If we have origin_intent_id, fetch the intent tag directly
        if (currentExecution.origin_intent_id) {
          const response = await fetch(
            `${apiUrl}/api/v1/workspaces/${workspaceId}/intent-tags/${currentExecution.origin_intent_id}`
          );
          if (response.ok) {
            const intentTag = await response.json();
            setIntentStatus(intentTag.status === 'confirmed' ? 'confirmed' : 'candidate');
          } else if (response.status === 404) {
            // Intent tag not found, might be from a different source, assume confirmed
            setIntentStatus('confirmed');
          }
        } else {
          // If we only have label but no ID, assume candidate (AI inferred)
          setIntentStatus('candidate');
        }
      } catch (err) {
        console.error('Failed to fetch intent status:', err);
        // On error, default to candidate status
        setIntentStatus('candidate');
      }
    };

    fetchIntentStatus();
  }, [currentExecution.origin_intent_id, currentExecution.origin_intent_label, apiUrl, workspaceId]);

  useEffect(() => {
    // Connect to SSE stream
    const streamUrl = `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${execution.execution_id}/stream`;
    const eventSource = new EventSource(streamUrl);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      setIsConnecting(false);
      console.log(`SSE connected for execution ${execution.execution_id}`);
    };

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        // Handle stream_end event to close connection gracefully
        if (data.type === 'stream_end') {
          if (eventSourceRef.current) {
            eventSourceRef.current.close();
            eventSourceRef.current = null;
          }
          return;
        }
        handleSSEEvent(data);
      } catch (err) {
        console.error('Failed to parse SSE event:', err);
      }
    };

    eventSource.onerror = (error) => {
      // Only log error if connection was not intentionally closed
      if (eventSourceRef.current?.readyState === EventSource.CLOSED) {
        // Connection was closed, this is normal
        return;
      }
      // Check if it's a network error (ERR_INCOMPLETE_CHUNKED_ENCODING is expected when stream ends)
      const target = error.target as EventSource;
      if (target?.readyState === EventSource.CLOSED) {
        // Stream ended normally, don't treat as error
        return;
      }
      console.warn('SSE connection issue (may be normal if execution completed):', error);
      setIsConnecting(true);
      // Try to reconnect after delay only if connection is not closed
      setTimeout(() => {
        if (eventSourceRef.current && eventSourceRef.current.readyState !== EventSource.CLOSED) {
          eventSourceRef.current.close();
        }
        // Will reconnect on next render
      }, 5000);
    };

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [execution.execution_id, apiUrl, workspaceId]);

  const handleSSEEvent = (data: any) => {
    switch (data.type) {
      case 'execution_update':
        if (data.execution) {
          const newStatus = data.execution.status;
          const oldStatus = currentExecution?.status;

          // Debug: Log execution update
          if (process.env.NODE_ENV === 'development') {
            console.log('[RunningTimelineItem] Received execution_update:', {
              execution_id: data.execution.execution_id,
              total_steps: data.execution.total_steps,
              current_step_index: data.execution.current_step_index,
              status: newStatus
            });
          }

          // Check if execution status changed to completed
          if ((newStatus === 'succeeded' || newStatus === 'failed') && oldStatus && oldStatus !== newStatus) {
            if (process.env.NODE_ENV === 'development') {
              console.log('[RunningTimelineItem] Execution status changed to completed:', newStatus, 'for execution:', data.execution.execution_id);
            }
            // Trigger task update event when execution completes
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
          if (onUpdate && currentExecution) {
            onUpdate(currentExecution, data.step);
          }
        }
        break;
      case 'execution_completed':
        if (process.env.NODE_ENV === 'development') {
          console.log('[RunningTimelineItem] Execution completed:', data.execution_id, data.status);
        }
        if (eventSourceRef.current) {
          eventSourceRef.current.close();
        }
        // Trigger task update event to refresh task list
        if (process.env.NODE_ENV === 'development') {
          console.log('[RunningTimelineItem] Dispatching workspace-task-updated event');
        }
        window.dispatchEvent(new CustomEvent('workspace-task-updated', {
          detail: {
            execution_id: data.execution_id,
            status: data.status
          }
        }));
        break;
      default:
        // Ignore other event types
        break;
    }
  };

  // Generate Agent/Tool narrative
  const getNarrative = (): string => {
    if (latestStep) {
      const agentLabel = latestStep.agent_type
        ? `${getAgentLabel(latestStep.agent_type)} · `
        : '';
      // Use total_steps from execution, but prefer from step if available
      // If total_steps is 0 or undefined, try to calculate from steps array or use 1 as fallback
      let totalSteps = currentExecution.total_steps;
      if (!totalSteps || totalSteps === 0) {
        // Try to get from step's total_steps if available
        if (latestStep && latestStep.total_steps) {
          totalSteps = latestStep.total_steps;
        } else {
          // Fallback to 1 only if we really can't determine
          totalSteps = 1;
        }
      }
      const stepInfo = `步驟 ${currentExecution.current_step_index + 1}/${totalSteps}`;

      if (latestStep.used_tools && latestStep.used_tools.length > 0) {
        const toolsText = latestStep.used_tools.join(' + ');
        return `${agentLabel}${stepInfo}：正在用 ${toolsText} ${latestStep.log_summary || '執行中...'}`;
      } else if (latestStep.log_summary) {
        return `${agentLabel}${stepInfo}：${latestStep.log_summary}`;
      } else {
        return `${agentLabel}${stepInfo}：執行中...`;
      }
    }
    // Use total_steps from execution, but prefer from step if available
    let totalSteps = currentExecution.total_steps;
    if (!totalSteps || totalSteps === 0) {
      // Fallback to 1 only if we really can't determine
      totalSteps = 1;
    }
    return `步驟 ${currentExecution.current_step_index + 1}/${totalSteps}：執行中...`;
  };

  const getAgentLabel = (agentType: string): string => {
    const agentLabels: Record<string, string> = {
      'researcher': '研究員',
      'editor': '編輯',
      'engineer': '工程師',
      'coordinator': '協調員',
    };
    return agentLabels[agentType] || agentType;
  };

  // Calculate total_steps: prefer from execution, then from step, then fallback to 1
  let totalSteps = currentExecution.total_steps;
  if (!totalSteps || totalSteps === 0) {
    // Try to get from latest step's total_steps if available
    if (latestStep && latestStep.total_steps) {
      totalSteps = latestStep.total_steps;
    } else {
      // Fallback to 1 only if we really can't determine
      totalSteps = 1;
    }
  }
  const progressPercentage = totalSteps > 0
    ? ((currentExecution.current_step_index + 1) / totalSteps) * 100
    : 0;

  return (
    <div
      className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded p-2 shadow-sm cursor-pointer hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors"
      onClick={onClick}
    >
      {/* Intent Breadcrumb */}
      {currentExecution.origin_intent_label && (
        <div className="text-[10px] text-gray-500 dark:text-gray-300 mb-1.5 font-light">
          <span className="text-gray-400 dark:text-gray-400">Intent：</span>
          <span className="text-gray-600 dark:text-gray-200">{currentExecution.origin_intent_label}</span>
          {intentStatus === 'confirmed' && (
            <span className="text-gray-400 dark:text-gray-400 ml-1">（由你確認）</span>
          )}
          {(intentStatus === 'candidate' || intentStatus === null) && (
            <span className="text-gray-400 dark:text-gray-400 ml-1">（AI 推測，執行中仍可更改）</span>
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
            Step {currentExecution.current_step_index + 1}/{totalSteps}
          </span>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="mb-2">
        <div className="w-full bg-blue-200 dark:bg-blue-800 rounded-full h-1.5">
          <div
            className="bg-blue-500 dark:bg-blue-600 h-1.5 rounded-full transition-all duration-300"
            style={{ width: `${progressPercentage}%` }}
          ></div>
        </div>
      </div>

      {/* Agent/Tool Narrative with Spinner */}
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

