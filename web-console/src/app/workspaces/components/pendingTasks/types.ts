export interface PendingTask {
  id: string;
  workspace_id: string;
  pack_id?: string;
  playbook_id?: string;
  task_type?: string;
  status: 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED';
  title?: string;
  summary?: string;
  message_id?: string;
  created_at: string;
  updated_at?: string;
  completed_at?: string;
  data?: any;
  params?: any;
  result?: any;
  artifact_creation_failed?: boolean;
  artifact_warning?: any;
}

export interface PendingTaskAutoExecutionConfig {
  confidence_threshold?: number;
  auto_execute?: boolean;
}

export interface PendingTasksWorkspace {
  playbook_auto_execution_config?: Record<string, PendingTaskAutoExecutionConfig>;
}

export interface PendingTasksPanelProps {
  workspaceId: string;
  apiUrl?: string;
  onViewArtifact?: (artifact: any) => void;
  onSwitchToOutcomes?: () => void;
  workspace?: PendingTasksWorkspace;
  onTaskCountChange?: (count: number) => void;
}

export interface BackgroundRoutine {
  playbook_code?: string;
  enabled?: boolean;
  [key: string]: any;
}

export interface RejectedTaskState {
  timestamp: number;
  canRestore: boolean;
}
