import type { Dispatch, SetStateAction } from 'react';
import type { ExecutionStep } from '@/components/execution';
import type { ExecutionUIState, PipelineStage, SSEEvent, TimelineEntry, TreeStep } from './types';

interface EventHandlerOptions {
  setState: Dispatch<SetStateAction<ExecutionUIState>>;
  addThinkingStep: (step: string) => void;
  calculateProgress: (steps: ExecutionStep[]) => number;
}

export function createExecutionStateEventHandler({
  setState,
  addThinkingStep,
  calculateProgress,
}: EventHandlerOptions) {
  return (event: SSEEvent) => {
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
          const newSteps: ExecutionStep[] = event.plan.steps.map(step => ({
            id: step.id,
            name: step.name,
            icon: step.icon || 'DOC',
            status: (step.status as ExecutionStep['status']) || 'pending',
          }));
          const treeSteps: TreeStep[] = event.plan.steps.map(step => ({
            id: step.id,
            name: step.name,
            status: (step.status as TreeStep['status']) || 'pending',
          }));
          const newTimelineEntry: TimelineEntry = {
            id: `plan-${Date.now()}`,
            timestamp: new Date().toISOString(),
            summary: event.plan.summary || `Execution plan: ${event.plan.steps.length} steps`,
            stepCount: event.plan.steps.length,
            status: 'in_progress',
          };
          const aiTeamMembers = (event.plan.ai_team_members && event.plan.ai_team_members.length > 0)
            ? event.plan.ai_team_members.map((member: any) => ({
              id: member.pack_id || member.id,
              name: member.name || member.pack_id,
              name_zh: member.name_zh,
              role: member.role || '',
              icon: member.icon || 'AI',
              status: 'pending' as const,
            }))
            : (isNewRun ? [] : prev.aiTeamMembers);

          return {
            ...prev,
            currentRunId: newRunId,
            pipelineStage: isNewRun ? null : prev.pipelineStage,
            aiTeamMembers,
            trainSteps: newSteps,
            thinkingSummary: event.plan.summary,
            overallProgress: calculateProgress(newSteps),
            executionTree: treeSteps,
            thinkingTimeline: isNewRun
              ? [newTimelineEntry, ...prev.thinkingTimeline].slice(0, 10)
              : prev.thinkingTimeline,
          };
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
              streaming: true,
            },
            aiTeamMembers: updatedMembers,
          };
        });
        break;

      case 'task_update':
        setState(prev => {
          if (!event.task.pack_id) return prev;

          return {
            ...prev,
            aiTeamMembers: prev.aiTeamMembers.map(member =>
              member.id === event.task.pack_id
                ? { ...member, status: mapTaskStatusToMemberStatus(event.task.status) }
                : member
            ),
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
                streaming: false,
              },
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
                streaming: false,
              },
            };
          }
          return prev;
        });
        break;

      case 'step_start':
        setState(prev => {
          const newSteps = prev.trainSteps.map(step =>
            step.id === event.stepId ? { ...step, status: 'in_progress' as const } : step
          );
          const newTree = prev.executionTree.map(step =>
            step.id === event.stepId ? { ...step, status: 'in_progress' as const } : step
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
          const newSteps = prev.trainSteps.map(step =>
            step.id === event.stepId
              ? { ...step, detail: event.message, status: 'in_progress' as const }
              : step
          );
          const newTree = prev.executionTree.map(step =>
            step.id === event.stepId
              ? { ...step, detail: event.message, status: 'in_progress' as const }
              : step
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
                    progress,
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
          const newSteps = prev.trainSteps.map(step =>
            step.id === event.stepId
              ? { ...step, status: 'completed' as const, detail: undefined }
              : step
          );
          const newTree = prev.executionTree.map(step =>
            step.id === event.stepId
              ? { ...step, status: 'completed' as const, detail: undefined }
              : step
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
          const newSteps = prev.trainSteps.map(step =>
            step.id === event.stepId
              ? { ...step, status: 'error' as const, detail: event.message }
              : step
          );
          const newTree = prev.executionTree.map(step =>
            step.id === event.stepId
              ? { ...step, status: 'error' as const, detail: event.message }
              : step
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
  };
}

function mapTaskStatusToMemberStatus(taskStatus: string): 'pending' | 'in_progress' | 'completed' | 'error' {
  if (taskStatus === 'SUCCEEDED' || taskStatus === 'succeeded') return 'completed';
  if (taskStatus === 'FAILED' || taskStatus === 'failed') return 'error';
  if (taskStatus === 'RUNNING' || taskStatus === 'running') return 'in_progress';
  return 'pending';
}
