/**
 * Sandbox API Client
 * Provides API functions for sandbox management, file operations, and version control
 */

const API_URL = typeof window !== 'undefined'
  ? (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000')
  : 'http://localhost:8000';

export interface Sandbox {
  sandbox_id: string;
  sandbox_type: string;
  workspace_id: string;
  current_version?: string;
  metadata?: Record<string, any>;
}

export interface SandboxFile {
  path: string;
  size: number;
  modified: number;
  type: string;
}

export interface SandboxFileContent {
  content: string;
  path: string;
  size: number;
  modified?: number;
}

export interface VersionMetadata {
  created_at: string;
  file_count: number;
  total_size: number;
  source_version?: string;
}

export interface CreateSandboxRequest {
  sandbox_type: string;
  context?: Record<string, any>;
}

export interface CreateVersionRequest {
  version: string;
  source_version?: string;
}

/**
 * List all sandboxes in workspace
 */
export async function listSandboxes(
  workspaceId: string,
  sandboxType?: string
): Promise<Sandbox[]> {
  const params = new URLSearchParams();
  if (sandboxType) {
    params.append('sandbox_type', sandboxType);
  }

  const response = await fetch(
    `${API_URL}/api/v1/workspaces/${workspaceId}/sandboxes?${params}`
  );
  if (!response.ok) {
    throw new Error(`Failed to list sandboxes: ${response.statusText}`);
  }
  return await response.json();
}

/**
 * Create a new sandbox
 */
export async function createSandbox(
  workspaceId: string,
  request: CreateSandboxRequest
): Promise<{ sandbox_id: string }> {
  const response = await fetch(
    `${API_URL}/api/v1/workspaces/${workspaceId}/sandboxes`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    }
  );
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to create sandbox: ${response.statusText}`);
  }
  return await response.json();
}

/**
 * Get sandbox details
 */
export async function getSandbox(
  workspaceId: string,
  sandboxId: string
): Promise<Sandbox> {
  const response = await fetch(
    `${API_URL}/api/v1/workspaces/${workspaceId}/sandboxes/${sandboxId}`
  );
  if (!response.ok) {
    throw new Error(`Failed to get sandbox: ${response.statusText}`);
  }
  return await response.json();
}

/**
 * Delete sandbox
 */
export async function deleteSandbox(
  workspaceId: string,
  sandboxId: string
): Promise<void> {
  const response = await fetch(
    `${API_URL}/api/v1/workspaces/${workspaceId}/sandboxes/${sandboxId}`,
    {
      method: 'DELETE',
    }
  );
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to delete sandbox: ${response.statusText}`);
  }
}

/**
 * List files in sandbox
 */
export async function listSandboxFiles(
  workspaceId: string,
  sandboxId: string,
  directory: string = '',
  version?: string,
  recursive: boolean = true
): Promise<SandboxFile[]> {
  const params = new URLSearchParams({
    directory,
    recursive: recursive.toString(),
  });
  if (version) {
    params.append('version', version);
  }

  const response = await fetch(
    `${API_URL}/api/v1/workspaces/${workspaceId}/sandboxes/${sandboxId}/files?${params}`
  );
  if (!response.ok) {
    throw new Error(`Failed to list files: ${response.statusText}`);
  }
  return await response.json();
}

/**
 * Get file content
 */
export async function getSandboxFileContent(
  workspaceId: string,
  sandboxId: string,
  filePath: string,
  version?: string
): Promise<SandboxFileContent> {
  const params = new URLSearchParams();
  if (version) {
    params.append('version', version);
  }

  const response = await fetch(
    `${API_URL}/api/v1/workspaces/${workspaceId}/sandboxes/${sandboxId}/files/${filePath}?${params}`
  );
  if (!response.ok) {
    throw new Error(`Failed to get file content: ${response.statusText}`);
  }
  return await response.json();
}

/**
 * Create a new version
 */
export async function createVersion(
  workspaceId: string,
  sandboxId: string,
  request: CreateVersionRequest
): Promise<{ version: string }> {
  const response = await fetch(
    `${API_URL}/api/v1/workspaces/${workspaceId}/sandboxes/${sandboxId}/versions`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    }
  );
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to create version: ${response.statusText}`);
  }
  return await response.json();
}

/**
 * List all versions
 */
export async function listVersions(
  workspaceId: string,
  sandboxId: string
): Promise<string[]> {
  const response = await fetch(
    `${API_URL}/api/v1/workspaces/${workspaceId}/sandboxes/${sandboxId}/versions`
  );
  if (!response.ok) {
    throw new Error(`Failed to list versions: ${response.statusText}`);
  }
  return await response.json();
}

/**
 * Get version metadata
 */
export async function getVersionMetadata(
  workspaceId: string,
  sandboxId: string,
  version: string
): Promise<VersionMetadata> {
  const response = await fetch(
    `${API_URL}/api/v1/workspaces/${workspaceId}/sandboxes/${sandboxId}/versions/${version}`
  );
  if (!response.ok) {
    throw new Error(`Failed to get version metadata: ${response.statusText}`);
  }
  return await response.json();
}

/**
 * Get sandbox by project ID
 */
export async function getSandboxByProject(
  workspaceId: string,
  projectId: string
): Promise<Sandbox | null> {
  const response = await fetch(
    `${API_URL}/api/v1/workspaces/${workspaceId}/sandboxes/by-project/${projectId}`
  );
  if (!response.ok) {
    if (response.status === 404) {
      return null;
    }
    throw new Error(`Failed to get sandbox by project: ${response.statusText}`);
  }
  const data = await response.json();
  return data || null;
}

