/**
 * Deployment API Client
 * Provides API functions for deploying sandbox projects
 */

const API_URL = typeof window !== 'undefined'
  ? (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000')
  : 'http://localhost:8000';

export interface DeployRequest {
  sandbox_id: string;
  target_path: string;
  files?: string[];
  git_branch?: string;
  commit_message?: string;
  auto_commit?: boolean;
  auto_push?: boolean;
}

export interface DeployResponse {
  status: string;
  files_copied?: string[];
  git_commands?: {
    executed: boolean;
    commands: string[];
    branch?: string;
    commit_message?: string;
  };
  vm_commands?: string[];
  error?: string;
}

/**
 * Deploy sandbox project to target path
 */
export async function deployProject(
  workspaceId: string,
  projectId: string,
  request: DeployRequest
): Promise<DeployResponse> {
  const response = await fetch(
    `${API_URL}/api/v1/workspaces/${workspaceId}/projects/${projectId}/deploy`,
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
    throw new Error(error.detail || `Failed to deploy: ${response.statusText}`);
  }

  return await response.json();
}

