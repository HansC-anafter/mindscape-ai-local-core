import type { ReactNode } from 'react';

export interface Workspace {
  id: string;
  title: string;
  description?: string;
  workspace_type?: 'personal' | 'brand' | 'team';
  group_id?: string | null;
  workspace_role?: 'dispatch' | 'cell' | null;
  group_memberships?: Array<{
    group_id: string;
    display_name: string;
    role: 'dispatch' | 'cell';
    revision: number;
  }>;
  primary_project_id?: string;
  default_playbook_id?: string;
  default_locale?: string;
  mode?: string | null;
  execution_mode?: 'qa' | 'execution' | 'hybrid' | 'meeting' | null;
  expected_artifacts?: string[];
  execution_priority?: 'low' | 'medium' | 'high' | null;
  data_sources?: any;
  associated_intent?: any;
  storage_base_path?: string;
  artifacts_dir?: string;
  uploads_dir?: string;
  storage_config?: any;
  metadata?: Record<string, any>;
  playbook_storage_config?: Record<string, any>;
  playbook_auto_execution_config?: Record<string, any>;
  workspace_blueprint?: {
    instruction?: {
      persona?: string;
      goals?: string[];
      anti_goals?: string[];
      style_rules?: string[];
      domain_context?: string;
      version?: number;
    };
    brief?: string;
    [key: string]: any;
  };
}

export interface Task {
  id: string;
  workspace_id: string;
  pack_id?: string;
  playbook_id?: string;
  task_type?: string;
  status: string;
  title?: string;
  summary?: string;
  message_id?: string;
  created_at: string;
  updated_at?: string;
  data?: any;
  params?: any;
  result?: any;
}

export interface ExecutionSession {
  execution_id: string;
  workspace_id: string;
  status: string;
  playbook_code?: string;
  trigger_source?: string;
  current_step_index: number;
  total_steps: number;
  paused_at?: string;
  origin_intent_label?: string;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
  steps?: any[];
  [key: string]: any;
}

export interface SystemStatus {
  llm_configured: boolean;
  llm_provider?: string;
  vector_db_connected: boolean;
  tools: Record<string, any>;
  critical_issues_count: number;
  has_issues: boolean;
}

export interface WorkspaceDataContextType {
  workspace: Workspace | null;
  tasks: Task[];
  executions: ExecutionSession[];
  systemStatus: SystemStatus | null;
  isLoading: boolean;
  isLoadingWorkspace: boolean;
  isLoadingWorkspaceDetails: boolean;
  isLoadingTasks: boolean;
  isLoadingExecutions: boolean;
  error: string | null;
  refreshWorkspace: () => Promise<void>;
  refreshWorkspaceDetails: () => Promise<void>;
  refreshTasks: () => Promise<void>;
  refreshExecutions: () => Promise<void>;
  refreshSystemStatus: (options?: { force?: boolean }) => Promise<void>;
  refreshAll: () => Promise<void>;
  updateWorkspace: (updates: Partial<Workspace>) => Promise<Workspace | null>;
}

export type WorkspaceDataInitialLoadProfile = 'full' | 'capability-host';

export interface WorkspaceDataProviderProps {
  workspaceId: string;
  initialLoadProfile?: WorkspaceDataInitialLoadProfile;
  children: ReactNode;
}
