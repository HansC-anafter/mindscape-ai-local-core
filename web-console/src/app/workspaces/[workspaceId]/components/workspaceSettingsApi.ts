import type {
  WorkspaceExecutionValues,
  WorkspaceSettingsApiContext,
  WorkspaceSettingsWorkspace,
  WorkspaceStorageValues,
} from './workspaceSettingsTypes';

export function buildWorkspaceSettingsUrl({ apiUrl, workspaceId }: WorkspaceSettingsApiContext): string {
  return `${apiUrl}/api/v1/workspaces/${workspaceId}`;
}

export function buildOpenWorkspaceFolderUrl({ apiUrl, workspaceId }: WorkspaceSettingsApiContext): string {
  return `${apiUrl}/api/v1/workspaces/${workspaceId}/open-folder`;
}

export function buildPlaybookAutoExecConfigUrl({ apiUrl, workspaceId }: WorkspaceSettingsApiContext): string {
  return `${apiUrl}/api/v1/workspaces/${workspaceId}/playbook-auto-exec-config`;
}

async function readErrorMessage(response: Response, fallback: string): Promise<string> {
  const errorData = await response.json().catch(() => ({ detail: fallback }));
  if (errorData && typeof errorData === 'object' && 'detail' in errorData) {
    const detail = (errorData as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }
  }
  return fallback;
}

async function readWorkspaceResponse(response: Response, fallback: string): Promise<WorkspaceSettingsWorkspace> {
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, fallback));
  }
  return response.json();
}

export async function updateWorkspaceExecutionSettings(
  context: WorkspaceSettingsApiContext,
  payload: ReturnType<typeof buildExecutionSettingsRequestPayload>,
): Promise<WorkspaceSettingsWorkspace> {
  const response = await fetch(buildWorkspaceSettingsUrl(context), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return readWorkspaceResponse(response, 'Failed to update execution settings');
}

export async function openWorkspaceFolder(
  context: WorkspaceSettingsApiContext,
  path: string,
): Promise<void> {
  const response = await fetch(buildOpenWorkspaceFolderUrl(context), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
  if (!response.ok) {
    throw new Error('Failed to open folder');
  }
}

export async function updateWorkspaceStorageSettings(
  context: WorkspaceSettingsApiContext,
  payload: ReturnType<typeof buildStorageSettingsRequestPayload>,
): Promise<WorkspaceSettingsWorkspace> {
  const response = await fetch(buildWorkspaceSettingsUrl(context), {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  return readWorkspaceResponse(response, 'Failed to update workspace');
}

export async function updateIntentExtractionSettings(
  context: WorkspaceSettingsApiContext,
  payload: {
    playbook_code: 'intent_extraction';
    auto_execute: boolean;
    confidence_threshold: number;
  },
): Promise<void> {
  const response = await fetch(buildPlaybookAutoExecConfigUrl(context), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, 'Failed to update intent extraction settings'));
  }
}

export async function updateWorkspaceSgrSettings(
  context: WorkspaceSettingsApiContext,
  payload: { metadata: Record<string, unknown> },
): Promise<WorkspaceSettingsWorkspace> {
  const response = await fetch(buildWorkspaceSettingsUrl(context), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return readWorkspaceResponse(response, 'Failed to update SGR settings');
}

export function buildExecutionSettingsRequestPayload(values: WorkspaceExecutionValues) {
  return {
    execution_mode: values.executionMode,
    execution_priority: values.executionPriority,
    project_assignment_mode: values.projectAssignmentMode,
    expected_artifacts: values.expectedArtifacts,
  };
}

export function buildStorageSettingsRequestPayload(values: WorkspaceStorageValues) {
  return {
    storage_base_path: values.storageBasePath.trim(),
    artifacts_dir: values.artifactsDir.trim() || 'artifacts',
  };
}
