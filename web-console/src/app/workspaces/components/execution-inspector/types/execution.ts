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
  url?: string;
  stepId?: string;
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
