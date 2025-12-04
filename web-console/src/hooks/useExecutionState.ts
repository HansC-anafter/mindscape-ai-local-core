'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import type { ExecutionStep } from '@/components/execution';

export interface ThinkingStep {
  id: string;
  content: string;
}

export interface ProducedArtifact {
  id: string;
  name: string;
  type: string;
  url?: string;
  createdAt?: string;
}

export interface TreeStep {
  id: string;
  name: string;
  status: 'pending' | 'in_progress' | 'completed' | 'error';
  detail?: string;
  children?: TreeStep[];
}

export interface TimelineEntry {
  id: string;
  timestamp: string;
  summary: string;
  stepCount?: number;
  artifactCount?: number;
  status?: 'completed' | 'in_progress' | 'error';
}

export interface PipelineStage {
  stage: 'intent_extraction' | 'playbook_selection' | 'task_assignment' | 'execution_start' | 'no_action_needed' | 'no_playbook_found' | 'execution_error';
  message: string;
  streaming?: boolean;
}

export interface ExecutionUIState {
  // Train progress bar
  trainSteps: ExecutionStep[];
  overallProgress: number;
  isExecuting: boolean;

  // Thinking context
  thinkingSummary?: string;
  thinkingContext: ThinkingStep[];
  pipelineStage?: PipelineStage | null;

  // Run ID for lifecycle management
  currentRunId: string | null;

  // AI Team members
  aiTeamMembers: Array<{
    id: string;
    name: string;
    name_zh?: string;
    role: string;
    icon: string;
    status: 'pending' | 'in_progress' | 'completed' | 'error';
  }>;

  // Produced artifacts
  producedArtifacts: ProducedArtifact[];

  // Current task
  currentTaskMessage?: string;

  // Error state
  errorMessage?: string;

  // Execution tree (left sidebar)
  executionTree: TreeStep[];

  // Thinking timeline (left sidebar)
  thinkingTimeline: TimelineEntry[];
}

type SSEEvent =
  | { type: 'thinking_start' }
  | { type: 'thinking_step'; step: string }
  | { type: 'execution_plan'; plan: { id?: string; summary?: string; steps: Array<{ id: string; name: string; icon?: string; status: string }>; ai_team_members?: Array<{ pack_id: string; name: string; name_zh?: string; role: string; icon: string }> } }
  | { type: 'pipeline_stage'; run_id: string; stage: string; message: string; metadata?: any }
  | { type: 'run_started'; run_id: string }
  | { type: 'run_completed'; run_id: string }
  | { type: 'run_failed'; run_id: string; error?: string }
  | { type: 'task_update'; event_type: string; task: { id: string; pack_id?: string; status: string } }
  | { type: 'step_start'; stepId: string }
  | { type: 'step_progress'; stepId: string; message: string; progress?: number }
  | { type: 'step_complete'; stepId: string }
  | { type: 'step_error'; stepId: string; message: string }
  | { type: 'artifact_created'; artifact: ProducedArtifact }
  | { type: 'execution_complete'; summary?: { totalSteps: number; totalArtifacts: number; duration?: string } };

const initialState: ExecutionUIState = {
  trainSteps: [],
  overallProgress: 0,
  isExecuting: false,
  thinkingContext: [],
  pipelineStage: null,
  currentRunId: null,
  aiTeamMembers: [],
  producedArtifacts: [],
  executionTree: [],
  thinkingTimeline: [],
};

