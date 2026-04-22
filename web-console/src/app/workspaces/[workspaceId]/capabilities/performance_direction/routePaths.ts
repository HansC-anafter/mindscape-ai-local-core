export function buildPerformanceDirectionStartPath(workspaceId: string): string {
  return `/workspaces/${encodeURIComponent(workspaceId)}/capabilities/performance_direction/start`;
}

export function buildPerformanceDirectionSessionBasePath(workspaceId: string): string {
  return `/workspaces/${encodeURIComponent(workspaceId)}/capabilities/performance_direction/sessions`;
}

export function buildPerformanceDirectionSessionPath(
  workspaceId: string,
  sessionId: string,
): string {
  return `${buildPerformanceDirectionSessionBasePath(workspaceId)}/${encodeURIComponent(sessionId)}`;
}
