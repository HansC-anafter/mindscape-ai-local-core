export type KnowledgeGrant = {
  principal_type: 'user' | 'workspace_role' | 'group_role' | 'service';
  principal_id: string;
  relation: 'reader' | 'editor' | 'owner' | 'ingester';
  effect: 'allow' | 'deny';
  valid_from?: string | null;
  valid_until?: string | null;
};

export type KnowledgeAccessSummaryItem = {
  knowledge_resource_id: string;
  security_label_id: string;
  owner_capability_code: string;
  source_kind: string;
  source_app: string;
  source_id: string;
  source_ref: string;
  source_revision: string;
  resource_active: boolean;
  updated_at: string;
  classification: string;
  authz_revision: number;
  projection_status?: string | null;
  projection_revision_id?: string | null;
  grant_count: number;
  deny_count: number;
  deny_present: boolean;
  record_count?: number | null;
  evidence_unit_count?: number | null;
  relation_count?: number | null;
  community_count: number;
  active_report_count: number;
  channels: Array<{
    modality: string;
    state: string;
    row_count: number;
    byte_count: number;
  }>;
};

export type KnowledgeAccessSummary = {
  contract_version: 'knowledge_access.v1';
  workspace_id: string;
  items: KnowledgeAccessSummaryItem[];
  total_count: number;
  state_counts: Record<string, number>;
  next_cursor?: string | null;
  request_budget: {
    initial_summary_requests: 1;
    polling: false;
  };
};

export type KnowledgeAccessDetail = {
  contract_version: 'knowledge_access.v1';
  resource: {
    knowledge_resource_id: string;
    security_label_id: string;
    owner_capability_code: string;
    source_kind: string;
    source_app: string;
    source_id: string;
    source_ref: string;
    source_revision: string;
    owner_scope_type: string;
    owner_scope_id: string;
    classification: string;
    authz_revision: number;
    active: boolean;
    updated_at: string;
  };
  projection: Record<string, unknown> | null;
  grants: KnowledgeGrant[];
  grant_count: number;
  grants_truncated: boolean;
  modality_truth: Array<{
    modality: 'text' | 'image' | 'video' | 'audio';
    state: string;
    channels: Array<Record<string, unknown>>;
    pointer_only_is_active: false;
  }>;
  graph: Record<string, number>;
  audit: Array<Record<string, unknown>>;
  agent_mask: {
    mode: 'runtime_intersection_only';
    can_grant_human_access: false;
    persisted_masks: KnowledgeAgentMask[];
    mask_count: number;
    masks_truncated: boolean;
    audit: Array<Record<string, unknown>>;
  };
  mutation?: {
    state: 'replaced';
    graph_reindex_required: boolean;
    agent_policy_revision: string;
    follow_up_get_required: false;
  };
};

export type KnowledgeAgentMask = {
  agent_role: string;
  effect: 'allow' | 'deny';
};

export type KnowledgeAccessReplacement = {
  expected_authz_revision: number;
  acknowledge_complete_replacement: true;
  grants: KnowledgeGrant[];
  agent_masks: KnowledgeAgentMask[];
};

export type KnowledgeProjectionAction = 'reindex' | 'retry' | 'revoke' | 'restore';

export type KnowledgeProjectionActionReceipt = {
  contract_version: 'knowledge_access.v1';
  knowledge_resource_id: string;
  action: KnowledgeProjectionAction;
  expected_authz_revision: number;
  expected_source_revision: string;
  admission: {
    state: string;
    intake_id?: string | null;
    task_id?: string | null;
    reason?: string | null;
  };
  request_budget: {
    mutation_requests: 1;
    follow_up_get_required: false;
    polling: false;
  };
};