export function useExecutionState(workspaceId: string, apiUrl: string = '') {
  const [state, setState] = useState<ExecutionUIState>(initialState);
  const eventSourceRef = useRef<EventSource | null>(null);
  const throttleRef = useRef<NodeJS.Timeout | null>(null);
  const pendingThinkingSteps = useRef<string[]>([]);

  // Calculate overall progress based on step statuses
  const calculateProgress = useCallback((steps: ExecutionStep[]): number => {
    if (steps.length === 0) return 0;

    const completed = steps.filter(s => s.status === 'completed').length;
    const inProgress = steps.find(s => s.status === 'in_progress');
    const inProgressWeight = inProgress ? 0.5 : 0;

    return Math.round(((completed + inProgressWeight) / steps.length) * 100);
  }, []);

  // Throttled thinking step handler (100ms)
  const addThinkingStep = useCallback((step: string) => {
    pendingThinkingSteps.current.push(step);

    if (throttleRef.current) return;

    throttleRef.current = setTimeout(() => {
      const steps = pendingThinkingSteps.current;
      pendingThinkingSteps.current = [];
      throttleRef.current = null;

      setState(prev => ({
        ...prev,
        thinkingContext: [
          ...prev.thinkingContext,
          ...steps.map((content, idx) => ({
            id: `thinking-${Date.now()}-${idx}`,
            content,
          })),
        ],
      }));
    }, 100);
  }, []);

  // Handle SSE event
  const handleEvent = useCallback((event: SSEEvent) => {
    switch (event.type) {
      case 'thinking_start':
        setState(prev => ({
          ...prev,
          trainSteps: [],
          thinkingContext: [],
          thinkingSummary: undefined,
          producedArtifacts: [],
          overallProgress: 0,
          isExecuting: true,
          errorMessage: undefined,
        }));
        break;

      case 'thinking_step':
        addThinkingStep(event.step);
        break;

      case 'execution_plan':
        if (process.env.NODE_ENV === 'development') {
          console.log('[useExecutionState] Processing execution_plan event:', {
            plan_id: event.plan.id,
            plan_summary: event.plan.summary,
            steps_count: event.plan.steps.length,
            steps: event.plan.steps
          });
        }
        setState(prev => {
          const newRunId = event.plan.id || `plan-${Date.now()}`;

          const newSteps: ExecutionStep[] = event.plan.steps.map(s => ({
            id: s.id,
            name: s.name,
            icon: s.icon || '📋',
            status: (s.status as ExecutionStep['status']) || 'pending',
          }));

          const treeSteps: TreeStep[] = event.plan.steps.map(s => ({
            id: s.id,
            name: s.name,
            status: (s.status as TreeStep['status']) || 'pending',
          }));

          if (process.env.NODE_ENV === 'development') {
            console.log('[useExecutionState] Created executionTree with', treeSteps.length, 'steps:', treeSteps);
          }

          const newTimelineEntry: TimelineEntry = {
            id: `plan-${Date.now()}`,
            timestamp: new Date().toISOString(),
            summary: event.plan.summary || `執行計畫：${event.plan.steps.length} 個步驟`,
            stepCount: event.plan.steps.length,
            status: 'in_progress',
          };

          const aiTeamMembers = (event.plan.ai_team_members || []).map((m: any) => ({
            id: m.pack_id || m.id,
            name: m.name || m.pack_id,
            name_zh: m.name_zh,
            role: m.role || '',
            icon: m.icon || '🤖',
            status: 'pending' as const
          }));

          if (process.env.NODE_ENV === 'development') {
            console.log('[useExecutionState] Received ai_team_members:', event.plan.ai_team_members, 'mapped to:', aiTeamMembers);
          }

          const newState = {
            ...prev,
            currentRunId: newRunId,
            pipelineStage: null,
            aiTeamMembers: aiTeamMembers,
            trainSteps: newSteps,
            thinkingSummary: event.plan.summary,
            overallProgress: calculateProgress(newSteps),
            executionTree: treeSteps,
            thinkingTimeline: [newTimelineEntry, ...prev.thinkingTimeline].slice(0, 10),
          };

          if (process.env.NODE_ENV === 'development') {
            console.log('[useExecutionState] Updated state with executionTree:', newState.executionTree, 'runId:', newRunId);
          }

          return newState;
        });
        break;

      case 'pipeline_stage':
        setState(prev => {
          if (event.run_id !== prev.currentRunId && prev.currentRunId !== null) {
            if (process.env.NODE_ENV === 'development') {
              console.warn(`[useExecutionState] Ignoring pipeline_stage event with mismatched run_id: ${event.run_id} (current: ${prev.currentRunId})`);
            }
            return prev;
          }

          let updatedMembers = prev.aiTeamMembers;
          if (event.metadata?.agent_members && Array.isArray(event.metadata.agent_members)) {
            updatedMembers = prev.aiTeamMembers.map(member =>
              event.metadata.agent_members.includes(member.id)
                ? { ...member, status: 'in_progress' as const }
                : member
            );
          }

          return {
            ...prev,
            pipelineStage: {
              stage: event.stage as PipelineStage['stage'],
              message: event.message,
              streaming: true
            },
            aiTeamMembers: updatedMembers
          };
        });
        break;

      case 'task_update':
        setState(prev => {
          if (!event.task.pack_id) return prev;

          const mapTaskStatusToMemberStatus = (taskStatus: string): 'pending' | 'in_progress' | 'completed' | 'error' => {
            if (taskStatus === 'SUCCEEDED' || taskStatus === 'succeeded') return 'completed';
            if (taskStatus === 'FAILED' || taskStatus === 'failed') return 'error';
            if (taskStatus === 'RUNNING' || taskStatus === 'running') return 'in_progress';
            return 'pending';
          };

          return {
            ...prev,
            aiTeamMembers: prev.aiTeamMembers.map(member =>
              member.id === event.task.pack_id
                ? { ...member, status: mapTaskStatusToMemberStatus(event.task.status) }
                : member
            )
          };
        });
        break;

      case 'run_started':
        setState(prev => ({
          ...prev,
          currentRunId: event.run_id,
          pipelineStage: null,
          aiTeamMembers: [],
        }));
        break;

      case 'run_completed':
        setState(prev => {
          if (event.run_id === prev.currentRunId) {
            return {
              ...prev,
              pipelineStage: {
                stage: 'execution_start',
                message: '執行完成',
                streaming: false
              }
            };
          }
          return prev;
        });
        break;

      case 'run_failed':
        setState(prev => {
          if (event.run_id === prev.currentRunId) {
            return {
              ...prev,
              pipelineStage: {
                stage: 'execution_error',
                message: event.error || '執行失敗',
                streaming: false
              }
            };
          }
          return prev;
        });
        break;

      case 'step_start':
        setState(prev => {
          const newSteps = prev.trainSteps.map(s =>
            s.id === event.stepId ? { ...s, status: 'in_progress' as const } : s
          );
          const newTree = prev.executionTree.map(s =>
            s.id === event.stepId ? { ...s, status: 'in_progress' as const } : s
          );
          return {
            ...prev,
            trainSteps: newSteps,
            executionTree: newTree,
            overallProgress: calculateProgress(newSteps),
          };
        });
        break;

      case 'step_progress':
        setState(prev => {
          const newSteps = prev.trainSteps.map(s =>
            s.id === event.stepId
              ? { ...s, detail: event.message, status: 'in_progress' as const }
              : s
          );
          const newTree = prev.executionTree.map(s =>
            s.id === event.stepId
              ? { ...s, detail: event.message, status: 'in_progress' as const }
              : s
          );
          return {
            ...prev,
            trainSteps: newSteps,
            executionTree: newTree,
            currentTaskMessage: event.message,
            overallProgress: calculateProgress(newSteps),
          };
        });
        break;

      case 'step_complete':
        setState(prev => {
          const newSteps = prev.trainSteps.map(s =>
            s.id === event.stepId
              ? { ...s, status: 'completed' as const, detail: undefined }
              : s
          );
          const newTree = prev.executionTree.map(s =>
            s.id === event.stepId
              ? { ...s, status: 'completed' as const, detail: undefined }
              : s
          );
          return {
            ...prev,
            trainSteps: newSteps,
            executionTree: newTree,
            overallProgress: calculateProgress(newSteps),
          };
        });
        break;

      case 'step_error':
        setState(prev => {
          const newSteps = prev.trainSteps.map(s =>
            s.id === event.stepId
              ? { ...s, status: 'error' as const, detail: event.message }
              : s
          );
          const newTree = prev.executionTree.map(s =>
            s.id === event.stepId
              ? { ...s, status: 'error' as const, detail: event.message }
              : s
          );
          return {
            ...prev,
            trainSteps: newSteps,
            executionTree: newTree,
            errorMessage: event.message,
          };
        });
        break;

      case 'artifact_created':
        setState(prev => {
          // Update timeline with artifact count
          const updatedTimeline = prev.thinkingTimeline.map((entry, idx) =>
            idx === 0
              ? { ...entry, artifactCount: (entry.artifactCount || 0) + 1 }
              : entry
          );
          return {
            ...prev,
            producedArtifacts: [...prev.producedArtifacts, event.artifact],
            thinkingTimeline: updatedTimeline,
          };
        });
        break;

      case 'execution_complete':
        setState(prev => {
          // Mark latest timeline entry as completed
          const updatedTimeline = prev.thinkingTimeline.map((entry, idx) =>
            idx === 0 ? { ...entry, status: 'completed' as const } : entry
          );
          return {
            ...prev,
            overallProgress: 100,
            isExecuting: false,
            currentTaskMessage: undefined,
            thinkingTimeline: updatedTimeline,
          };
        });
        break;
    }
  }, [addThinkingStep, calculateProgress]);

  // Reset state
  const resetState = useCallback(() => {
    setState(initialState);
  }, []);

  // Manual trigger for testing (simulate events)
  const simulateExecution = useCallback((steps: Array<{ id: string; name: string; icon: string }>) => {
    // Simulate thinking_start
    handleEvent({ type: 'thinking_start' });

    // Simulate execution_plan after 500ms
    setTimeout(() => {
      handleEvent({
        type: 'execution_plan',
        plan: {
          summary: `本次執行：${steps.length} 個步驟`,
          steps: steps.map(s => ({ ...s, status: 'pending' })),
        },
      });
    }, 500);
  }, [handleEvent]);

  // Listen for custom events from workspace chat
  useEffect(() => {
    const handleExecutionEvent = (e: CustomEvent) => {
      if (e.detail && e.detail.type) {
        handleEvent(e.detail as SSEEvent);
      }
    };

    window.addEventListener('execution-event', handleExecutionEvent as EventListener);
    return () => {
      window.removeEventListener('execution-event', handleExecutionEvent as EventListener);
    };
  }, [handleEvent]);

  // Load execution state from backend on mount
  useEffect(() => {
    if (!workspaceId || !apiUrl) return;

    const loadExecutionState = async () => {
      try {
        // Get latest execution plan events
        const eventsResponse = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/events?event_types=execution_plan&limit=10`
        );

        if (!eventsResponse.ok) {
          console.warn('[useExecutionState] Failed to load execution plan events');
          return;
        }

        const eventsData = await eventsResponse.json();
        const executionPlanEvents = eventsData.events || [];

        if (executionPlanEvents.length === 0) {
          return;
        }

        // Get the most recent execution plan event
        const latestPlanEvent = executionPlanEvents[0];
        const planPayload = latestPlanEvent.payload;

        if (!planPayload || !planPayload.steps) {
          return;
        }

        // Restore execution tree from the plan
        const treeSteps: TreeStep[] = (planPayload.steps || []).map((s: any) => ({
          id: s.step_id || s.id || `step-${Math.random().toString(36).substr(2, 9)}`,
          name: s.intent || s.name || 'Unknown Step',
          status: (s.status as TreeStep['status']) || 'pending',
        }));

        // Restore train steps
        const trainSteps: ExecutionStep[] = (planPayload.steps || []).map((s: any) => ({
          id: s.step_id || s.id || `step-${Math.random().toString(36).substr(2, 9)}`,
          name: s.intent || s.name || 'Unknown Step',
          icon: s.artifacts?.[0] === 'pptx' ? '📊' :
                s.artifacts?.[0] === 'xlsx' ? '📊' :
                s.artifacts?.[0] === 'docx' ? '📝' : '📋',
          status: (s.status as ExecutionStep['status']) || 'pending',
        }));

        // Create timeline entry
        const timelineEntry: TimelineEntry = {
          id: `plan-${latestPlanEvent.id}`,
          timestamp: latestPlanEvent.timestamp || new Date().toISOString(),
          summary: planPayload.plan_summary || `Execution Plan: ${planPayload.steps?.length || 0} steps`,
          stepCount: planPayload.steps?.length || 0,
          status: 'completed' as const,
        };

        // Check if there's a running execution to determine status
        const executionsResponse = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/executions-with-steps?limit=1&include_steps_for=active`
        );

        let isExecuting = false;
        if (executionsResponse.ok) {
          const execData = await executionsResponse.json();
          const activeExecutions = (execData.executions || []).filter(
            (e: any) => e.status === 'running'
          );
          if (activeExecutions.length > 0) {
            isExecuting = true;
            timelineEntry.status = 'in_progress';

            // Update step statuses from execution steps if available
            const execution = activeExecutions[0];
            if (execution.steps && execution.steps.length > 0) {
              // Update tree steps with actual execution status
              treeSteps.forEach(step => {
                const execStep = execution.steps.find((s: any) =>
                  (s.step_name === step.name || s.id === step.id)
                );
                if (execStep) {
                  step.status = execStep.status === 'running' ? 'in_progress' :
                               execStep.status === 'completed' ? 'completed' :
                               execStep.status === 'failed' ? 'error' : 'pending';
                }
              });

              // Update train steps with actual execution status
              trainSteps.forEach(step => {
                const execStep = execution.steps.find((s: any) =>
                  (s.step_name === step.name || s.id === step.id)
                );
                if (execStep) {
                  step.status = execStep.status === 'running' ? 'in_progress' :
                               execStep.status === 'completed' ? 'completed' :
                               execStep.status === 'failed' ? 'error' : 'pending';
                }
              });
            }
          }
        }

        // Build timeline from all execution plan events
        const timelineEntries: TimelineEntry[] = executionPlanEvents
          .slice(0, 10)
          .map((event: any) => {
            const payload = event.payload || {};
            return {
              id: `plan-${event.id}`,
              timestamp: event.timestamp || new Date().toISOString(),
              summary: payload.plan_summary || `Execution Plan: ${payload.steps?.length || 0} steps`,
              stepCount: payload.steps?.length || 0,
              status: 'completed' as const,
            };
          });

        // Calculate progress
        const completed = trainSteps.filter(s => s.status === 'completed').length;
        const inProgress = trainSteps.find(s => s.status === 'in_progress');
        const inProgressWeight = inProgress ? 0.5 : 0;
        const calculatedProgress = trainSteps.length > 0
          ? Math.round(((completed + inProgressWeight) / trainSteps.length) * 100)
          : 0;

        // Restore state
        setState(prev => ({
          ...prev,
          trainSteps,
          executionTree: treeSteps,
          thinkingTimeline: timelineEntries,
          thinkingSummary: planPayload.plan_summary,
          overallProgress: calculatedProgress,
          isExecuting,
        }));

        if (process.env.NODE_ENV === 'development') {
          console.log('[useExecutionState] Restored execution state from backend:', {
            treeStepsCount: treeSteps.length,
            timelineEntriesCount: timelineEntries.length,
            isExecuting,
          });
        }
      } catch (err) {
        console.error('[useExecutionState] Failed to load execution state:', err);
      }
    };

    loadExecutionState();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, apiUrl]);

  // Cleanup
  useEffect(() => {
    return () => {
      if (throttleRef.current) {
        clearTimeout(throttleRef.current);
      }
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  return {
    ...state,
    resetState,
    simulateExecution,
    handleEvent,
  };
}

export default useExecutionState;

