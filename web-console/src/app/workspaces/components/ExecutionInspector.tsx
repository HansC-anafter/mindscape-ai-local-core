'use client';

import React, { useEffect, useState } from 'react';
import { useT } from '@/lib/i18n';
import ExecutionChatPanel from './ExecutionChatPanel';
import ExecutionHeader from './ExecutionHeader';
import StepTimelineWithDetails from './StepTimelineWithDetails';
import PlaybookRevisionArea from './PlaybookRevisionArea';
import WorkflowVisualization from './WorkflowVisualization';

interface ExecutionSession {
  execution_id: string;
  workspace_id: string;
  status: string;
  playbook_code?: string;
  playbook_version?: string;
  trigger_source?: 'auto' | 'suggestion' | 'manual';
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

interface AgentCollaboration {
  id: string;
  execution_id: string;
  step_id: string;
  collaboration_type: string;
  participants: string[];
  topic: string;
  discussion?: Array<{ agent: string; content: string; timestamp?: string }>;
  status: string;
  result?: Record<string, any>;
  started_at?: string;
  completed_at?: string;
}

interface ToolCall {
  id: string;
  execution_id: string;
  step_id: string;
  tool_name: string;
  tool_id?: string;
  parameters?: Record<string, any>;
  response?: Record<string, any>;
  status: string;
  error?: string;
  duration_ms?: number;
  factory_cluster?: string;
  started_at?: string;
  completed_at?: string;
  created_at: string;
}

interface StageResult {
  id: string;
  execution_id: string;
  step_id: string;
  stage_name: string;
  result_type: string;
  content: Record<string, any>;
  preview?: string;
  requires_review: boolean;
  review_status?: string;
  artifact_id?: string;
  created_at: string;
}

interface PlaybookMetadata {
  playbook_code: string;
  title?: string;
  description?: string;
  version?: string;
  parameters?: Record<string, any>;
  [key: string]: any;
}

interface ExecutionInspectorProps {
  executionId: string;
  workspaceId: string;
  apiUrl: string;
  onClose?: () => void;
}

export default function ExecutionInspector({
  executionId,
  workspaceId,
  apiUrl,
  onClose
}: ExecutionInspectorProps) {
  const t = useT();
  const [execution, setExecution] = useState<ExecutionSession | null>(null);
  const [steps, setSteps] = useState<ExecutionStep[]>([]);
  const [currentStepIndex, setCurrentStepIndex] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [collaborations, setCollaborations] = useState<AgentCollaboration[]>([]);
  const [stageResults, setStageResults] = useState<StageResult[]>([]);
  const [playbookMetadata, setPlaybookMetadata] = useState<PlaybookMetadata | null>(null);
  const [rightPanelTab, setRightPanelTab] = useState<'info' | 'chat'>('info');
  const [duration, setDuration] = useState<string>('');
  const [stepEvents, setStepEvents] = useState<Array<{
    id: string;
    type: 'step' | 'tool' | 'collaboration';
    timestamp: Date;
    agent?: string;
    tool?: string;
    content: string;
  }>>([]);
  const [workflowData, setWorkflowData] = useState<{
    workflow_result?: any;
    handoff_plan?: any;
  } | null>(null);

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

  // Load workflow data for multi-step workflows
  useEffect(() => {
    const loadWorkflowData = async () => {
      try {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/workflow`
        );
        if (response.ok) {
          const data = await response.json();
          if (data.workflow_result || data.handoff_plan) {
            setWorkflowData(data);
          }
        } else if (response.status === 404) {
          setWorkflowData(null);
        }
      } catch (err) {
        console.error('Failed to load workflow data:', err);
        setWorkflowData(null);
      }
    };

    if (executionId) {
      loadWorkflowData();
    }
  }, [executionId, workspaceId, apiUrl]);

  // Set default tab to 'chat' if playbook supports execution chat
  useEffect(() => {
    if (playbookMetadata?.supports_execution_chat) {
      setRightPanelTab('chat');
    }
  }, [playbookMetadata?.supports_execution_chat]);

  // Calculate and update duration
  useEffect(() => {
    if (!execution?.started_at) {
      setDuration('');
      return;
    }

    const updateDuration = () => {
      const start = new Date(execution.started_at!);
      // Use completed_at if execution is finished, otherwise use current time
      const end = execution.completed_at
        ? new Date(execution.completed_at)
        : new Date();
      const diffMs = end.getTime() - start.getTime();

      const hours = Math.floor(diffMs / (1000 * 60 * 60));
      const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
      const seconds = Math.floor((diffMs % (1000 * 60)) / 1000);

      if (hours > 0) {
        setDuration(`${hours}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`);
      } else if (minutes > 0) {
        setDuration(`${minutes}:${seconds.toString().padStart(2, '0')}`);
      } else {
        setDuration(`${seconds}s`);
      }
    };

    updateDuration();

    // Only poll if execution is still running
    // If execution is completed (succeeded/failed), duration is fixed and doesn't need updates
    if (execution.status === 'running') {
      const interval = setInterval(updateDuration, 1000);
      return () => clearInterval(interval);
    }
  }, [execution?.started_at, execution?.status, execution?.completed_at]);

  // Load playbook metadata (optional - endpoint may not exist yet)
  useEffect(() => {
    if (!execution?.playbook_code) return;

    const loadPlaybookMetadata = async () => {
      try {
        const response = await fetch(
          `${apiUrl}/api/v1/playbooks/${execution.playbook_code}`
        );
        if (response.ok) {
          const data = await response.json();
          setPlaybookMetadata(data);
        } else if (response.status === 404) {
          // Endpoint not implemented yet, use basic metadata from execution
          setPlaybookMetadata({
            playbook_code: execution.playbook_code || '',
            version: execution.playbook_version || '1.0.0'
          });
        }
      } catch (err) {
        // Silently ignore errors, use basic metadata from execution
        setPlaybookMetadata({
          playbook_code: execution.playbook_code || '',
          version: execution.playbook_version || '1.0.0'
        });
      }
    };

    loadPlaybookMetadata();
  }, [execution?.playbook_code, execution?.playbook_version, apiUrl]);

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
          const stepsArray = stepsData.steps || [];
          // Remove duplicates by step.id, keeping the last occurrence
          const uniqueSteps = Array.from(
            new Map(stepsArray.map((step: ExecutionStep) => [step.id, step])).values()
          );
          // Sort by step_index to maintain order
          uniqueSteps.sort((a, b) => a.step_index - b.step_index);
          setSteps(uniqueSteps);
        }

        // Load tool calls (optional - endpoint may not exist yet)
        try {
          const toolCallsResponse = await fetch(
            `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/tool-calls`
          );
          if (toolCallsResponse.ok) {
            const toolCallsData = await toolCallsResponse.json();
            setToolCalls(toolCallsData.tool_calls || []);
          } else if (toolCallsResponse.status === 404) {
            // Endpoint not implemented yet, silently ignore
            setToolCalls([]);
          }
        } catch (err) {
          // Silently ignore errors for optional endpoints
          setToolCalls([]);
        }

        // Load stage results (optional - endpoint may not exist yet)
        try {
          const stageResultsResponse = await fetch(
            `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/stage-results`
          );
          if (stageResultsResponse.ok) {
            const stageResultsData = await stageResultsResponse.json();
            setStageResults(stageResultsData.stage_results || []);
          } else if (stageResultsResponse.status === 404) {
            // Endpoint not implemented yet, silently ignore
            setStageResults([]);
          }
        } catch (err) {
          // Silently ignore errors for optional endpoints
          setStageResults([]);
        }

        // Load agent collaborations
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
              // Remove duplicates and sort by step_index
              const uniqueSteps = Array.from(
                new Map(updated.map((step: ExecutionStep) => [step.id, step])).values()
              );
              uniqueSteps.sort((a, b) => a.step_index - b.step_index);
              return uniqueSteps;
            } else {
              const newSteps = [...prev, update.step];
              // Remove duplicates and sort by step_index
              const uniqueSteps = Array.from(
                new Map(newSteps.map((step: ExecutionStep) => [step.id, step])).values()
              );
              uniqueSteps.sort((a, b) => a.step_index - b.step_index);
              return uniqueSteps;
            }
          });
          // Add to step events if it's the current step
          if (update.step.step_index === currentStepIndex) {
            setStepEvents(prev => {
              // Check if event already exists to avoid duplicates
              const exists = prev.some(e => e.id === update.step.id && e.type === 'step');
              if (exists) {
                return prev;
              }
              return [...prev, {
                id: update.step.id,
                type: 'step',
                timestamp: new Date(),
                agent: update.step.agent_type,
                content: update.step.log_summary || 'Step updated'
              }];
            });
          }
        } else if (update.type === 'tool_call_update') {
          // Add tool call event if it belongs to current step
          if (update.tool_call && currentStep && update.tool_call.step_id === currentStep.id) {
            setStepEvents(prev => {
              // Check if event already exists to avoid duplicates
              const exists = prev.some(e => e.id === update.tool_call.id && e.type === 'tool');
              if (exists) {
                return prev;
              }
              return [...prev, {
                id: update.tool_call.id,
                type: 'tool',
                timestamp: new Date(),
                tool: update.tool_call.tool_name,
                content: `Tool: ${update.tool_call.tool_name} completed, ${update.tool_call.summary || 'execution completed'}`
              }];
            });
          }
        } else if (update.type === 'collaboration_update') {
          // Add collaboration event if it belongs to current step
          if (update.collaboration && currentStep && update.collaboration.step_id === currentStep.id) {
            setStepEvents(prev => {
              // Check if event already exists to avoid duplicates
              const exists = prev.some(e => e.id === update.collaboration.id && e.type === 'collaboration');
              if (exists) {
                return prev;
              }
              return [...prev, {
                id: update.collaboration.id,
                type: 'collaboration',
                timestamp: new Date(),
                agent: update.collaboration.participants?.[0] || 'Agent',
                content: `Collaboration: ${update.collaboration.topic || 'Agent discussion'}`
              }];
            });
          }
        } else if (update.type === 'execution_completed') {
          window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
        }
      } catch (err) {
        console.error('Failed to parse SSE message:', err);
      }
    };

    eventSource.onerror = (err) => {
      // SSE connection errors are common during development, only log if connection was established
      if (eventSource.readyState === EventSource.OPEN) {
        console.warn('SSE connection error:', err);
      }
      // Don't close on error - EventSource will auto-reconnect
    };

    return () => {
      eventSource.close();
    };
  }, [executionId, workspaceId, apiUrl]);

  const currentStep = steps.find(s => s.step_index === currentStepIndex);
  const currentStepToolCalls = toolCalls.filter(tc => tc.step_id === currentStep?.id);
  const currentStepCollaborations = collaborations.filter(c => c.step_id === currentStep?.id);
  const currentStepStageResults = stageResults.filter(sr => sr.step_id === currentStep?.id);

  // Filter step events for current step only
  useEffect(() => {
    if (currentStep) {
      setStepEvents(prev => prev.filter(e => {
        // Keep events that match current step context
        if (e.type === 'step') {
          const step = steps.find(s => s.id === e.id);
          return step?.step_index === currentStepIndex;
        } else if (e.type === 'tool') {
          const toolCall = toolCalls.find(tc => tc.id === e.id);
          return toolCall?.step_id === currentStep.id;
        } else if (e.type === 'collaboration') {
          const collab = collaborations.find(c => c.id === e.id);
          return collab?.step_id === currentStep.id;
        }
        return false;
      }));
    }
  }, [currentStepIndex, currentStep?.id, steps, toolCalls, collaborations]);

  const getStepStatusIcon = (step: ExecutionStep) => {
    if (step.status === 'completed') return '[Done]';
    if (step.status === 'running') return '[Running]';
    if (step.status === 'waiting_confirmation') return '[Paused]';
    if (step.status === 'failed') return '[Failed]';
    return '[Pending]';
  };

  const getStepStatusColor = (step: ExecutionStep) => {
    if (step.status === 'completed') return 'text-green-600 bg-green-50 border-green-200';
    if (step.status === 'running') return 'text-blue-600 bg-blue-50 border-blue-200';
    if (step.status === 'waiting_confirmation') return 'text-yellow-600 bg-yellow-50 border-yellow-200';
    if (step.status === 'failed') return 'text-red-600 bg-red-50 border-red-200';
    return 'text-gray-400 bg-gray-50 border-gray-200';
  };

  const getTriggerSourceBadge = (source?: string) => {
    switch (source) {
      case 'auto':
        return { label: t('triggerSourceAuto'), color: 'bg-blue-100 text-blue-700 border-blue-300' };
      case 'suggestion':
        return { label: t('triggerSourceSuggested'), color: 'bg-purple-100 text-purple-700 border-purple-300' };
      case 'manual':
        return { label: t('triggerSourceManual'), color: 'bg-gray-100 text-gray-700 border-gray-300' };
      default:
        return { label: t('triggerSourceUnknown'), color: 'bg-gray-100 text-gray-700 border-gray-300' };
    }
  };

  const getAgentAvatar = (agentType: string) => {
    const avatars: Record<string, string> = {
      'researcher': '🔬',
      'editor': '✍️',
      'engineer': '⚙️',
      'coordinator': '🎯',
    };
    return avatars[agentType] || '🤖';
  };

  const handleConfirm = async () => {
    if (!currentStep) return;
    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/steps/${currentStep.id}/confirm`,
        { method: 'POST' }
      );
      if (response.ok) {
        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
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
  };

  const handleReject = async () => {
    if (!currentStep) return;
    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/steps/${currentStep.id}/reject`,
        { method: 'POST' }
      );
      if (response.ok) {
        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
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
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  // Calculate total steps: use execution.total_steps if available, otherwise use steps.length
  const totalSteps = (execution && execution.total_steps && execution.total_steps > 0) ? execution.total_steps : (steps.length > 0 ? steps.length : 1);
  const progressPercentage = execution && totalSteps > 0
    ? (((execution.current_step_index ?? 0) + 1) / totalSteps) * 100
    : 0;

  const triggerBadge = getTriggerSourceBadge(execution?.trigger_source);

  // Extract errors from execution for RunOverview
  const executionErrors = execution?.failure_reason
    ? [{
        timestamp: execution.completed_at || execution.started_at || new Date().toISOString(),
        message: execution.failure_reason,
        details: execution.failure_type ? { failure_type: execution.failure_type } : undefined
      }]
    : [];

  const runNumber = parseInt(executionId.slice(-1), 16) % 10 + 1; // Simple run number calculation

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* 1️⃣ Top: Run Header (這次執行的一行總結) */}
      {execution && (
        <ExecutionHeader
          execution={execution}
          playbookTitle={playbookMetadata?.title || playbookMetadata?.playbook_code}
          onRetry={execution.status === 'failed' ? () => {
            // TODO: Implement retry
            console.log('Retry execution');
          } : undefined}
          onStop={execution.status === 'running' ? () => {
            // TODO: Implement stop
            console.log('Stop execution');
          } : undefined}
        />
      )}

      {/* Main Content Area */}
      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* 2️⃣ Top: Run Insight & Draft Changes (split left/right) */}
          <div className="flex-shrink-0 border-b bg-white">
            <div className="grid grid-cols-2 gap-0 h-56">
              <div className="border-r p-3 overflow-y-auto">
                <PlaybookRevisionArea
                  playbookCode={execution?.playbook_code}
                  playbookSteps={steps.map(s => ({
                    step_index: s.step_index,
                    step_name: s.step_name || t('unnamed'),
                    description: s.description,
                    agent_type: s.agent_type,
                    used_tools: s.used_tools
                  }))}
                  revisionPatches={[]}
                  aiSummary={execution?.status === 'failed' && execution.failure_reason
                    ? t('thisExecutionFailed', { reason: execution.failure_reason })
                    : undefined}
                  onApplyPatch={(patchId) => {
                    // TODO: Implement apply patch
                    console.log('Apply patch:', patchId);
                  }}
                  onDiscardPatch={(patchId) => {
                    // TODO: Implement discard patch
                    console.log('Discard patch:', patchId);
                  }}
                  onEditPlaybook={() => {
                    // TODO: Navigate to playbook editor
                    console.log('Edit playbook');
                  }}
                />
              </div>
              <div className="p-3 overflow-y-auto">
                <div className="text-xs font-semibold text-gray-900 mb-1.5">{t('revisionDraft')}</div>
                <div className="text-[10px] text-gray-500">{t('aiSuggestedChangesWillAppear')}</div>
              </div>
            </div>
          </div>

          {/* 3️⃣ Bottom: Steps Timeline + Current Step Details OR Workflow Visualization */}
          <div className="flex-1 overflow-hidden bg-gray-50 p-3">
            {workflowData && workflowData.workflow_result && workflowData.handoff_plan ? (
              <div className="h-full overflow-y-auto">
                <WorkflowVisualization
                  workflowResult={workflowData.workflow_result}
                  handoffPlan={workflowData.handoff_plan}
                  executionId={executionId}
                />
              </div>
            ) : (
              <StepTimelineWithDetails
                steps={steps}
                currentStepIndex={currentStepIndex}
                onStepSelect={setCurrentStepIndex}
                currentStepEvents={stepEvents}
                currentStepToolCalls={currentStepToolCalls}
                currentStepCollaborations={currentStepCollaborations}
                executionStatus={execution?.status}
              />
            )}
          </div>
        </div>

        {/* 4️⃣ Right: Playbook Inspector / Conversation */}
        {playbookMetadata?.supports_execution_chat && (
          <div className="w-80 flex-shrink-0 border-l bg-white">
            <ExecutionChatPanel
              executionId={executionId}
              workspaceId={workspaceId}
              apiUrl={apiUrl}
              playbookMetadata={playbookMetadata}
              executionStatus={execution?.status}
              runNumber={execution?.execution_id ? parseInt(execution.execution_id.slice(-4), 16) % 1000 : 1}
              collapsible={true}
              defaultCollapsed={false}
            />
          </div>
        )}
      </div>
    </div>
  );
}
