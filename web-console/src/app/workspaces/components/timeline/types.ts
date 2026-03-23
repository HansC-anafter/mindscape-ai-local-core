export interface TimelineItem {
  id: string;
  workspace_id: string;
  message_id?: string;
  task_id?: string;
  type: string;
  title: string;
  summary?: string;
  data?: any;
  cta?:
    | {
        action: string;
        label: string;
        confirm?: boolean;
      }
    | Array<{
        action: string;
        label: string;
        confirm?: boolean;
      }>;
  created_at: string;
  execution_id?: string;
  task_status?: string;
  task_started_at?: string;
  task_completed_at?: string;
  has_execution_context?: boolean;
}

export interface ExecutionStep {
  id: string;
  execution_id: string;
  step_index: number;
  step_name: string;
  status: string;
  requires_confirmation: boolean;
  confirmation_status?: string;
  [key: string]: any;
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
  steps?: ExecutionStep[];
  [key: string]: any;
}

export interface PendingRestartInfo {
  playbook_code: string;
  workspace_id: string;
  timestamp: number;
}

export interface TimelinePanelProps {
  workspaceId: string;
  apiUrl: string;
  isInSettingsPage?: boolean;
  focusExecutionId?: string | null;
  onClearFocus?: () => void;
  showArchivedOnly?: boolean;
  onArtifactClick?: (artifact: any) => void;
}
