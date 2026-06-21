export type ExecutionMode = 'qa' | 'execution' | 'hybrid' | 'meeting';
export type ExecutionPriority = 'low' | 'medium' | 'high';
export type ProjectAssignmentMode = 'auto_silent' | 'assistive' | 'manual_first';
export type SgrMode = 'inline' | 'two_pass';

export interface WorkspaceSettingsWorkspace {
  id: string;
  title: string;
  storage_base_path?: string;
  artifacts_dir?: string;
  storage_config?: unknown;
  execution_mode?: ExecutionMode;
  expected_artifacts?: string[];
  execution_priority?: ExecutionPriority;
  project_assignment_mode?: ProjectAssignmentMode;
  playbook_auto_execution_config?: Record<string, {
    auto_execute?: boolean;
    confidence_threshold?: number;
  }>;
  metadata?: Record<string, unknown>;
  workspace_blueprint?: {
    instruction?: {
      persona?: string;
      goals?: string[];
      anti_goals?: string[];
      style_rules?: string[];
      domain_context?: string;
      version?: number;
    } | null;
    brief?: string | null;
  } | null;
}

export interface WorkspaceSettingsProps {
  workspace: WorkspaceSettingsWorkspace | null;
  workspaceId: string;
  apiUrl: string;
  onUpdate?: () => void;
}

export interface WorkspaceSettingsApiContext {
  apiUrl: string;
  workspaceId: string;
}

export interface WorkspaceStorageValues {
  storageBasePath: string;
  artifactsDir: string;
}

export interface WorkspaceExecutionValues {
  executionMode: ExecutionMode;
  executionPriority: ExecutionPriority;
  projectAssignmentMode: ProjectAssignmentMode;
  expectedArtifacts: string[];
}

export interface WorkspaceIntentExtractionValues {
  autoExecute: boolean;
  threshold: number;
}

export interface WorkspaceSgrValues {
  enabled: boolean;
  mode: SgrMode;
}
