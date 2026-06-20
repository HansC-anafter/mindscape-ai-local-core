import type { MessageKey } from '@/lib/i18n';

export interface WorkspaceMemoryItemSummary {
  id: string;
  kind: string;
  layer: string;
  title: string;
  claim: string;
  summary: string;
  lifecycle_status: string;
  verification_status: string;
  salience: number;
  confidence: number;
  subject_type: string;
  subject_id: string;
  supersedes_memory_id?: string | null;
  observed_at: string;
  last_confirmed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceMemoryListResponse {
  workspace_id: string;
  items: WorkspaceMemoryItemSummary[];
  total: number;
  limit: number;
}

export interface MemoryVersionSummary {
  id: string;
  version_no: number;
  update_mode: string;
  claim_snapshot: string;
  summary_snapshot?: string | null;
  metadata_snapshot: Record<string, unknown>;
  created_at: string;
  created_from_run_id?: string | null;
}

export interface MemoryEvidenceSummary {
  id: string;
  evidence_type: string;
  evidence_id: string;
  link_role: string;
  excerpt?: string | null;
  confidence?: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
  artifact_landing?: ArtifactLandingDrilldownSummary | null;
  execution_trace_drilldown?: ExecutionTraceDrilldownSummary | null;
}

export interface ArtifactLandingDrilldownSummary {
  artifact_dir?: string | null;
  result_json_path?: string | null;
  summary_md_path?: string | null;
  attachments_count: number;
  attachments: string[];
  landed_at?: string | null;
  artifact_dir_exists: boolean;
  result_json_exists: boolean;
  summary_md_exists: boolean;
}

export interface ExecutionTraceDrilldownSummary {
  trace_source?: string | null;
  trace_file_path?: string | null;
  trace_file_exists: boolean;
  sandbox_path?: string | null;
  tool_call_count: number;
  file_change_count: number;
  files_created_count: number;
  files_modified_count: number;
  success?: boolean | null;
  duration_seconds?: number | null;
  task_description?: string | null;
  output_summary?: string | null;
}

export interface MemoryEdgeSummary {
  id: string;
  from_memory_id: string;
  to_memory_id: string;
  edge_type: string;
  weight?: number | null;
  valid_from: string;
  valid_to?: string | null;
  evidence_strength?: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface PersonalKnowledgeProjectionSummary {
  id: string;
  knowledge_type: string;
  content: string;
  status: string;
  confidence: number;
  created_at: string;
  last_verified_at?: string | null;
}

export interface GoalLedgerProjectionSummary {
  id: string;
  title: string;
  description: string;
  status: string;
  horizon: string;
  created_at: string;
  confirmed_at?: string | null;
}

export interface WorkspaceMemoryDetailResponse {
  workspace_id: string;
  memory_item: WorkspaceMemoryItemSummary;
  versions: MemoryVersionSummary[];
  evidence: MemoryEvidenceSummary[];
  outgoing_edges: MemoryEdgeSummary[];
  personal_knowledge_projections: PersonalKnowledgeProjectionSummary[];
  goal_projections: GoalLedgerProjectionSummary[];
  evidence_coverage?: EvidenceCoverageSummary;
  transition_cues?: TransitionCue[];
  successor_draft_suggestion?: SuccessorDraftSuggestion | null;
  transition_reason_suggestions?: {
    verify: string;
    stale: string;
    supersede: string;
  };
}

export interface MemoryTransitionResponse {
  workspace_id: string;
  memory_item_id: string;
  transition: 'verify' | 'stale' | 'supersede';
  noop: boolean;
  lifecycle_status: string;
  verification_status: string;
  run_id: string;
  successor_memory_item_id?: string | null;
}

export interface GovernedMemoryPanelProps {
  workspaceId: string;
}

export interface EvidenceCoverageSummary {
  deliberation: number;
  execution: number;
  governance: number;
  support: number;
  derived: number;
}

export interface TransitionCue {
  id: string;
  tone: 'positive' | 'neutral' | 'caution';
  title: string;
  body: string;
}

export interface SuccessorDraftSuggestion {
  title: string;
  claim: string;
  summary: string;
  primary_evidence_id?: string | null;
  primary_evidence_type?: string | null;
}

export type TranslateFn = (key: MessageKey, params?: Record<string, string>) => string;

export type MemoryTransitionAction = MemoryTransitionResponse['transition'];

export interface MemoryTransitionOptions {
  successor_title?: string;
  successor_claim?: string;
  successor_summary?: string;
}
