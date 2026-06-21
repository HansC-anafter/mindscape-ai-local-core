import { getApiBaseUrl } from '@/lib/api-url';

import type { AgentsStatusSnapshot, HostServiceStatus } from './integratedSystemStatusTypes';
import { HOST_SERVICE_TIMEOUT_MS } from './integratedSystemStatusTypes';

type StatusFetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const emptyAgentsSnapshot: AgentsStatusSnapshot = {
  agents: [],
  bridgeScriptPath: null,
};

export const buildWorkspaceAgentsUrl = (apiUrl: string, workspaceId: string) =>
  `${apiUrl}/api/v1/workspaces/${workspaceId}/agents`;

export const buildXttsHealthUrl = (apiUrl: string) =>
  `${apiUrl}/api/v1/host/services/xtts/health`;

export const buildMcpGatewayHealthUrl = (apiUrl: string) =>
  `${apiUrl}/api/v1/host/services/mcp-gateway/health`;

export const shouldSkipBackgroundPoll = () =>
  typeof document !== 'undefined' && document.visibilityState === 'hidden';

const timeoutInit = (): RequestInit | undefined => {
  if (typeof AbortSignal === 'undefined' || typeof AbortSignal.timeout !== 'function') {
    return undefined;
  }
  return { signal: AbortSignal.timeout(HOST_SERVICE_TIMEOUT_MS) };
};

const readJson = async (response: Response): Promise<Record<string, unknown>> => {
  const payload = await response.json();
  return payload && typeof payload === 'object' && !Array.isArray(payload)
    ? payload as Record<string, unknown>
    : {};
};

export const fetchAgentsStatus = async (
  workspaceId: string,
  apiUrl = getApiBaseUrl(),
  fetchImpl: StatusFetch = fetch,
): Promise<AgentsStatusSnapshot | null> => {
  try {
    const response = await fetchImpl(buildWorkspaceAgentsUrl(apiUrl, workspaceId));
    if (!response.ok) {
      return null;
    }

    const data = await readJson(response);
    return {
      agents: Array.isArray(data.agents) ? data.agents as AgentsStatusSnapshot['agents'] : [],
      bridgeScriptPath: typeof data.bridge_script_path === 'string' ? data.bridge_script_path : null,
    };
  } catch {
    return null;
  }
};

const fetchXttsStatus = async (
  apiUrl: string,
  fetchImpl: StatusFetch,
): Promise<HostServiceStatus> => {
  try {
    const response = await fetchImpl(buildXttsHealthUrl(apiUrl), timeoutInit());
    if (!response.ok) {
      return { name: 'XTTS Service', ok: false, detail: 'unreachable' };
    }

    const data = await readJson(response);
    return {
      name: 'XTTS Service',
      ok: data.status === 'ok',
      detail: data.model_loaded ? 'model loaded' : 'model not loaded',
    };
  } catch {
    return { name: 'XTTS Service', ok: false, detail: 'unreachable' };
  }
};

const fetchMcpGatewayStatus = async (
  apiUrl: string,
  fetchImpl: StatusFetch,
): Promise<HostServiceStatus> => {
  try {
    const response = await fetchImpl(buildMcpGatewayHealthUrl(apiUrl), timeoutInit());
    return {
      name: 'MCP Gateway',
      ok: response.ok,
      detail: response.ok ? 'running' : 'not running',
    };
  } catch {
    return { name: 'MCP Gateway', ok: false, detail: 'unreachable' };
  }
};

export const fetchHostServicesStatus = async (
  apiUrl = getApiBaseUrl(),
  fetchImpl: StatusFetch = fetch,
): Promise<HostServiceStatus[]> => [
  await fetchXttsStatus(apiUrl, fetchImpl),
  await fetchMcpGatewayStatus(apiUrl, fetchImpl),
];

export const emptyIntegratedAgentsSnapshot = () => ({ ...emptyAgentsSnapshot });
