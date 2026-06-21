import { getApiBaseUrl } from '../../../../lib/api-url';
import type { CreatedWorkspace, LaunchpadData, WorkspaceWizardData } from './workspaceHomeTypes';

export const API_URL = getApiBaseUrl();
export const DEFAULT_OWNER_USER_ID = 'default-user';
export const TEXT_SEED_LOCALE = 'zh-TW';

const jsonHeaders = { 'Content-Type': 'application/json' };

interface WorkspaceCreatePayload {
  title?: string;
  description: string;
  execution_mode: 'hybrid';
}

interface WorkspaceSeedPayload {
  seed_type: 'text';
  payload: string;
  locale: typeof TEXT_SEED_LOCALE;
}

export function resolveApiBaseUrl(apiBaseUrl = API_URL): string {
  return apiBaseUrl.startsWith('http') ? apiBaseUrl : '';
}

export function buildLaunchpadUrl(workspaceId: string, apiBaseUrl = API_URL): string {
  const apiUrl = resolveApiBaseUrl(apiBaseUrl);
  return `${apiUrl}/api/v1/workspaces/${workspaceId}/launchpad`;
}

export function buildWorkspaceCreateUrl(
  ownerUserId = DEFAULT_OWNER_USER_ID,
  apiBaseUrl = API_URL
): string {
  const apiUrl = resolveApiBaseUrl(apiBaseUrl);
  return `${apiUrl}/api/v1/workspaces?owner_user_id=${ownerUserId}`;
}

export function buildWorkspaceSeedUrl(workspaceId: string | number, apiBaseUrl = API_URL): string {
  const apiUrl = resolveApiBaseUrl(apiBaseUrl);
  return `${apiUrl}/api/v1/workspaces/${workspaceId}/seed`;
}

export function createEmptyLaunchpadData(): LaunchpadData {
  return {
    brief: null,
    initial_intents: [],
    first_playbook: null,
    tool_connections: [],
    launch_status: 'pending',
  };
}

export function buildWorkspaceCreatePayload(wizardData: WorkspaceWizardData): WorkspaceCreatePayload {
  return {
    title: wizardData.title,
    description: wizardData.description || '',
    execution_mode: 'hybrid',
  };
}

export function buildTextSeedPayload(seedText: string, trimPayload: boolean): WorkspaceSeedPayload {
  return {
    seed_type: 'text',
    payload: trimPayload ? seedText.trim() : seedText,
    locale: TEXT_SEED_LOCALE,
  };
}

async function readErrorPayload(response: Response): Promise<{ detail?: string; message?: string }> {
  try {
    return await response.json();
  } catch {
    return { detail: response.statusText };
  }
}

export async function readWorkspaceResponseError(response: Response, fallback: string): Promise<string> {
  const errorData = await readErrorPayload(response);
  return errorData.detail || errorData.message || fallback;
}

export async function fetchWorkspaceLaunchpad(workspaceId: string): Promise<LaunchpadData> {
  const response = await fetch(buildLaunchpadUrl(workspaceId));
  if (!response.ok) {
    if (response.status === 404) {
      return createEmptyLaunchpadData();
    }
    const errorData = await readErrorPayload(response);
    throw new Error(errorData.detail || `Failed to fetch launchpad data`);
  }
  return await response.json();
}

export async function createWorkspaceFromWizard(
  wizardData: WorkspaceWizardData,
  ownerUserId = DEFAULT_OWNER_USER_ID
): Promise<CreatedWorkspace> {
  const response = await fetch(buildWorkspaceCreateUrl(ownerUserId), {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(buildWorkspaceCreatePayload(wizardData)),
  });

  if (!response.ok) {
    const errorData = await readErrorPayload(response);
    throw new Error(errorData.detail || errorData.message || `Failed to create workspace: ${response.status}`);
  }

  return await response.json();
}

export async function postWorkspaceSeed(
  workspaceId: string | number,
  seedText: string,
  options: { trimPayload: boolean }
): Promise<Response> {
  return await fetch(buildWorkspaceSeedUrl(workspaceId), {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(buildTextSeedPayload(seedText, options.trimPayload)),
  });
}
