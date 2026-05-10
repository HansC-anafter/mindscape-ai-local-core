export function buildPerformanceDirectionStartPath(workspaceId: string): string {
  return `/capability-ui-hosts/performance_direction/${encodeURIComponent(workspaceId)}/start`;
}

export function buildPerformanceDirectionSessionBasePath(workspaceId: string): string {
  return `/capability-ui-hosts/performance_direction/${encodeURIComponent(workspaceId)}/sessions`;
}

export function buildPerformanceDirectionSessionPath(
  workspaceId: string,
  sessionId: string,
): string {
  return `${buildPerformanceDirectionSessionBasePath(workspaceId)}/${encodeURIComponent(sessionId)}`;
}
