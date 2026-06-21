import type { Project } from '@/types/project';

export interface ProjectCardData {
  projectId: string;
  projectName: string;
  storyThreadId?: string;
  mindLensId?: string;
  mindLensName?: string;
  status: 'active' | 'paused' | 'completed' | 'archived';
  lastActivity: string;
  stats: {
    totalPlaybooks: number;
    runningExecutions: number;
    pendingConfirmations: number;
    completedExecutions: number;
    artifactCount: number;
  };
  progress: {
    current: number;
    label: string;
  };
  recentEvents: Array<{
    id: string;
    type: 'playbook_started' | 'step_completed' | 'artifact_created' | 'confirmation_needed';
    playbookCode: string;
    playbookName: string;
    executionId: string;
    stepIndex?: number;
    stepName?: string;
    timestamp: string;
    metadata?: Record<string, any>;
    projectId?: string;
    projectName?: string;
  }>;
  playbooks?: Array<{
    code: string;
    name: string;
    description: string;
  }>;
  meeting?: {
    enabled: boolean;
    active: boolean;
    session_id?: string | null;
    status?: string | null;
    round_count?: number;
    max_rounds?: number;
    action_item_count?: number;
    last_activity?: string | null;
    minutes_preview?: string;
  };
}

export interface ProjectCardProps {
  project: Project;
  workspaceId?: string;
  isExpanded?: boolean;
  isFocused?: boolean;
  defaultExpanded?: boolean;
  onToggleExpand?: () => void;
  onFocus?: () => void;
  onOpenExecution?: (executionId: string) => void;
  apiUrl?: string;
}

export interface WorkflowEvidenceValues {
  profile: string | null;
  scope: string | null;
  selectedLineCount: number | null;
  totalLineBudget: number | null;
  totalCandidateCount: number | null;
  totalDroppedCount: number | null;
  renderedSectionCount: number | null;
  budgetUtilizationRatio: number | null;
}

export interface ProjectCardProgressValues {
  progressPercentage: number;
  scanRangeStart: number;
  scanRangeEnd: number;
  scanRangeWidth: number;
}

export interface ProjectCardApiContext {
  apiUrl: string;
  workspaceId: string;
  projectId: string;
}
