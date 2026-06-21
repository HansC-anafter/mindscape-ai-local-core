import { getApiBaseUrl } from '../../lib/api-url';

export const API_URL = getApiBaseUrl();
export const DEFAULT_AGENTS_PROFILE_ID = 'default-user';

const jsonHeaders = { 'Content-Type': 'application/json' };

interface BackendConfigResponse {
  current_mode?: string;
  available_backends?: Record<string, { available?: boolean } | undefined>;
}

interface SuggestedPlaybookResponse {
  metadata: {
    playbook_code: string;
  };
}

export interface BackendAvailabilityResult {
  backendAvailable: boolean;
  missingApiKey: boolean;
}

export interface RunAgentPayload {
  task: string;
  agentType: string;
  agentTypeDescription?: string;
  useMindscape: boolean;
}

export interface RunAllAgentsPayload {
  task: string;
  useMindscape: boolean;
}

export function resolveAgentsApiBaseUrl(apiBaseUrl = API_URL): string {
  return apiBaseUrl.startsWith('http') ? apiBaseUrl : '';
}

export function buildBackendConfigUrl(
  profileId = DEFAULT_AGENTS_PROFILE_ID,
  apiBaseUrl = API_URL
): string {
  const apiUrl = resolveAgentsApiBaseUrl(apiBaseUrl);
  return `${apiUrl}/api/v1/config/backend?profile_id=${profileId}`;
}

export function buildPlaybooksUrl(apiBaseUrl = API_URL): string {
  const apiUrl = resolveAgentsApiBaseUrl(apiBaseUrl);
  return `${apiUrl}/api/v1/playbooks`;
}

export function buildRunAgentUrl(
  profileId = DEFAULT_AGENTS_PROFILE_ID,
  apiBaseUrl = API_URL
): string {
  const apiUrl = resolveAgentsApiBaseUrl(apiBaseUrl);
  return `${apiUrl}/api/v1/agent/run?profile_id=${profileId}`;
}

export function buildRunAllAgentsUrl(
  profileId = DEFAULT_AGENTS_PROFILE_ID,
  apiBaseUrl = API_URL
): string {
  const apiUrl = resolveAgentsApiBaseUrl(apiBaseUrl);
  return `${apiUrl}/api/v1/agent/run-all?profile_id=${profileId}`;
}

async function readErrorDetail(response: Response, fallbackMessage: string): Promise<string> {
  try {
    const errorData = await response.json();
    return errorData?.detail || fallbackMessage;
  } catch {
    return fallbackMessage;
  }
}

export async function loadBackendAvailability(
  apiBaseUrl = API_URL,
  profileId = DEFAULT_AGENTS_PROFILE_ID
): Promise<BackendAvailabilityResult | null> {
  const response = await fetch(buildBackendConfigUrl(profileId, apiBaseUrl), {
    headers: jsonHeaders,
  });

  if (!response.ok) {
    return null;
  }

  const config = await response.json() as BackendConfigResponse;
  const currentBackend = config.available_backends?.[config.current_mode || ''];
  const backendAvailable = currentBackend?.available || false;

  return {
    backendAvailable,
    missingApiKey: !currentBackend?.available,
  };
}

export async function loadSuggestedPlaybookCodes(
  apiBaseUrl = API_URL
): Promise<string[] | null> {
  const response = await fetch(buildPlaybooksUrl(apiBaseUrl), {
    headers: jsonHeaders,
  });

  if (!response.ok) {
    return null;
  }

  const playbooks = await response.json() as SuggestedPlaybookResponse[];
  return playbooks.slice(0, 3).map((playbook) => playbook.metadata.playbook_code);
}

export async function runAgentRequest(
  payload: RunAgentPayload,
  profileId = DEFAULT_AGENTS_PROFILE_ID,
  apiBaseUrl = API_URL
): Promise<any> {
  const response = await fetch(buildRunAgentUrl(profileId, apiBaseUrl), {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({
      task: payload.task,
      agent_type: payload.agentType,
      agent_type_description: payload.agentTypeDescription || undefined,
      use_mindscape: payload.useMindscape,
      intent_ids: [],
    }),
  });

  if (!response.ok) {
    throw new Error(await readErrorDetail(response, 'Failed to run agent'));
  }

  return await response.json();
}

export async function runAllAgentsRequest(
  payload: RunAllAgentsPayload,
  profileId = DEFAULT_AGENTS_PROFILE_ID,
  apiBaseUrl = API_URL
): Promise<any[]> {
  const response = await fetch(buildRunAllAgentsUrl(profileId, apiBaseUrl), {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({
      task: payload.task,
      agent_type: 'planner',
      use_mindscape: payload.useMindscape,
      intent_ids: [],
    }),
  });

  if (!response.ok) {
    throw new Error(await readErrorDetail(response, 'Failed to run all agents'));
  }

  return await response.json() as any[];
}
