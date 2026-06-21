import type {
  ExecutionMode,
  ExecutionPriority,
  ProjectAssignmentMode,
  SgrMode,
  WorkspaceExecutionValues,
  WorkspaceIntentExtractionValues,
  WorkspaceSettingsWorkspace,
  WorkspaceSgrValues,
  WorkspaceStorageValues,
} from './workspaceSettingsTypes';

export const EXECUTION_MODE_OPTIONS: { value: ExecutionMode; label: string; icon: string; description: string }[] = [
  { value: 'qa', label: 'Chat First', icon: 'chat', description: 'Conversation-oriented, execution as supplement' },
  { value: 'execution', label: 'Execution First', icon: 'zap', description: 'Action-oriented, direct output' },
  { value: 'hybrid', label: 'Chat & Execute', icon: 'refresh', description: 'Balance conversation with action' },
  { value: 'meeting', label: 'Meeting', icon: 'groups', description: 'Multi-agent meeting for decision convergence and action items' },
];

export const EXECUTION_PRIORITY_OPTIONS: { value: ExecutionPriority; label: string; description: string }[] = [
  { value: 'low', label: 'Conservative', description: 'Execute only at high confidence (90%)' },
  { value: 'medium', label: 'Balanced', description: 'Medium confidence threshold (80%)' },
  { value: 'high', label: 'Aggressive', description: 'Low threshold, fast execution (60%)' },
];

export const PROJECT_ASSIGNMENT_MODE_OPTIONS: { value: ProjectAssignmentMode; label: string; description: string }[] = [
  { value: 'auto_silent', label: 'Auto Classify', description: 'Auto classify with labels, prompt only when uncertain' },
  { value: 'assistive', label: 'Assisted', description: 'Auto classify, prompt for confirmation at medium-low confidence' },
  { value: 'manual_first', label: 'Manual', description: 'Manual selection required, AI provides suggestions only' },
];

export const COMMON_ARTIFACTS = ['docx', 'pptx', 'xlsx', 'pdf', 'md', 'html'];

export interface DerivedWorkspaceSettings {
  storage: WorkspaceStorageValues;
  execution: WorkspaceExecutionValues;
  intentExtraction: WorkspaceIntentExtractionValues;
  sgr: WorkspaceSgrValues;
}

export function deriveWorkspaceSettings(workspace: WorkspaceSettingsWorkspace | null): DerivedWorkspaceSettings {
  const intentConfig = workspace?.playbook_auto_execution_config?.intent_extraction;
  const metadata = workspace?.metadata || {};

  return {
    storage: {
      storageBasePath: workspace?.storage_base_path || '',
      artifactsDir: workspace?.artifacts_dir || 'artifacts',
    },
    execution: {
      executionMode: workspace?.execution_mode || 'hybrid',
      executionPriority: workspace?.execution_priority || 'medium',
      projectAssignmentMode: workspace?.project_assignment_mode || 'auto_silent',
      expectedArtifacts: workspace?.expected_artifacts || [],
    },
    intentExtraction: {
      autoExecute: intentConfig?.auto_execute || false,
      threshold: intentConfig?.confidence_threshold || 0.8,
    },
    sgr: {
      enabled: Boolean(metadata.sgr_enabled || false),
      mode: ((metadata.sgr_mode as SgrMode | undefined) || 'inline'),
    },
  };
}

export function hasStorageSettingsChanged(
  current: WorkspaceStorageValues,
  original: WorkspaceStorageValues,
): boolean {
  return (
    current.storageBasePath !== original.storageBasePath ||
    current.artifactsDir !== original.artifactsDir
  );
}

function sortedArtifacts(artifacts: string[]): string[] {
  return [...artifacts].sort();
}

export function hasExecutionSettingsChanged(
  current: WorkspaceExecutionValues,
  original: WorkspaceExecutionValues,
): boolean {
  return (
    current.executionMode !== original.executionMode ||
    current.executionPriority !== original.executionPriority ||
    current.projectAssignmentMode !== original.projectAssignmentMode ||
    JSON.stringify(sortedArtifacts(current.expectedArtifacts)) !== JSON.stringify(sortedArtifacts(original.expectedArtifacts))
  );
}

export function toggleExpectedArtifact(currentArtifacts: string[], artifact: string): string[] {
  return currentArtifacts.includes(artifact)
    ? currentArtifacts.filter((item) => item !== artifact)
    : [...currentArtifacts, artifact];
}

export function buildIntentExtractionRequestPayload(values: WorkspaceIntentExtractionValues) {
  return {
    playbook_code: 'intent_extraction' as const,
    auto_execute: values.autoExecute,
    confidence_threshold: values.threshold,
  };
}

export function buildSgrSettingsRequestPayload(
  workspace: WorkspaceSettingsWorkspace | null,
  values: WorkspaceSgrValues,
) {
  const currentMeta = workspace?.metadata || {};
  return {
    metadata: {
      ...currentMeta,
      sgr_enabled: values.enabled,
      sgr_mode: values.mode,
    },
  };
}
