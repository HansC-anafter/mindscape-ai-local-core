export interface UnifiedEvent {
  id: string;
  type: string;
  timestamp: string;
  actor: string;
  workspace_id?: string;
  project_id?: string;
  profile_id: string;
  thread_id?: string;
  payload: {
    decision_id?: string;
    intent_log_id?: string;
    requires_user_approval?: boolean;
    can_auto_execute?: boolean;
    missing_inputs?: string[];
    clarification_questions?: string[];
    conflicts?: Array<{ type: string; description: string; layers: string[] }>;
    blocking_steps?: string[];
    card_type?: 'decision' | 'input' | 'review' | 'assignment' | 'governance';
    priority?: 'blocker' | 'high' | 'normal';
    selected_playbook_code?: string;
    rationale?: string;
    governance_decision?: {
      type: 'cost_exceeded' | 'node_rejected' | 'policy_violation' | 'preflight_failed';
      layer: 'cost' | 'node' | 'policy' | 'preflight';
      approved: boolean;
      reason?: string;
      cost_governance?: {
        estimated_cost: number;
        quota_limit: number;
        current_usage: number;
        downgrade_suggestion?: {
          profile: string;
          estimated_cost: number;
        };
      };
      node_governance?: {
        rejection_reason: 'blacklist' | 'risk_label' | 'throttle';
        affected_playbooks?: string[];
        alternatives?: string[];
      };
      policy_violation?: {
        violation_type: 'role' | 'data_domain' | 'pii';
        policy_id?: string;
        violation_items: string[];
        request_permission_url?: string;
      };
      preflight_failure?: {
        missing_inputs: string[];
        missing_credentials: string[];
        environment_issues: string[];
        recommended_alternatives?: string[];
      };
    };
    execution_id?: string;
    previous_state?: string;
    new_state?: 'WAITING_HUMAN' | 'READY' | 'RUNNING' | 'DONE';
    reason?: string;
    playbook_code?: string;
    blocker_count?: number;
    artifact_id?: string;
    artifact_type?: string;
    title?: string;
    summary?: string;
    file_path?: string;
    storage_ref?: string;
    tool_fqn?: string;
    tool_call_id?: string;
    step_id?: string;
    status?: string;
    result_summary?: string;
    branch_id?: string;
    alternatives?: Array<{
      playbook_code: string;
      confidence: number;
      rationale: string;
      differences?: string[];
    }>;
    recommended_branch?: string;
    memory_item_id?: string;
    digest_id?: string;
    writeback_run_id?: string;
    lifecycle_status?: string;
    verification_status?: string;
    meeting_session_id?: string;
    meeting_type?: string;
    workflow_evidence_profile?: string;
    workflow_evidence_scope?: string;
    workflow_evidence_selected_line_count?: number;
    workflow_evidence_total_line_budget?: number;
    workflow_evidence_total_candidate_count?: number;
    workflow_evidence_total_dropped_count?: number;
    workflow_evidence_rendered_section_count?: number;
    workflow_evidence_budget_utilization_ratio?: number;
  };
  entity_ids?: Record<string, string>;
  metadata?: Record<string, any>;
}

export interface ExecutionStatus {
  status: 'WAITING_HUMAN' | 'READY' | 'RUNNING' | 'DONE' | 'UNKNOWN';
  message: string;
  detailedMessage?: string;
  blockers?: Array<{
    id: string;
    reason: string;
    type: string;
  }>;
  readyCount?: number;
}

export interface TimelineItem {
  id: string;
  timestamp: string;
  type: string;
  summary: string;
  clickable: boolean;
  targetCardId?: string;
  navigationHref?: string;
  memoryItemId?: string;
  memoryLifecycleStatus?: string;
  memoryVerificationStatus?: string;
  meetingEvidenceProfile?: string;
  meetingEvidenceScope?: string;
  meetingEvidenceSelectedLines?: number;
  meetingEvidenceTotalBudget?: number;
  meetingEvidenceTotalCandidates?: number;
  meetingEvidenceTotalDropped?: number;
  meetingEvidenceRenderedSections?: number;
  meetingEvidenceBudgetUtilizationRatio?: number;
}
