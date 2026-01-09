/**
 * Dashboard types aligned with site-hub contract
 */

import { DateTime } from 'luxon';

export enum InboxItemType {
  PENDING_DECISION = 'pending_decision',
  ASSIGNMENT = 'assignment',
  MENTION = 'mention',
  SYSTEM_ALERT = 'system_alert',
  CASE_UPDATE = 'case_update',
}

export enum WorkspaceSetupStatus {
  READY = 'ready',
  NEEDS_SETUP = 'needs_setup',
  PENDING = 'pending',
  ERROR = 'error',
}

export enum SetupItem {
  MODEL_CONFIG = 'model_config',
  TOOL_AUTH = 'tool_auth',
  PLAYBOOK_SELECTION = 'playbook_selection',
  RUNTIME_PROFILE = 'runtime_profile',
  COMPUTE_PROFILE = 'compute_profile',
  CAPABILITY_PACK = 'capability_pack',
}

export enum AssignmentReviewStatus {
  NONE = 'none',
  SUBMITTED = 'submitted',
  NEEDS_CHANGES = 'needs_changes',
  APPROVED = 'approved',
  DELIVERED = 'delivered',
}

export interface DashboardQuery {
  scope?: string;
  view?: string;
  filters?: Record<string, any>;
  sort_by?: string;
  sort_order?: string;
  limit?: number;
  offset?: number;
}

export interface DashboardCountsDTO {
  pending_decisions: number;
  open_assignments: number;
  open_cases: number;
  blocked_cases: number;
  running_jobs: number;
  overdue_items: number;
  mentions: number;
  delegated_pending: number;
}

export interface DashboardSummaryDTO {
  scope: string;
  counts: DashboardCountsDTO;
  recent_activity_at?: string;
  needs_setup: SetupItem[];
  not_supported: string[];
  warnings: string[];
}

export interface InboxItemDTO {
  id: string;
  item_type: InboxItemType;
  source_type: string;
  source_id: string;
  workspace_id?: string;
  workspace_name?: string;
  case_id?: string;
  case_title?: string;
  thread_id?: string;
  title: string;
  summary?: string;
  status: string;
  priority: number;
  is_overdue: boolean;
  due_at?: string | null;
  assignee_user_id?: string;
  assignee_name?: string;
  created_by_user_id?: string;
  created_by_name?: string;
  available_actions: string[];
  extra: Record<string, any>;
  created_at: string;
  updated_at?: string;
}

export interface CaseCardDTO {
  id: string;
  tenant_id: string;
  group_id?: string;
  group_name?: string;
  workspace_id?: string;
  workspace_name?: string;
  title?: string;
  summary?: string;
  status: string;
  progress_percent?: number;
  checklist_done: number;
  checklist_total: number;
  owner_user_id?: string;
  owner_name?: string;
  owner_avatar?: string;
  assignees: Array<{ user_id: string; name?: string }>;
  priority: number;
  due_at?: string | null;
  is_overdue: boolean;
  open_assignments_count: number;
  artifacts_count: number;
  threads_count: number;
  last_activity_type?: string;
  last_activity_at?: string;
  last_activity_by?: string;
  available_actions: string[];
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface AssignmentCardDTO {
  id: string;
  case_id?: string;
  case_title?: string;
  case_group_id?: string;
  case_group_name?: string;
  source_workspace_id?: string;
  source_workspace_name?: string;
  target_workspace_id?: string;
  target_workspace_name?: string;
  title: string;
  description?: string;
  status: string;
  review_status?: AssignmentReviewStatus;
  priority: number;
  claimed_by_user_id?: string;
  claimed_by_name?: string;
  claimed_by_avatar?: string;
  delegated_by_user_id?: string;
  delegated_by_name?: string;
  delegated_by_avatar?: string;
  due_at?: string | null;
  is_overdue: boolean;
  required_artifacts: string[];
  submitted_artifacts: string[];
  available_actions: string[];
  hop_count: number;
  max_hops: number;
  routing_reason?: string;
  created_at: string;
  claimed_at?: string;
  completed_at?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  warnings: string[];
}

export interface SavedViewDTO {
  id: string;
  name: string;
  scope: string;
  view: string;
  tab: string;
  filters: Record<string, any>;
  sort_by: string;
  sort_order: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface SavedViewCreate {
  name: string;
  scope?: string;
  view?: string;
  tab?: string;
  filters?: Record<string, any>;
  sort_by?: string;
  sort_order?: string;
  is_default?: boolean;
}

