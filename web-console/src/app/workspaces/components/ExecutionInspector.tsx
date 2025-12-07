'use client';

import React, { useEffect, useState } from 'react';
import { useT } from '@/lib/i18n';
import { useExecutionStream } from '@/hooks/useExecutionStream';
import ExecutionChatPanel from './ExecutionChatPanel';
import ExecutionHeader from './ExecutionHeader';
import StepTimelineWithDetails from './StepTimelineWithDetails';
import PlaybookRevisionArea from './PlaybookRevisionArea';
import WorkflowVisualization from './WorkflowVisualization';
import ConfirmDialog from '@/components/ConfirmDialog';

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
  total_steps?: number;  // Add total_steps field
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
  console.log('[ExecutionInspector] Component rendered with executionId:', executionId, 'last8:', executionId?.slice(-8));
  const t = useT();
  const [execution, setExecution] = useState<ExecutionSession | null>(null);
  
  // Reset execution state when executionId changes
  useEffect(() => {
    setExecution(null);
    setLoading(true);
  }, [executionId]);
  const [steps, setSteps] = useState<ExecutionStep[]>([]);
  // step_index is 1-based (1, 2, 3, ...), so initialize to 1
  const [currentStepIndex, setCurrentStepIndex] = useState<number>(1);
  const [loading, setLoading] = useState(true);
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [collaborations, setCollaborations] = useState<AgentCollaboration[]>([]);
  const [stageResults, setStageResults] = useState<StageResult[]>([]);
  const [playbookMetadata, setPlaybookMetadata] = useState<PlaybookMetadata | null>(null);
  const [playbookStepDefinitions, setPlaybookStepDefinitions] = useState<Array<{
    step_index: number;
    step_name: string;
    description?: string;
    agent_type?: string;
    used_tools?: string[];
  }>>([]);
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
  const [isStopping, setIsStopping] = useState(false);
  const [isReloading, setIsReloading] = useState(false);
  const [isRestarting, setIsRestarting] = useState(false);
  const [showRestartConfirm, setShowRestartConfirm] = useState(false);

  // Load execution details
  useEffect(() => {
    const loadExecution = async () => {
      const currentExecutionId = executionId; // Capture executionId for logging
      console.log('[ExecutionInspector] Loading execution for executionId:', currentExecutionId);

      try {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${currentExecutionId}`
        );
        console.log('[ExecutionInspector] Execution fetch response status:', response.status, 'for executionId:', currentExecutionId);

        if (response.ok) {
          const data = await response.json();
          console.log('[ExecutionInspector] Loaded execution data:', {
            executionId: data.execution_id,
            last8: data.execution_id?.slice(-8),
            status: data.status,
            currentExecutionId
          });

          // Verify the loaded execution matches the requested executionId
          if (data.execution_id !== currentExecutionId) {
            console.error('[ExecutionInspector] ⚠️ Execution ID mismatch!', {
              requested: currentExecutionId,
              received: data.execution_id
            });
          }

          setExecution(data);
          // current_step_index is 0-based, convert to 1-based for display
          const maxStepIndex = data.total_steps || ((data.current_step_index || 0) + 1);
          const stepIndex0Based = data.current_step_index || 0;
          const stepIndex1Based = stepIndex0Based + 1;
          const validStepIndex = Math.min(Math.max(1, stepIndex1Based), maxStepIndex);
          setCurrentStepIndex(validStepIndex);
        } else {
          console.error('[ExecutionInspector] Failed to load execution:', response.status, 'for executionId:', currentExecutionId);
        }
      } catch (err) {
        console.error('[ExecutionInspector] Failed to load execution:', err, 'for executionId:', currentExecutionId);
      } finally {
        setLoading(false);
      }
    };

    if (executionId) {
      loadExecution();
    } else {
      console.log('[ExecutionInspector] No executionId provided, clearing execution state');
      setExecution(null);
      setLoading(false);
    }
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

          // Extract step definitions from playbook if available
          const stepDefs: Array<{
            step_index: number;
            step_name: string;
            description?: string;
            agent_type?: string;
            used_tools?: string[];
          }> = [];

          try {
            // Try to parse steps from various sources
            let playbookSteps: any[] = [];

            // First, try direct steps array in metadata or root
            if (Array.isArray(data.steps)) {
              playbookSteps = data.steps;
            } else if (data.metadata?.steps && Array.isArray(data.metadata.steps)) {
              playbookSteps = data.metadata.steps;
            } else if (data.workflow?.steps && Array.isArray(data.workflow.steps)) {
              playbookSteps = data.workflow.steps;
            } else if (data.sop_content) {
              // sop_content might be JSON string or Markdown text
              // Only try JSON parse if it looks like JSON (starts with { or [)
              const sopStr = typeof data.sop_content === 'string' ? data.sop_content.trim() : String(data.sop_content);
              if (sopStr.startsWith('{') || sopStr.startsWith('[')) {
                try {
                  const parsed = JSON.parse(sopStr);
                  if (parsed.steps && Array.isArray(parsed.steps)) {
                    playbookSteps = parsed.steps;
                  }
                } catch (e) {
                  // sop_content is not JSON, might be Markdown - skip it
                  console.debug('sop_content is not JSON format, skipping:', e);
                }
              } else {
                // sop_content is Markdown or other text format - cannot extract steps from it
                console.debug('sop_content is not JSON format (appears to be text/markdown), skipping step extraction');
              }
            }

            // Extract step information from playbook structure
            playbookSteps.forEach((step: any, index: number) => {
              // Extract description from inputs.text (contains the step instructions)
              let description = '';
              if (step.inputs?.text) {
                // Format: "{{...}}\n\n{{...}}\n\n[Instruction text]"
                // Split by double newlines and find the last part that doesn't contain template variables
                const textParts = step.inputs.text.split('\n\n').map((p: string) => p.trim()).filter((p: string) => p);

                // Find the last part without template variables (usually the instruction)
                for (let i = textParts.length - 1; i >= 0; i--) {
                  const part = textParts[i];
                  if (part && !part.includes('{{') && part.length > 10) {
                    description = part;
                    break;
                  }
                }

                // If no clean part found, use the last part anyway (might have templates but still useful)
                if (!description && textParts.length > 0) {
                  description = textParts[textParts.length - 1];
                }
              }

              // Convert step ID to readable name (e.g., "understand_requirements" -> "Understand Requirements")
              const stepName = step.id
                ? step.id.split('_').map((word: string) =>
                    word.charAt(0).toUpperCase() + word.slice(1)
                  ).join(' ')
                : step.name || step.step_name || `Step ${index + 1}`;

              stepDefs.push({
                step_index: index,
                step_name: stepName,
                description: description || step.description || step.instructions || step.prompt || '',
                agent_type: step.agent_type || step.agent,
                used_tools: step.tool ? [step.tool] : (step.tools || step.used_tools || [])
              });
            });

            if (stepDefs.length > 0) {
              console.log('[ExecutionInspector] Extracted step definitions:', stepDefs.length, 'steps');
              setPlaybookStepDefinitions(stepDefs);
            } else {
              console.debug('[ExecutionInspector] No step definitions extracted. Playbook data structure:', {
                hasSteps: Array.isArray(data.steps),
                hasMetadataSteps: Array.isArray(data.metadata?.steps),
                hasWorkflowSteps: Array.isArray(data.workflow?.steps),
                hasSopContent: !!data.sop_content,
                sopContentType: typeof data.sop_content,
                sopContentPreview: typeof data.sop_content === 'string' ? data.sop_content.substring(0, 50) : 'N/A',
                dataKeys: Object.keys(data),
                metadataKeys: data.metadata ? Object.keys(data.metadata) : []
              });
              // Clear step definitions if none found (will use execution steps as fallback)
              setPlaybookStepDefinitions([]);
            }
          } catch (e) {
            console.warn('Failed to extract step definitions from playbook:', e);
          }
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

    if (execution?.playbook_code) {
      loadPlaybookMetadata();
    }
  }, [execution?.playbook_code, execution?.playbook_version, apiUrl, executionId]);

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
          const uniqueSteps = Array.from(
            new Map(stepsArray.map((step: ExecutionStep) => [step.id, step])).values()
          ) as ExecutionStep[];
          uniqueSteps.sort((a, b) => a.step_index - b.step_index);
          setSteps(uniqueSteps);
          // Debug: Log steps and total_steps
          console.log('[ExecutionInspector] Loaded steps:', uniqueSteps.length, 'steps');
          if (uniqueSteps.length > 0) {
            console.log('[ExecutionInspector] Step total_steps values:', uniqueSteps.map(s => ({ step_index: s.step_index, total_steps: (s as any).total_steps })));
          }
        } else {
          console.error('[ExecutionInspector] Failed to load steps:', stepsResponse.status, stepsResponse.statusText);
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

  // Connect to SSE stream for real-time updates using unified stream manager
  useExecutionStream(
    executionId,
    workspaceId,
    apiUrl,
    (update) => {
      if (update.type === 'execution_update') {
        setExecution(update.execution);
        // current_step_index is 0-based, convert to 1-based for display
        if (update.execution) {
          const maxStepIndex = update.execution.total_steps || ((update.execution.current_step_index || 0) + 1);
          const stepIndex0Based = update.execution.current_step_index || 0;
          const stepIndex1Based = stepIndex0Based + 1;
          const validStepIndex = Math.min(Math.max(1, stepIndex1Based), maxStepIndex);
          setCurrentStepIndex(validStepIndex);
        } else {
          setCurrentStepIndex(1);
        }
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
        // Add to step events if it's the current step (will be handled by useEffect below)
      } else if (update.type === 'tool_call_update') {
        // Add tool call event if it belongs to current step (will be handled by useEffect below)
        setStepEvents(prev => {
          // Check if event already exists to avoid duplicates
          const exists = prev.some(e => e.id === update.tool_call?.id && e.type === 'tool');
          if (exists) {
            return prev;
          }
          const currentStep = steps.find(s => s.step_index === currentStepIndex);
          if (update.tool_call && currentStep && update.tool_call.step_id === currentStep.id) {
            return [...prev, {
              id: update.tool_call.id,
              type: 'tool',
              timestamp: new Date(),
              tool: update.tool_call.tool_name,
              content: `Tool: ${update.tool_call.tool_name} completed, ${update.tool_call.summary || 'execution completed'}`
            }];
          }
          return prev;
        });
      } else if (update.type === 'collaboration_update') {
        // Add collaboration event if it belongs to current step (will be handled by useEffect below)
        setStepEvents(prev => {
          // Check if event already exists to avoid duplicates
          const exists = prev.some(e => e.id === update.collaboration?.id && e.type === 'collaboration');
          if (exists) {
            return prev;
          }
          const currentStep = steps.find(s => s.step_index === currentStepIndex);
          if (update.collaboration && currentStep && update.collaboration.step_id === currentStep.id) {
            return [...prev, {
              id: update.collaboration.id,
              type: 'collaboration',
              timestamp: new Date(),
              agent: update.collaboration.participants?.[0] || 'Agent',
              content: `Collaboration: ${update.collaboration.topic || 'Agent discussion'}`
            }];
          }
          return prev;
        });
      } else if (update.type === 'execution_completed') {
        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
      }
    }
  );

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
    if (step.status === 'completed') return 'text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/30 border-green-200 dark:border-green-700';
    if (step.status === 'running') return 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30 border-blue-200 dark:border-blue-700';
    if (step.status === 'waiting_confirmation') return 'text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900/30 border-yellow-200 dark:border-yellow-700';
    if (step.status === 'failed') return 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/30 border-red-200 dark:border-red-700';
    return 'text-gray-400 dark:text-gray-500 bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700';
  };

  const getTriggerSourceBadge = (source?: string) => {
    switch (source) {
      case 'auto':
        return { label: t('triggerSourceAuto'), color: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-700' };
      case 'suggestion':
        return { label: t('triggerSourceSuggested'), color: 'bg-gray-100 dark:bg-gray-800/30 text-gray-700 dark:text-gray-300 border-gray-400 dark:border-gray-600' };
      case 'manual':
        return { label: t('triggerSourceManual'), color: 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600' };
      default:
        return { label: t('triggerSourceUnknown'), color: 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600' };
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
          // current_step_index is 0-based, convert to 1-based for display
          setCurrentStepIndex((execData.current_step_index || 0) + 1);
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
          // current_step_index is 0-based, convert to 1-based for display
          setCurrentStepIndex((execData.current_step_index || 0) + 1);
        }
      }
    } catch (err) {
      console.error('Failed to reject step:', err);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 dark:border-blue-500"></div>
      </div>
    );
  }

  // Calculate total steps:
  // Always use execution.total_steps as the authoritative source
  // step's total_steps might be incorrect or outdated
  // Fallback to steps.length only if execution.total_steps is not available
  const totalSteps = (execution && execution.total_steps && execution.total_steps > 0)
    ? execution.total_steps
    : (steps.length > 0 ? steps.length : 1);

  // Debug: Log totalSteps calculation
  if (process.env.NODE_ENV === 'development' && steps.length > 0) {
    console.log('[ExecutionInspector] totalSteps calculation:', {
      execution_total_steps: execution?.total_steps,
      steps_length: steps.length,
      final_totalSteps: totalSteps
    });
  }
  // current_step_index is 0-based, convert to 1-based for display
  const currentStepIndexValid = execution
    ? Math.min(Math.max(1, (execution.current_step_index ?? 0) + 1), Math.max(1, totalSteps))
    : 1;
  const progressPercentage = execution && totalSteps > 0
    ? (currentStepIndexValid / totalSteps) * 100
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
    <div className="h-full flex flex-col bg-gray-50 dark:bg-gray-950">
      {/* Execution Header */}
      {execution && (
        <ExecutionHeader
          execution={execution}
          playbookTitle={playbookMetadata?.title || playbookMetadata?.playbook_code}
          onRetry={execution.status === 'failed' ? () => {
            // TODO: Implement retry functionality
          } : undefined}
          isStopping={isStopping}
          isReloading={isReloading}
          isRestarting={isRestarting}
          playbookCode={execution?.playbook_code}
          apiUrl={apiUrl}
          workspaceId={workspaceId}
          onStop={execution.status === 'running' ? async () => {
            if (isStopping) return;
            setIsStopping(true);
            try {
              const response = await fetch(
                `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/cancel`,
                {
                  method: 'POST',
                  headers: {
                    'Content-Type': 'application/json',
                  },
                }
              );
              if (response.ok) {
                const result = await response.json();
                // Reload execution to get updated status
                const execResponse = await fetch(
                  `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}`
                );
                if (execResponse.ok) {
                  const execData = await execResponse.json();
                  setExecution(execData);
                }
              } else {
                const errorData = await response.json().catch(() => ({ detail: 'Failed to cancel execution' }));
                console.error('Failed to cancel execution:', errorData);
                alert(errorData.detail || 'Failed to cancel execution');
              }
            } catch (error) {
              console.error('Error cancelling execution:', error);
              alert('Failed to cancel execution. Please try again.');
            } finally {
              setIsStopping(false);
            }
          } : undefined}
          onReloadPlaybook={async () => {
            if (!execution?.playbook_code) return;
            setIsReloading(true);
            try {
              const response = await fetch(
                `${apiUrl}/api/v1/playbooks/${execution.playbook_code}/reload?locale=zh-TW`,
                { method: 'POST' }
              );
              if (response.ok) {
                window.dispatchEvent(new CustomEvent('playbook-reloaded', {
                  detail: { playbookCode: execution.playbook_code }
                }));
                // Reload the page to reflect changes
                window.location.reload();
              } else {
                const error = await response.json().catch(() => ({ detail: 'Failed to reload playbook' }));
                alert(error.detail || 'Failed to reload playbook');
              }
            } catch (error) {
              console.error('Error reloading playbook:', error);
              alert('Failed to reload playbook. Please try again.');
            } finally {
              setIsReloading(false);
            }
          }}
          onRestartExecution={async () => {
            if (!execution?.playbook_code || !executionId) return;

            // Show confirmation dialog
            setShowRestartConfirm(true);
          }}
        />
      )}

      {/* Main Content Area */}
      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Run Insight & Draft Changes */}
          <div className="flex-shrink-0 border-b dark:border-gray-700 bg-white dark:bg-gray-900">
            <div className="grid grid-cols-2 gap-0 h-56">
              <div className="border-r dark:border-gray-700 p-3 overflow-y-auto">
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
                    // TODO: Implement apply patch functionality
                  }}
                  onDiscardPatch={(patchId) => {
                    // TODO: Implement discard patch functionality
                  }}
                  onEditPlaybook={() => {
                    // TODO: Navigate to playbook editor
                  }}
                  onReloadPlaybook={async () => {
                    if (!execution?.playbook_code) return;
                    setIsReloading(true);
                    try {
                      const response = await fetch(
                        `${apiUrl}/api/v1/playbooks/${execution.playbook_code}/reload?locale=zh-TW`,
                        { method: 'POST' }
                      );
                      if (response.ok) {
                        window.dispatchEvent(new CustomEvent('playbook-reloaded', {
                          detail: { playbookCode: execution.playbook_code }
                        }));
                        // Reload the page to reflect changes
                        window.location.reload();
                      } else {
                        const error = await response.json().catch(() => ({ detail: 'Failed to reload playbook' }));
                        alert(error.detail || 'Failed to reload playbook');
                      }
                    } catch (error) {
                      console.error('Error reloading playbook:', error);
                      alert('Failed to reload playbook. Please try again.');
                    } finally {
                      setIsReloading(false);
                    }
                  }}
                  onRestartExecution={async () => {
                    if (!execution?.playbook_code || !executionId) return;
                    setIsRestarting(true);
                    try {
                      // First cancel current execution if running
                      if (execution.status === 'running') {
                        await fetch(
                          `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/cancel`,
                          { method: 'POST' }
                        );
                      }

                      // Start new execution with same playbook
                      const response = await fetch(
                        `${apiUrl}/api/v1/workspaces/${workspaceId}/playbooks/${execution.playbook_code}/execute`,
                        {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({
                            inputs: {},
                            execution_mode: 'async'
                          })
                        }
                      );

                      if (response.ok) {
                        const result = await response.json();
                        const newExecutionId = result.execution_id || result.result?.execution_id;
                        if (newExecutionId) {
                          // Navigate to new execution
                          window.location.href = `/workspaces/${workspaceId}/executions/${newExecutionId}`;
                        } else {
                          alert('Execution started but failed to get execution ID');
                        }
                      } else {
                        const error = await response.json().catch(() => ({ detail: 'Failed to restart execution' }));
                        alert(error.detail || 'Failed to restart execution');
                      }
                    } catch (error) {
                      console.error('Error restarting execution:', error);
                      alert('Failed to restart execution. Please try again.');
                    } finally {
                      setIsRestarting(false);
                    }
                  }}
                  onStopExecution={async () => {
                    if (isStopping) return;
                    setIsStopping(true);
                    try {
                      const response = await fetch(
                        `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/cancel`,
                        {
                          method: 'POST',
                          headers: {
                            'Content-Type': 'application/json',
                          },
                        }
                      );
                      if (response.ok) {
                        const result = await response.json();
                        // Reload execution to get updated status
                        const execResponse = await fetch(
                          `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}`
                        );
                        if (execResponse.ok) {
                          const execData = await execResponse.json();
                          setExecution(execData);
                        }
                      } else {
                        const errorData = await response.json().catch(() => ({ detail: 'Failed to cancel execution' }));
                        console.error('Failed to cancel execution:', errorData);
                        alert(errorData.detail || 'Failed to cancel execution');
                      }
                    } catch (error) {
                      console.error('Error cancelling execution:', error);
                      alert('Failed to cancel execution. Please try again.');
                    } finally {
                      setIsStopping(false);
                    }
                  }}
                  isReloading={isReloading}
                  isRestarting={isRestarting}
                  isStopping={isStopping}
                  executionStatus={execution?.status}
                  apiUrl={apiUrl}
                  workspaceId={workspaceId}
                />
              </div>
              <div className="p-3 overflow-y-auto">
                <div className="text-xs font-semibold text-gray-900 dark:text-gray-100 mb-1.5">{t('revisionDraft')}</div>
                <div className="text-[10px] text-gray-500 dark:text-gray-300">{t('aiSuggestedChangesWillAppear')}</div>
              </div>
            </div>
          </div>

          {/* Steps Timeline & Current Step Details or Workflow Visualization */}
          <div className="flex-1 overflow-hidden bg-gray-50 dark:bg-gray-950 p-3">
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
                totalSteps={totalSteps}
                playbookSteps={playbookStepDefinitions.length > 0
                  ? playbookStepDefinitions
                  : (steps.length > 0 ? steps.map(s => ({
                      step_index: s.step_index,
                      step_name: s.step_name || s.id || `Step ${s.step_index + 1}`,
                      description: s.description || s.log_summary || '',
                      agent_type: s.agent_type,
                      used_tools: s.used_tools || []
                    })) : [])}
              />
            )}
          </div>
        </div>

        {/* 4️⃣ Right: Playbook Inspector / Conversation */}
        {playbookMetadata?.supports_execution_chat && (
          <div className="w-80 flex-shrink-0 border-l dark:border-gray-700 bg-white dark:bg-gray-900">
            <ExecutionChatPanel
              key={executionId}
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

      {/* Restart Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showRestartConfirm}
        onClose={() => setShowRestartConfirm(false)}
        onConfirm={() => {
          setShowRestartConfirm(false);
          if (execution?.playbook_code && executionId) {
            setIsRestarting(true);

            try {
              // Immediately navigate back to workspace to avoid long wait
              // Store restart info in sessionStorage for progress indicator
              const restartInfo = {
                playbook_code: execution.playbook_code,
                workspace_id: workspaceId,
                timestamp: Date.now()
              };
              sessionStorage.setItem('pending_restart', JSON.stringify(restartInfo));

              // Store flag to force refresh executions on workspace page load
              sessionStorage.setItem('force_refresh_executions', 'true');

              // Navigate to workspace immediately
              window.location.href = `/workspaces/${workspaceId}`;

              // Start new execution in background (don't wait for response)
              // Cancel current execution if running (fire and forget)
              if (execution.status === 'running') {
                fetch(
                  `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/cancel`,
                  { method: 'POST' }
                ).catch(err => console.warn('Failed to cancel execution:', err));
              }

              // Start new execution
              // Remove execution_id from inputs to ensure a new execution is created
              const inputs = { ...(execution.execution_context || {}) };
              delete inputs.execution_id;
              delete inputs.status;
              delete inputs.current_step_index;

              fetch(
                `${apiUrl}/api/v1/workspaces/${workspaceId}/playbooks/${execution.playbook_code}/execute`,
                {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    inputs: inputs,
                    execution_mode: 'async'
                  })
                }
              )
                .then(async (response) => {
                  if (response.ok) {
                    const result = await response.json();
                    const newExecutionId = result.execution_id || result.result?.execution_id;
                    if (newExecutionId) {
                      // Store new execution ID in sessionStorage for notification
                      sessionStorage.setItem('restart_success', JSON.stringify({
                        execution_id: newExecutionId,
                        workspace_id: workspaceId,
                        playbook_code: execution.playbook_code,
                        timestamp: Date.now()
                      }));
                      // Clear restart info
                      sessionStorage.removeItem('pending_restart');
                      // Trigger custom event to show notification in workspace
                      window.dispatchEvent(new CustomEvent('execution-restarted', {
                        detail: {
                          execution_id: newExecutionId,
                          workspace_id: workspaceId,
                          playbook_code: execution.playbook_code
                        }
                      }));
                    } else {
                      sessionStorage.removeItem('pending_restart');
                      console.error('Execution started but failed to get execution ID');
                      // Show error notification
                      window.dispatchEvent(new CustomEvent('execution-restart-error', {
                        detail: { message: '執行已啟動但無法獲取執行 ID' }
                      }));
                    }
                  } else {
                    sessionStorage.removeItem('pending_restart');
                    const error = await response.json().catch(() => ({ detail: 'Failed to restart execution' }));
                    // Show error notification
                    window.dispatchEvent(new CustomEvent('execution-restart-error', {
                      detail: { message: error.detail || '重啟執行失敗' }
                    }));
                  }
                })
                .catch((error) => {
                  sessionStorage.removeItem('pending_restart');
                  console.error('Error restarting execution:', error);
                  // Show error notification
                  window.dispatchEvent(new CustomEvent('execution-restart-error', {
                    detail: { message: '重啟執行失敗，請重試' }
                  }));
                });
            } catch (error) {
              sessionStorage.removeItem('pending_restart');
              console.error('Error restarting execution:', error);
              alert('Failed to restart execution. Please try again.');
            } finally {
              setIsRestarting(false);
            }
          }
        }}
        title={t('confirmRestartExecution') || '確認重啟執行'}
        message={t('confirmRestartExecution') || '確定要重啟此執行嗎？這將創建一個新的執行並取消當前執行。'}
        confirmText={t('accept') || '確定'}
        cancelText={t('cancel') || '取消'}
        confirmButtonClassName="bg-blue-600 hover:bg-blue-700"
      />
    </div>
  );
}
