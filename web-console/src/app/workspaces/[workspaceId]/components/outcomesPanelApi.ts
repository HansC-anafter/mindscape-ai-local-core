import type { Artifact } from './outcomesPanelTypes';

const artifactListRequests = new Map<string, Promise<Artifact[]>>();

export const buildArtifactListUrl = (apiUrl: string, workspaceId: string): string => {
  const params = new URLSearchParams({
    include_content: 'false',
    include_preview: 'false',
    limit: '100',
  });
  return `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts?${params.toString()}`;
};

export const buildArtifactCopyUrl = (
  apiUrl: string,
  workspaceId: string,
  artifactId: string,
  force = false,
): string => {
  const suffix = force ? '?force=true' : '';
  return `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts/${artifactId}/copy${suffix}`;
};

export const buildArtifactExternalUrl = (
  apiUrl: string,
  workspaceId: string,
  artifactId: string,
): string => `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts/${artifactId}/external-url`;

export const buildArtifactFileUrl = (
  apiUrl: string,
  workspaceId: string,
  artifactId: string,
): string => `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts/${artifactId}/file`;

export const buildCapabilityComponentUrl = (
  workspaceId: string,
  capabilityCode: string,
  componentCode: string,
): string =>
  `/workspaces/${workspaceId}/capabilities/${capabilityCode}/ui?component=${encodeURIComponent(componentCode)}`;

export const buildExecutionDetailUrl = (
  workspaceId: string,
  executionId: string,
): string => `/workspaces/${workspaceId}/executions/${executionId}`;

export const buildExecutionSandboxUrl = (
  workspaceId: string,
  sandboxId: string,
): string => `/workspaces/${workspaceId}/executions?sandbox=${sandboxId}`;

export const clearArtifactListRequestCache = () => {
  artifactListRequests.clear();
};

export const fetchWorkspaceArtifacts = (
  apiUrl: string,
  workspaceId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<Artifact[]> => {
  const requestKey = `${apiUrl}|${workspaceId}`;
  const existingRequest = artifactListRequests.get(requestKey);
  if (existingRequest) {
    return existingRequest;
  }

  const request = fetchImpl(buildArtifactListUrl(apiUrl, workspaceId))
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`Failed to load artifacts: ${response.statusText}`);
      }
      const data = await response.json();
      return data.artifacts || data || [];
    })
    .finally(() => {
      artifactListRequests.delete(requestKey);
    });

  artifactListRequests.set(requestKey, request);
  return request;
};
