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

export type SSEEvent =
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

export interface ExecutionStateSnapshot {
  trainSteps: ExecutionStep[];
  executionTree: TreeStep[];
  thinkingTimeline: TimelineEntry[];
  thinkingSummary?: string;
  overallProgress: number;
  isExecuting: boolean;
  aiTeamMembers: ExecutionUIState['aiTeamMembers'];
}
