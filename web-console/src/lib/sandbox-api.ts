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

export interface PreviewServerStatus {
  success: boolean;
  port: number | null;
  url: string | null;
  error: string | null;
  port_conflict: boolean;
  message?: string;
}

export interface EnsurePreviewResult {
  success: boolean;
  sandbox_id: string | null;
  preview_url: string | null;
  port: number | null;
  synced_files: string[];
  status: 'ready' | 'error' | 'synced' | 'created';
  error?: string | null;
  port_conflict?: boolean;
}

/**
 * Ensure preview is ready (one-click preview setup)
 * 
 * This is the main entry point for preview. It will:
 * 1. Find or create a web_page sandbox
 * 2. Sync workspace files to sandbox
 * 3. Initialize Next.js template if needed
 * 4. Start preview server
 */
export async function ensurePreviewReady(
  workspaceId: string,
  projectId?: string,
  port: number = 3000
): Promise<EnsurePreviewResult> {
  const response = await fetch(
    `${API_URL}/api/v1/workspaces/${workspaceId}/sandboxes/preview/ensure`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, port }),
    }
  );
  if (!response.ok) {
    const error = await response.json();
    return {
      success: false,
      sandbox_id: null,
      preview_url: null,
      port: null,
      synced_files: [],
      status: 'error',
      error: error.detail || 'Failed to ensure preview',
    };
  }
  return response.json();
}

export async function startPreviewServer(
  workspaceId: string,
  sandboxId: string,
  port: number = 3000
): Promise<PreviewServerStatus> {
  const response = await fetch(
    `${API_URL}/api/v1/workspaces/${workspaceId}/sandboxes/${sandboxId}/preview/start`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ port }),
    }
  );
  if (!response.ok) {
    const error = await response.json();
    return {
      success: false,
      port: null,
      url: null,
      error: error.detail || 'Failed to start preview server',
      port_conflict: false,
    };
  }
  return response.json();
}

export async function stopPreviewServer(
  workspaceId: string,
  sandboxId: string
): Promise<{ success: boolean }> {
  const response = await fetch(
    `${API_URL}/api/v1/workspaces/${workspaceId}/sandboxes/${sandboxId}/preview/stop`,
    {
      method: 'POST',
    }
  );
  if (!response.ok) {
    throw new Error('Failed to stop preview server');
  }
  return response.json();
}

export async function getPreviewServerStatus(
  workspaceId: string,
  sandboxId: string
): Promise<{
  running: boolean;
  port: number | null;
  url: string | null;
  error: string | null;
}> {
  const response = await fetch(
    `${API_URL}/api/v1/workspaces/${workspaceId}/sandboxes/${sandboxId}/preview/status`
  );
  if (!response.ok) {
    return {
      running: false,
      port: null,
      url: null,
      error: 'Failed to get preview server status',
    };
  }
  return response.json();
}

