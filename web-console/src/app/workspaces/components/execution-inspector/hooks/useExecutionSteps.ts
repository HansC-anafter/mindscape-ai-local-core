import { useState, useEffect, useCallback, useRef } from 'react';
import { useExecutionStream } from '@/hooks/useExecutionStream';
import type {
  ExecutionStep,
  ToolCall,
  AgentCollaboration,
  StageResult,
  StepEvent,
} from '../types/execution';
import { convertStepIndexTo1Based } from '../utils/execution-inspector';

export interface UseExecutionStepsResult {
  steps: ExecutionStep[];
  toolCalls: ToolCall[];
  collaborations: AgentCollaboration[];
  stageResults: StageResult[];
  stepEvents: StepEvent[];
  loading: boolean;
  error: Error | null;
}

export function useExecutionSteps(
  executionId: string | null,
  workspaceId: string,
  apiUrl: string,
  currentStepIndex: number,
  executionStatus?: string
): UseExecutionStepsResult {
  const [steps, setSteps] = useState<ExecutionStep[]>([]);
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [collaborations, setCollaborations] = useState<AgentCollaboration[]>([]);
  const [stageResults, setStageResults] = useState<StageResult[]>([]);
  const [stepEvents, setStepEvents] = useState<StepEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  // Use refs to track current values without causing re-renders
  const stepsRef = useRef(steps);
  const currentStepIndexRef = useRef(currentStepIndex);

  useEffect(() => {
    stepsRef.current = steps;
  }, [steps]);

  useEffect(() => {
    currentStepIndexRef.current = currentStepIndex;
  }, [currentStepIndex]);

  // Load step details
  useEffect(() => {
    // Reset state immediately when executionId changes
    if (!executionId) {
      setSteps([]);
      setToolCalls([]);
      setCollaborations([]);
      setStageResults([]);
      setStepEvents([]);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;

    const loadStepDetails = async () => {
      try {
        setError(null);
        setLoading(true);

        // Load steps
        const stepsResponse = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/steps`
        );

        // Check if cancelled or executionId changed
        if (cancelled || !executionId) {
          return;
        }

        if (stepsResponse.ok) {
          const stepsData = await stepsResponse.json();
          const stepsArray = stepsData.steps || [];

          // Group steps by step_index and step_name, then select the latest status for each
          // Priority: completed > running > failed > pending
          const stepsByIndex = new Map<number, ExecutionStep>();
          const statusPriority: Record<string, number> = {
            'completed': 4,
            'running': 3,
            'failed': 2,
            'error': 2,
            'pending': 1,
          };

          for (const step of stepsArray) {
            const stepIndex = step.step_index;
            const existing = stepsByIndex.get(stepIndex);

            if (!existing) {
              stepsByIndex.set(stepIndex, step);
            } else {
              // Compare by status priority, then by timestamp (completed_at or started_at)
              const existingPriority = statusPriority[existing.status] || 0;
              const newPriority = statusPriority[step.status] || 0;

              if (newPriority > existingPriority) {
                stepsByIndex.set(stepIndex, step);
              } else if (newPriority === existingPriority) {
                // If same priority, prefer the one with later timestamp
                const existingTime = existing.completed_at || existing.started_at || '';
                const newTime = step.completed_at || step.started_at || '';
                if (newTime > existingTime) {
                  stepsByIndex.set(stepIndex, step);
                }
              }
            }
          }

          const uniqueSteps = Array.from(stepsByIndex.values()) as ExecutionStep[];
          uniqueSteps.sort((a, b) => a.step_index - b.step_index);

          // Check again before setting state
          if (!cancelled && executionId) {
            setSteps(uniqueSteps);
          }
        } else {
          console.error('[useExecutionSteps] Failed to load steps:', stepsResponse.status, stepsResponse.statusText);
        }

        // Load tool calls (optional - endpoint may not exist yet)
        try {
          if (cancelled || !executionId) return;

          const toolCallsResponse = await fetch(
            `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/tool-calls`
          );

          if (cancelled || !executionId) return;

          if (toolCallsResponse.ok) {
            const toolCallsData = await toolCallsResponse.json();
            if (!cancelled && executionId) {
              setToolCalls(toolCallsData.tool_calls || []);
            }
          } else if (toolCallsResponse.status === 404) {
            if (!cancelled && executionId) {
              setToolCalls([]);
            }
          }
        } catch (err) {
          if (!cancelled && executionId) {
            setToolCalls([]);
          }
        }

        // Load stage results (optional - endpoint may not exist yet)
        try {
          if (cancelled || !executionId) return;

          const stageResultsResponse = await fetch(
            `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/stage-results`
          );

          if (cancelled || !executionId) return;

          if (stageResultsResponse.ok) {
            const stageResultsData = await stageResultsResponse.json();
            if (!cancelled && executionId) {
              setStageResults(stageResultsData.stage_results || []);
            }
          } else if (stageResultsResponse.status === 404) {
            if (!cancelled && executionId) {
              setStageResults([]);
            }
          }
        } catch (err) {
          if (!cancelled && executionId) {
            setStageResults([]);
          }
        }

        // Load agent collaborations
        try {
          if (cancelled || !executionId) return;

          const eventsResponse = await fetch(
            `${apiUrl}/api/v1/workspaces/${workspaceId}/events?event_types=AGENT_EXECUTION&execution_id=${executionId}&limit=100`
          );

          if (cancelled || !executionId) return;

          if (eventsResponse.ok) {
            const eventsData = await eventsResponse.json();
            const collaborationEvents = (eventsData.events || []).filter(
              (e: any) => e.event_type === 'AGENT_EXECUTION' && e.payload?.is_agent_collaboration
            );
            if (!cancelled && executionId) {
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
          }
        } catch (err) {
          console.warn('[useExecutionSteps] Failed to load agent collaborations:', err);
        }
      } catch (err) {
        const error = err instanceof Error ? err : new Error('Unknown error');
        setError(error);
        console.error('[useExecutionSteps] Failed to load step details:', err);
      } finally {
        if (!cancelled && executionId) {
          setLoading(false);
        }
      }
    };

    loadStepDetails();

    // Cleanup function
    return () => {
      cancelled = true;
    };
  }, [executionId, workspaceId, apiUrl]);

  // Connect to SSE stream for real-time updates
  useExecutionStream(
    executionId,
    workspaceId,
    apiUrl,
    useCallback((update: { type: string; step?: ExecutionStep; tool_call?: ToolCall; collaboration?: AgentCollaboration; [key: string]: any }) => {
      if (update.type === 'step_update' && update.step) {
        setSteps(prev => {
          // Find step by step_index (not id) since same step can have multiple events
          const stepIndex = update.step!.step_index;
          const index = prev.findIndex(s => s.step_index === stepIndex);

          const statusPriority: Record<string, number> = {
            'completed': 4,
            'running': 3,
            'failed': 2,
            'error': 2,
            'pending': 1,
          };

          if (index >= 0) {
            // Update existing step if new status has higher priority
            const existing = prev[index];
            const existingPriority = statusPriority[existing.status] || 0;
            const newPriority = statusPriority[update.step!.status] || 0;

            if (newPriority > existingPriority) {
              const updated = [...prev];
              updated[index] = update.step!;
              return updated.sort((a, b) => a.step_index - b.step_index);
            } else if (newPriority === existingPriority) {
              // Same priority, prefer the one with later timestamp
              const existingTime = existing.completed_at || existing.started_at || '';
              const newTime = update.step!.completed_at || update.step!.started_at || '';
              if (newTime > existingTime) {
                const updated = [...prev];
                updated[index] = update.step!;
                return updated.sort((a, b) => a.step_index - b.step_index);
              }
            }
            return prev;
          } else {
            // Add new step
            const newSteps = [...prev, update.step!];
            return newSteps.sort((a, b) => a.step_index - b.step_index);
          }
        });
      } else if (update.type === 'tool_call_update' && update.tool_call) {
        const toolCall = update.tool_call;
        setToolCalls(prev => {
          const index = prev.findIndex(tc => tc.id === toolCall.id);
          if (index >= 0) {
            const updated = [...prev];
            updated[index] = toolCall;
            return updated;
          } else {
            return [...prev, toolCall];
          }
        });

        // Add to step events if it belongs to current step
        setStepEvents(prev => {
          const exists = prev.some(e => e.id === toolCall.id && e.type === 'tool');
          if (exists) {
            return prev;
          }
          const currentStep = stepsRef.current.find(s => s.step_index === currentStepIndexRef.current);
          if (currentStep && toolCall.step_id === currentStep.id) {
            return [...prev, {
              id: toolCall.id,
              type: 'tool' as const,
              timestamp: new Date(),
              tool: toolCall.tool_name,
              content: `Tool: ${toolCall.tool_name} completed, execution completed`
            }];
          }
          return prev;
        });
      } else if (update.type === 'collaboration_update' && update.collaboration) {
        setCollaborations(prev => {
          const index = prev.findIndex(c => c.id === update.collaboration!.id);
          if (index >= 0) {
            const updated = [...prev];
            updated[index] = update.collaboration!;
            return updated;
          } else {
            return [...prev, update.collaboration!];
          }
        });

        // Add to step events if it belongs to current step
        setStepEvents(prev => {
          const exists = prev.some(e => e.id === update.collaboration!.id && e.type === 'collaboration');
          if (exists) {
            return prev;
          }
          const currentStep = stepsRef.current.find(s => s.step_index === currentStepIndexRef.current);
          if (currentStep && update.collaboration!.step_id === currentStep.id) {
            return [...prev, {
              id: update.collaboration!.id,
              type: 'collaboration' as const,
              timestamp: new Date(),
              agent: update.collaboration!.participants?.[0] || 'Agent',
              content: `Collaboration: ${update.collaboration!.topic || 'Agent discussion'}`
            }];
          }
          return prev;
        });
      } else if (update.type === 'execution_completed') {
        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
      }
    }, [])
  );

  // Filter step events for current step only
  useEffect(() => {
    const currentStep = steps.find(s => s.step_index === currentStepIndex);
    if (currentStep) {
      setStepEvents(prev => prev.filter(e => {
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
  }, [currentStepIndex, steps, toolCalls, collaborations]);

  return {
    steps,
    toolCalls,
    collaborations,
    stageResults,
    stepEvents,
    loading,
    error,
  };
}
