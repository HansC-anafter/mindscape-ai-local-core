'use client';

import React, { useEffect, useState } from 'react';
import { useT } from '@/lib/i18n';
import WorkflowStepCard from './WorkflowStepCard';

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
  origin_intent_id?: string;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
  failure_type?: string;
  failure_reason?: string;
  [key: string]: any;
}

interface ExecutionStep {
  id: string;
  execution_id: string;
  step_index: number;
  step_name: string;
  status: string;
  step_type: string;
  agent_type?: string;
  used_tools?: string[];
  assigned_agent?: string;
  collaborating_agents?: string[];
  description?: string;
  log_summary?: string;
  requires_confirmation: boolean;
  confirmation_prompt?: string;
  confirmation_status?: string;
  started_at?: string;
  completed_at?: string;
  error?: string;
  failure_type?: string;
  [key: string]: any;
}

interface ExecutionConsoleProps {
  executionId: string;
  workspaceId: string;
  apiUrl: string;
  onClose: () => void;
}

export default function ExecutionConsole({
  executionId,
  workspaceId,
  apiUrl,
  onClose
}: ExecutionConsoleProps) {
  const t = useT();
  const [execution, setExecution] = useState<ExecutionSession | null>(null);
  const [steps, setSteps] = useState<ExecutionStep[]>([]);
  const [currentStepIndex, setCurrentStepIndex] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [toolCalls, setToolCalls] = useState<any[]>([]);
  const [collaborations, setCollaborations] = useState<any[]>([]);
  const [stageResults, setStageResults] = useState<any[]>([]);

  // Load execution details
  useEffect(() => {
    const loadExecution = async () => {
      try {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}`
        );
        if (response.ok) {
          const data = await response.json();
          setExecution(data);
          setCurrentStepIndex(data.current_step_index || 0);
        }
      } catch (err) {
        console.error('Failed to load execution:', err);
      } finally {
        setLoading(false);
      }
    };

    loadExecution();
  }, [executionId, workspaceId, apiUrl]);

  // Load steps, tool calls, collaborations, and stage results
  useEffect(() => {
    const loadStepDetails = async () => {
      try {
        // Load steps
        const stepsResponse = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/steps`
        );
        if (stepsResponse.ok) {
          const stepsData = await stepsResponse.json();
          setSteps(stepsData.steps || []);
        }

        // Load tool calls
        try {
          const toolCallsResponse = await fetch(
            `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/tool-calls`
          );
          if (toolCallsResponse.ok) {
            const toolCallsData = await toolCallsResponse.json();
            setToolCalls(toolCallsData.tool_calls || []);
          }
        } catch (err) {
          console.warn('Failed to load tool calls:', err);
        }

        // Load stage results
        try {
          const stageResultsResponse = await fetch(
            `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/stage-results`
          );
          if (stageResultsResponse.ok) {
            const stageResultsData = await stageResultsResponse.json();
            setStageResults(stageResultsData.stage_results || []);
          }
        } catch (err) {
          console.warn('Failed to load stage results:', err);
        }

        // Load agent collaborations (from AGENT_EXECUTION events)
        try {
          const eventsResponse = await fetch(
            `${apiUrl}/api/v1/workspaces/${workspaceId}/events?event_types=AGENT_EXECUTION&execution_id=${executionId}&limit=100`
          );
          if (eventsResponse.ok) {
            const eventsData = await eventsResponse.json();
            const collaborationEvents = (eventsData.events || []).filter(
              (e: any) => e.event_type === 'AGENT_EXECUTION' && e.payload?.is_agent_collaboration
            );
            setCollaborations(collaborationEvents.map((e: any) => ({
              id: e.id,
              execution_id: e.payload?.execution_id,
              step_id: e.payload?.step_id,
              collaboration_type: e.payload?.collaboration_type,
              participants: e.payload?.participants || [],
              topic: e.payload?.topic,
              discussion: e.payload?.discussion || [],
              status: e.payload?.status,
              result: e.payload?.result,
              started_at: e.payload?.started_at,
              completed_at: e.payload?.completed_at
            })));
          }
        } catch (err) {
          console.warn('Failed to load agent collaborations:', err);
        }
      } catch (err) {
        console.error('Failed to load step details:', err);
      }
    };

    if (executionId) {
      loadStepDetails();
    }
  }, [executionId, workspaceId, apiUrl]);

  // Connect to SSE stream for real-time updates
  useEffect(() => {
    if (!executionId) return;

    const streamUrl = `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/stream`;
    const eventSource = new EventSource(streamUrl);

    eventSource.onmessage = (event) => {
      try {
        const update = JSON.parse(event.data);

        if (update.type === 'execution_update') {
          setExecution(update.execution);
          setCurrentStepIndex(update.execution?.current_step_index || 0);
        } else if (update.type === 'step_update') {
          setSteps(prev => {
            const index = prev.findIndex(s => s.id === update.step.id);
            if (index >= 0) {
              const updated = [...prev];
              updated[index] = update.step;
              return updated;
            } else {
              return [...prev, update.step];
            }
          });
        } else if (update.type === 'execution_completed') {
          // Reload execution and steps
          window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
        }
      } catch (err) {
        console.error('Failed to parse SSE message:', err);
      }
    };

    eventSource.onerror = (err) => {
      console.error('SSE connection error:', err);
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [executionId, workspaceId, apiUrl]);

  const currentStep = steps.find(s => s.step_index === currentStepIndex);

  const getStepStatusIcon = (step: ExecutionStep) => {
    if (step.status === 'completed') return '✓';
    if (step.status === 'running') return '⟳';
    if (step.status === 'waiting_confirmation') return '⏸';
    return '○';
  };

  const getStepStatusColor = (step: ExecutionStep) => {
    if (step.status === 'completed') return 'text-green-600';
    if (step.status === 'running') return 'text-blue-600';
    if (step.status === 'waiting_confirmation') return 'text-yellow-600';
    return 'text-gray-400';
  };

  if (loading) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center">
        <div className="bg-white rounded-lg p-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-2xl w-full max-w-6xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b">
          <div className="flex-1">
            <h2 className="text-xl font-semibold text-gray-900">
              Playbook: {execution?.playbook_code || 'Execution'}
            </h2>
            {execution?.origin_intent_label && (
              <p className="text-sm text-gray-600 mt-1">
                Intent: {execution.origin_intent_label}
                {execution.origin_intent_id && execution.trigger_source === 'auto' && (
                  <span className="text-gray-500 ml-2">{t('executionAISuggested' as any)}</span>
                )}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="ml-4 text-gray-400 hover:text-gray-600 transition-colors"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden flex">
          {/* Steps List */}
          <div className="w-64 border-r bg-gray-50 overflow-y-auto">
            <div className="p-4">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">Steps</h3>
              <div className="space-y-2">
                {steps.map((step) => (
                  <div
                    key={step.id}
                    className={`p-3 rounded border cursor-pointer transition-colors ${
                      step.step_index === currentStepIndex
                        ? 'bg-blue-50 border-blue-300'
                        : 'bg-white border-gray-200 hover:bg-gray-50'
                    }`}
                    onClick={() => setCurrentStepIndex(step.step_index)}
                  >
                    <div className="flex items-center gap-2">
                      <span className={`text-sm font-medium ${getStepStatusColor(step)}`}>
                        {getStepStatusIcon(step)}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium text-gray-900 truncate">
                          Step {step.step_index + 1}: {step.step_name}
                        </div>
                        {step.requires_confirmation && (
                          <div className="text-xs text-yellow-600 mt-1">{t('executionRequiresConfirmation' as any)}</div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Step Details */}
          <div className="flex-1 overflow-y-auto p-6">
            {currentStep ? (
              <WorkflowStepCard
                step={currentStep}
                isActive={currentStep.step_index === currentStepIndex}
                toolCalls={toolCalls.filter(tc => tc.step_id === currentStep.id)}
                collaborations={collaborations.filter(c => c.step_id === currentStep.id)}
                stageResults={stageResults.filter(sr => sr.step_id === currentStep.id)}
                onConfirm={async (stepId) => {
                  try {
                    const response = await fetch(
                      `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/steps/${stepId}/confirm`,
                      { method: 'POST' }
                    );
                    if (response.ok) {
                      window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
                      // Reload execution and steps
                      const execResponse = await fetch(
                        `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}`
                      );
                      if (execResponse.ok) {
                        const execData = await execResponse.json();
                        setExecution(execData);
                        setCurrentStepIndex(execData.current_step_index || 0);
                      }
                    }
                  } catch (err) {
                    console.error('Failed to confirm step:', err);
                  }
                }}
                onReject={async (stepId) => {
                  try {
                    const response = await fetch(
                      `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/steps/${stepId}/reject`,
                      { method: 'POST' }
                    );
                    if (response.ok) {
                      window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
                      // Reload execution and steps
                      const execResponse = await fetch(
                        `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}`
                      );
                      if (execResponse.ok) {
                        const execData = await execResponse.json();
                        setExecution(execData);
                        setCurrentStepIndex(execData.current_step_index || 0);
                      }
                    }
                  } catch (err) {
                    console.error('Failed to reject step:', err);
                  }
                }}
              />
            ) : (
              <div className="text-center text-gray-500 py-8">
                {t('executionSelectStepForDetails' as any)}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="border-t p-4 bg-gray-50">
          <div className="flex items-center justify-between">
            <div className="text-sm text-gray-600">
              Status: <span className="font-medium">{execution?.status || 'Unknown'}</span>
              {execution && execution.total_steps > 0 && (
                <span className="ml-4">
                  Progress: {currentStepIndex + 1} / {execution.total_steps}
                </span>
              )}
            </div>
            {execution?.status === 'running' && (
              <button
                onClick={async () => {
                  try {
                    const response = await fetch(
                      `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/cancel`,
                      { method: 'POST' }
                    );
                    if (response.ok) {
                      window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
                      onClose();
                    }
                  } catch (err) {
                    console.error('Failed to cancel execution:', err);
                  }
                }}
                className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 transition-colors"
              >
                {t('executionCancel' as any)}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

