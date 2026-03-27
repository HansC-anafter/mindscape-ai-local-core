export interface ExecutionSession {
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

export interface RemoteExecutionSummary {
  job_type?: string | null;
  capability_code?: string | null;
  tool_name?: string | null;
  workflow_step_id?: string | null;
  result_ingress_mode?: string | null;
  cloud_dispatch_state?: string | null;
  cloud_execution_id?: string | null;
  cloud_state?: string | null;
  callback_delivered_at?: string | null;
  callback_error?: string | null;
  target_device_id?: string | null;
  lineage_root_execution_id?: string | null;
  replay_of_execution_id?: string | null;
  latest_replay_execution_id?: string | null;
  replay_children_execution_ids?: string[];
  replay_children_count?: number;
  replay_requested_at?: string | null;
  is_workflow_step_child?: boolean;
  is_replay_attempt?: boolean;
  is_superseded_by_replay?: boolean;
  has_replays?: boolean;
}

export interface RemoteChildExecution {
  id?: string;
  execution_id: string;
  parent_execution_id?: string | null;
  status: string;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
  playbook_code?: string;
  remote_execution_summary?: RemoteExecutionSummary | null;
}

export interface RemoteExecutionAggregate {
  totalRemoteChildren: number;
  replayAttempts: number;
  supersededByReplay: number;
  uniqueTargetDevices: string[];
}

export interface ExecutionStep {
  id: string;
  execution_id: string;
  step_index: number;
  step_name: string;
  total_steps?: number;
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

export interface AgentCollaboration {
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

export interface ToolCall {
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

export interface StageResult {
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

export interface PlaybookMetadata {
  playbook_code: string;
  title?: string;
  description?: string;
  version?: string;
  parameters?: Record<string, any>;
  [key: string]: any;
}

export interface PlaybookStepDefinition {
  step_index: number;
  step_name: string;
  description?: string;
  agent_type?: string;
  used_tools?: string[];
}

export interface ExecutionInspectorProps {
  executionId: string;
  workspaceId: string;
  apiUrl: string;
  onClose?: () => void;
}

export interface StepEvent {
  id: string;
  type: 'step' | 'tool' | 'collaboration';
  timestamp: Date;
  agent?: string;
  tool?: string;
  content: string;
}

export interface Artifact {
  id: string;
  name: string;
  type: string;
  createdAt?: string;
  updatedAt?: string;
  url?: string;
  stepId?: string;
  filePath?: string;
  description?: string;
  metadata?: Record<string, any>;
  content?: Record<string, any>;
  executionId?: string;
  artifactType?: string | null;
  title?: string;
}

export interface ReviewChecklistItemView {
  check_id: string;
  label?: string;
  description?: string;
  focus?: string;
}

export interface ReviewChecklistSummaryView {
  average_score?: number | null;
  scored_checks?: number;
}

export interface ReviewDecisionView {
  decision?: string;
  reviewer_id?: string;
  reviewed_at?: string;
  notes?: string;
  checklist_scores?: Record<string, number>;
  checklist_summary?: ReviewChecklistSummaryView | null;
  followup_actions?: string[];
}

export interface VisualAcceptanceSlotView {
  slot_key?: string;
  label?: string;
  index?: number;
  storage_key?: string;
  preview_url?: string;
  preview_kind?: string;
  mask_storage_key?: string;
  mask_preview_url?: string;
  mask_preview_kind?: string;
  alpha_storage_key?: string;
  alpha_preview_url?: string;
  alpha_preview_kind?: string;
  source_reference_fingerprint?: string;
}

export interface VisualAcceptanceBundleContent {
  review_bundle_id?: string;
  run_id?: string;
  scene_id?: string;
  source_kind?: string;
  status?: string;
  render_status?: string;
  renderer?: string;
  owning_capability_code?: string | null;
  package_id?: string | null;
  preset_id?: string | null;
  artifact_ids?: string[];
  binding_mode?: string | null;
  slots?: VisualAcceptanceSlotView[];
  checklist_template?: ReviewChecklistItemView[];
  latest_review_decision?: ReviewDecisionView | null;
  scene_context?: {
    object_workload_snapshot?: Record<string, any> | null;
    scene_manifest?: Record<string, any> | null;
  } | null;
  object_workload_snapshot?: Record<string, any> | null;
}

export interface ReviewBundleArtifact extends Artifact {
  metadata?: Record<string, any>;
  content?: VisualAcceptanceBundleContent;
}

export interface RelatedGovernedMemoryLink {
  eventId: string;
  memoryItemId: string;
  lifecycleStatus?: string;
  verificationStatus?: string;
}

export interface WorkflowData {
  workflow_result?: any;
  handoff_plan?: any;
}

export interface ExecutionStats {
  concurrent: number;
  waitingConfirmation: number;
  completed: number;
}
