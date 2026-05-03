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
  trainSteps: ExecutionStep[];
  overallProgress: number;
  isExecuting: boolean;

  thinkingSummary?: string;
  thinkingContext: ThinkingStep[];
  pipelineStage?: PipelineStage | null;

  currentRunId: string | null;

  aiTeamMembers: Array<{
    id: string;
    name: string;
    name_zh?: string;
    role: string;
    icon: string;
    status: 'pending' | 'in_progress' | 'completed' | 'error';
  }>;

  producedArtifacts: ProducedArtifact[];

  currentTaskMessage?: string;

  errorMessage?: string;

  executionTree: TreeStep[];

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
  const throttleRef = useRef<NodeJS.Timeout | null>(null);
  const pendingThinkingSteps = useRef<string[]>([]);

  const calculateProgress = useCallback((steps: ExecutionStep[]): number => {
    if (steps.length === 0) return 0;

    const completed = steps.filter(s => s.status === 'completed').length;
    const inProgress = steps.find(s => s.status === 'in_progress');
    const inProgressWeight = inProgress ? 0.5 : 0;

    return Math.round(((completed + inProgressWeight) / steps.length) * 100);
  }, []);

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
        setState(prev => {
          const newRunId = event.plan.id || `plan-${Date.now()}`;

          const isNewRun = newRunId !== prev.currentRunId;

          const newSteps: ExecutionStep[] = event.plan.steps.map(s => ({
            id: s.id,
            name: s.name,
            icon: s.icon || 'DOC',
            status: (s.status as ExecutionStep['status']) || 'pending',
          }));

          const treeSteps: TreeStep[] = event.plan.steps.map(s => ({
            id: s.id,
            name: s.name,
            status: (s.status as TreeStep['status']) || 'pending',
          }));

          const newTimelineEntry: TimelineEntry = {
            id: `plan-${Date.now()}`,
            timestamp: new Date().toISOString(),
            summary: event.plan.summary || `Execution plan: ${event.plan.steps.length} steps`,
            stepCount: event.plan.steps.length,
            status: 'in_progress',
          };

          const aiTeamMembers = (event.plan.ai_team_members && event.plan.ai_team_members.length > 0)
            ? event.plan.ai_team_members.map((m: any) => ({
              id: m.pack_id || m.id,
              name: m.name || m.pack_id,
              name_zh: m.name_zh,
              role: m.role || '',
              icon: m.icon || 'AI',
              status: 'pending' as const
            }))
            : (isNewRun ? [] : prev.aiTeamMembers);

          const newState = {
            ...prev,
            currentRunId: newRunId,
            pipelineStage: isNewRun ? null : prev.pipelineStage,
            aiTeamMembers: aiTeamMembers,
            trainSteps: newSteps,
            thinkingSummary: event.plan.summary,
            overallProgress: calculateProgress(newSteps),
            executionTree: treeSteps,
            thinkingTimeline: isNewRun
              ? [newTimelineEntry, ...prev.thinkingTimeline].slice(0, 10)
              : prev.thinkingTimeline,
          };

          return newState;
        });
        break;

      case 'pipeline_stage':
        setState(prev => {
          if (event.run_id && event.run_id !== prev.currentRunId && prev.currentRunId !== null) {
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
        setState(prev => {
          window.dispatchEvent(new CustomEvent('execution-event', {
            detail: {
              type: 'execution_started',
              data: {
                executionId: event.run_id,
                playbookCode: prev.trainSteps[0]?.name || '',
                runNumber: parseInt(event.run_id.split('-').pop() || '1', 10),
              },
            },
          }));
          return {
            ...prev,
            currentRunId: event.run_id,
            pipelineStage: null,
            aiTeamMembers: [],
          };
        });
        break;

      case 'run_completed':
        setState(prev => {
          if (event.run_id === prev.currentRunId) {
            window.dispatchEvent(new CustomEvent('execution-event', {
              detail: {
                type: 'execution_completed',
                data: {
                  executionId: event.run_id,
                },
              },
            }));
            return {
              ...prev,
              pipelineStage: {
                stage: 'execution_start',
                message: 'Execution completed',
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
            window.dispatchEvent(new CustomEvent('execution-event', {
              detail: {
                type: 'execution_failed',
                data: {
                  executionId: event.run_id,
                  error: event.error,
                },
              },
            }));
            return {
              ...prev,
              pipelineStage: {
                stage: 'execution_error',
                message: event.error || 'Execution failed',
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
          const progress = calculateProgress(newSteps);

          if (prev.currentRunId) {
            window.dispatchEvent(new CustomEvent('execution-event', {
              detail: {
                type: 'execution_concurrent_update',
                data: {
                  playbookCode: prev.trainSteps[0]?.name || '',
                  executions: [{
                    executionId: prev.currentRunId,
                    runNumber: parseInt(prev.currentRunId.split('-').pop() || '1', 10),
                    status: 'running',
                    progress: progress,
                  }],
                },
              },
            }));
          }

          return {
            ...prev,
            trainSteps: newSteps,
            executionTree: newTree,
            currentTaskMessage: event.message,
            overallProgress: progress,
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

  const resetState = useCallback(() => {
    setState(initialState);
  }, []);

  const simulateExecution = useCallback((steps: Array<{ id: string; name: string; icon: string }>) => {
    handleEvent({ type: 'thinking_start' });

    setTimeout(() => {
      handleEvent({
        type: 'execution_plan',
        plan: {
          summary: `This execution: ${steps.length} steps`,
          steps: steps.map(s => ({ ...s, status: 'pending' })),
        },
      });
    }, 500);
  }, [handleEvent]);

  useEffect(() => {
    const handleExecutionEvent = (e: CustomEvent) => {
      if (e.detail && e.detail.type) {
        handleEvent(e.detail as SSEEvent);
      }
    };

    const handleClearPipeline = () => {
      setState(prev => prev.pipelineStage ? { ...prev, pipelineStage: null } : prev);
    };

    window.addEventListener('execution-event', handleExecutionEvent as EventListener);
    window.addEventListener('clear-pipeline-stage', handleClearPipeline as EventListener);
    return () => {
      window.removeEventListener('execution-event', handleExecutionEvent as EventListener);
      window.removeEventListener('clear-pipeline-stage', handleClearPipeline as EventListener);
    };
  }, [handleEvent]);

  useEffect(() => {
    if (!workspaceId || apiUrl == null) return;

    const loadExecutionState = async () => {
      try {
        const eventsResponse = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/events?event_types=execution_plan&limit=10`
        );

        if (!eventsResponse.ok) {
          return;
        }

        const eventsData = await eventsResponse.json();
        const executionPlanEvents = eventsData.events || [];

        if (executionPlanEvents.length === 0) {
          return;
        }

        const latestPlanEvent = executionPlanEvents[0];
        const planPayload = latestPlanEvent.payload;

        if (!planPayload || !planPayload.steps) {
          return;
        }

        const treeSteps: TreeStep[] = (planPayload.steps || []).map((s: any) => ({
          id: s.step_id || s.id || `step-${Math.random().toString(36).substr(2, 9)}`,
          name: s.intent || s.name || 'Unknown Step',
          status: (s.status as TreeStep['status']) || 'pending',
        }));

        const trainSteps: ExecutionStep[] = (planPayload.steps || []).map((s: any) => ({
          id: s.step_id || s.id || `step-${Math.random().toString(36).substr(2, 9)}`,
          name: s.intent || s.name || 'Unknown Step',
          icon: s.artifacts?.[0] === 'pptx' ? 'PPT' :
            s.artifacts?.[0] === 'xlsx' ? 'XLS' :
              s.artifacts?.[0] === 'docx' ? 'DOC' : 'DOC',
          status: (s.status as ExecutionStep['status']) || 'pending',
        }));

        const timelineEntry: TimelineEntry = {
          id: `plan-${latestPlanEvent.id}`,
          timestamp: latestPlanEvent.timestamp || new Date().toISOString(),
          summary: planPayload.plan_summary || `Execution Plan: ${planPayload.steps?.length || 0} steps`,
          stepCount: planPayload.steps?.length || 0,
          status: 'completed' as const,
        };

        const executionsResponse = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/tasks?limit=20&task_type=execution`
        );

        let isExecuting = false;
        const runningPlaybookCodes = new Set<string>();
        const recentPlaybookCodes = new Set<string>();

        if (executionsResponse.ok) {
          const tasksData = await executionsResponse.json();
          const tasks = tasksData.tasks || [];

          const allExecutions = tasks.map((t: any) => ({
            execution_id: t.id,
            status: t.status,
            task: t,
            playbook_code: t.pack_id,
            steps: []
          }));

          const activeExecutions = allExecutions.filter((e: any) =>
            e.status === 'running' || e.status === 'pending' || e.status === 'queued'
          );

          activeExecutions.forEach((execution: any) => {
            const playbookCode = execution.playbook_code || execution.task?.execution_context?.playbook_code;
            if (playbookCode) {
              runningPlaybookCodes.add(playbookCode);
            }
          });

          const recentExecutions = allExecutions
            .filter((e: any) => {
              const playbookCode = e.playbook_code || e.task?.execution_context?.playbook_code;
              return playbookCode && playbookCode !== 'execution_status_query';
            })
            .slice(0, 5);

          recentExecutions.forEach((execution: any) => {
            const playbookCode = execution.playbook_code || execution.task?.execution_context?.playbook_code;
            if (playbookCode) {
              recentPlaybookCodes.add(playbookCode);
            }
          });

          if (activeExecutions.length > 0) {
            isExecuting = true;
            timelineEntry.status = 'in_progress';

            const execution = activeExecutions[0];
            if (execution.steps && execution.steps.length > 0) {
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

        const completed = trainSteps.filter(s => s.status === 'completed').length;
        const inProgress = trainSteps.find(s => s.status === 'in_progress');
        const inProgressWeight = inProgress ? 0.5 : 0;
        const calculatedProgress = trainSteps.length > 0
          ? Math.round(((completed + inProgressWeight) / trainSteps.length) * 100)
          : 0;

        let aiTeamMembers = (planPayload.ai_team_members && planPayload.ai_team_members.length > 0)
          ? planPayload.ai_team_members.map((m: any) => ({
            id: m.pack_id || m.id,
            name: m.name || m.pack_id,
            name_zh: m.name_zh,
            role: m.role || '',
            icon: m.icon || 'AI',
            status: 'pending' as const
          }))
          : [];

        const playbookCodesToFetch = runningPlaybookCodes.size > 0 ? runningPlaybookCodes : recentPlaybookCodes;
        if (playbookCodesToFetch.size > 0) {
          try {
            const playbookCodesArray = Array.from(playbookCodesToFetch);

            const membersResponse = await fetch(
              `${apiUrl}/api/v1/workspaces/${workspaceId}/ai-team-members?playbook_codes=${playbookCodesArray.join(',')}`
            );

            if (membersResponse.ok) {
              const membersData = await membersResponse.json();
              const executionMembers = (membersData.members || []).map((m: any) => ({
                id: m.pack_id || m.id,
                name: m.name || m.pack_id,
                name_zh: m.name_zh,
                role: m.role || '',
                icon: m.icon || 'AI',
                status: 'in_progress' as const
              }));

              const existingIds = new Set(aiTeamMembers.map((m: any) => m.id));
              executionMembers.forEach((member: any) => {
                if (!existingIds.has(member.id)) {
                  aiTeamMembers.push(member);
                }
              });
            }
          } catch {
          }
        }

        setState(prev => ({
          ...prev,
          trainSteps,
          executionTree: treeSteps,
          thinkingTimeline: timelineEntries,
          thinkingSummary: planPayload.plan_summary,
          overallProgress: calculatedProgress,
          isExecuting,
          aiTeamMembers,
        }));

      } catch {
      }
    };

    loadExecutionState();
  }, [workspaceId, apiUrl]);

  useEffect(() => {
    return () => {
      if (throttleRef.current) {
        clearTimeout(throttleRef.current);
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
