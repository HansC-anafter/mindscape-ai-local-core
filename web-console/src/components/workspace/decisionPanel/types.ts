import type { DecisionCardData } from '../DecisionCard';

export interface IntentCard {
  id: string;
  title: string;
  description?: string;
  status: 'pending_decision' | 'confirmed' | 'rejected';
  priority: 'high' | 'medium' | 'low';
  decisions?: Array<{
    id: string;
    question: string;
    options: string[];
    selectedOption?: string;
  }>;
  createdAt?: string;
}

export interface DecisionPanelWorkspace {
  playbook_auto_execution_config?: Record<string, {
    confidence_threshold?: number;
    auto_execute?: boolean;
  }>;
  owner_user_id?: string;
}

export interface DecisionPanelProps {
  workspaceId: string;
  apiUrl: string;
  selectedThreadId?: string | null;
  onViewArtifact?: (artifact: any) => void;
  onSwitchToOutcomes?: () => void;
  workspace?: DecisionPanelWorkspace;
}

export type DecisionFilter =
  | 'all'
  | 'blockers'
  | 'assigned-to-me'
  | 'mentioned-me'
  | 'waiting-on-others';

export interface InputDialogState {
  title: string;
  fields: Array<{
    key: string;
    label: string;
    type?: 'text' | 'textarea' | 'file';
    required?: boolean;
    placeholder?: string;
  }>;
  onSubmit: (values: Record<string, string>) => void;
}

export interface BranchDialogState {
  title: string;
  alternatives: Array<{
    playbook_code: string;
    confidence: number;
    rationale: string;
    differences?: string[];
  }>;
  recommendedBranch?: string;
  onSubmit: (selectedPlaybookCode: string) => void;
}

export interface RelatedDecisionContext {
  memoryId: string | null;
  memoryLifecycleStatus?: string;
  memoryVerificationStatus?: string;
  meetingSessionId: string | null;
  workflowEvidenceProfile?: string;
  workflowEvidenceScope?: string;
  workflowEvidenceSelectedLines?: number;
  workflowEvidenceTotalBudget?: number;
  workflowEvidenceTotalCandidates?: number;
  workflowEvidenceTotalDropped?: number;
  workflowEvidenceRenderedSections?: number;
  workflowEvidenceUtilizationRatio?: number;
}

export interface DecisionPanelViewProps {
  workspaceId: string;
  apiUrl: string;
  workspace?: DecisionPanelWorkspace;
  onViewArtifact?: (artifact: any) => void;
  onSwitchToOutcomes?: () => void;
  loading: boolean;
  pendingTaskCount: number;
  onPendingTaskCountChange: (count: number) => void;
  currentUserId: string;
  filteredDecisionCards: DecisionCardData[];
  pendingCards: IntentCard[];
  historyCards: IntentCard[];
  blockerCount: number;
  assignedToMeCount: number;
  openDecisionCount: number;
  mentionedMeCount: number;
  waitingOnOthersCount: number;
  filter: DecisionFilter;
  onFilterChange: (filter: DecisionFilter) => void;
  showLegacyTasks: boolean;
  onToggleLegacyTasks: () => void;
  showHistory: boolean;
  onToggleHistory: () => void;
  relatedContext: RelatedDecisionContext;
  relatedMemoryLoading: boolean;
  inputDialog: InputDialogState | null;
  branchDialog: BranchDialogState | null;
  onCloseInputDialog: () => void;
  onCloseBranchDialog: () => void;
  onIntentStatusChange: () => void;
  onExpandCard: (cardId: string) => void;
}
