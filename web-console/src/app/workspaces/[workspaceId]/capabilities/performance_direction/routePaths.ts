import { buildCapabilityWorkbenchPath } from '@/lib/capability-static-hosts';

export function buildPerformanceDirectionStartPath(workspaceId: string): string {
  return buildCapabilityWorkbenchPath(workspaceId, 'performance_direction', {
    surfacePath: ['start'],
  });
}

export function buildPerformanceDirectionSessionBasePath(workspaceId: string): string {
  return buildCapabilityWorkbenchPath(workspaceId, 'performance_direction', {
    surfacePath: ['sessions'],
  });
}

export function buildPerformanceDirectionSessionPath(
  workspaceId: string,
  sessionId: string,
): string {
  return `${buildPerformanceDirectionSessionBasePath(workspaceId)}/${encodeURIComponent(sessionId)}`;
}
