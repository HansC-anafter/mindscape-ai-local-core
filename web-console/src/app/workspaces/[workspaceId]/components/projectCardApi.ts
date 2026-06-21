import { sharedGetFetch } from '@/lib/resilient-fetch';
import type { ProjectCardApiContext, ProjectCardData } from './projectCardTypes';

export function buildProjectCardUrl({ apiUrl, workspaceId, projectId }: ProjectCardApiContext): string {
  return `${apiUrl}/api/v1/workspaces/${workspaceId}/projects/${projectId}/card`;
}

export function buildProjectCardDedupKey({ workspaceId, projectId }: Pick<ProjectCardApiContext, 'workspaceId' | 'projectId'>): string {
  return `workspace-project-card:${workspaceId}:${projectId}`;
}

export function buildProjectUrl({ apiUrl, workspaceId, projectId }: ProjectCardApiContext): string {
  return `${apiUrl}/api/v1/workspaces/${workspaceId}/projects/${projectId}`;
}

export function buildMeetingSessionUrl(apiUrl: string, workspaceId: string, sessionId: string): string {
  return `${apiUrl}/api/v1/workspaces/${workspaceId}/meeting-sessions/${sessionId}`;
}

export function buildActiveMeetingSessionUrl({ apiUrl, workspaceId, projectId }: ProjectCardApiContext): string {
  return `${apiUrl}/api/v1/workspaces/${workspaceId}/meeting-sessions/active?project_id=${projectId}`;
}

export function buildStartMeetingSessionUrl(apiUrl: string, workspaceId: string): string {
  return `${apiUrl}/api/v1/workspaces/${workspaceId}/meeting-sessions/start`;
}

export function buildWorkspaceChatUrl(apiUrl: string, workspaceId: string): string {
  return `${apiUrl}/api/v1/workspaces/${workspaceId}/chat`;
}

export async function loadProjectCardWithSharedFetch(
  context: ProjectCardApiContext,
  signal: AbortSignal,
): Promise<ProjectCardData> {
  const response = await sharedGetFetch(buildProjectCardUrl(context), {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
    },
    signal,
    credentials: 'include',
  }, { dedupKey: buildProjectCardDedupKey(context) });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${response.statusText} - ${text}`);
  }
  return response.json();
}

export async function fetchProjectCard(context: ProjectCardApiContext): Promise<ProjectCardData | null> {
  const response = await fetch(buildProjectCardUrl(context), {
    method: 'GET',
    headers: { 'Accept': 'application/json' },
    credentials: 'include',
  });
  return response.ok ? response.json() : null;
}

export async function loadMeetingSession(
  apiUrl: string,
  workspaceId: string,
  sessionId: string,
): Promise<any> {
  const response = await fetch(buildMeetingSessionUrl(apiUrl, workspaceId, sessionId), {
    method: 'GET',
    headers: { Accept: 'application/json' },
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error(`Failed to load meeting session: ${response.status}`);
  }
  return response.json();
}

export async function updateProjectMeetingFlag(
  context: ProjectCardApiContext,
  enabled: boolean,
): Promise<void> {
  const response = await fetch(buildProjectUrl(context), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ meeting_enabled: enabled }),
  });
  if (!response.ok) {
    throw new Error(`Failed to update meeting flag: ${response.status}`);
  }
}

export async function fetchActiveMeetingSession(
  context: ProjectCardApiContext,
): Promise<{ status: number; id?: string }> {
  const response = await fetch(buildActiveMeetingSessionUrl(context), { method: 'GET' });
  if (response.ok) {
    const active = await response.json();
    return { status: response.status, id: active.id };
  }
  return { status: response.status };
}

export async function startMeetingSession(
  apiUrl: string,
  workspaceId: string,
  payload: { project_id: string; thread_id: string | null },
): Promise<{ id?: string } | null> {
  const response = await fetch(buildStartMeetingSessionUrl(apiUrl, workspaceId), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return response.ok ? response.json() : null;
}

export async function postMeetingChatMessage(
  apiUrl: string,
  workspaceId: string,
  payload: { message: string; project_id: string; thread_id?: string },
): Promise<void> {
  await fetch(buildWorkspaceChatUrl(apiUrl, workspaceId), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}
