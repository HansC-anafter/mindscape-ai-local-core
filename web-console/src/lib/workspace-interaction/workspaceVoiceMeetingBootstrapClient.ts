import type { MeetingVoiceCommandContext } from '@/lib/meeting-voice/voiceTurnClient';

export type WorkspaceVoiceMeetingSession = {
  id: string;
  workspace_id: string;
  project_id: string | null;
  thread_id: string | null;
  status: string;
  is_active: boolean;
  metadata: Record<string, unknown>;
};

export type WorkspaceVoiceMeetingScope = {
  projectId: 'workspace_voice';
  threadId: string;
  capabilityCode: string | null;
};

export type EnsureWorkspaceVoiceMeetingSessionInput = {
  apiUrl: string;
  workspaceId: string;
  activeCapabilityCode: string | null;
  fetchImpl?: typeof fetch;
};

const WORKSPACE_VOICE_PROJECT_ID = 'workspace_voice';

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}
function normalizeCapabilityCode(value: string | null): string | null {
  const normalized = String(value || '').trim();
  return normalized || null;
}

function scopeToken(value: string | null): string {
  const normalized = String(value || 'workspace')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '_')
    .replace(/^_+|_+$/g, '');
  return normalized || 'workspace';
}

export function buildWorkspaceVoiceMeetingScope(
  activeCapabilityCode: string | null,
): WorkspaceVoiceMeetingScope {
  const capabilityCode = normalizeCapabilityCode(activeCapabilityCode);
  return {
    projectId: WORKSPACE_VOICE_PROJECT_ID,
    threadId: `workspace_voice_${scopeToken(capabilityCode)}`,
    capabilityCode,
  };
}

function readSession(
  value: unknown,
  expected: {
    workspaceId: string;
    scope: WorkspaceVoiceMeetingScope;
  },
): WorkspaceVoiceMeetingSession {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('workspace_voice_meeting_session_invalid');
  }
  const session = value as Record<string, unknown>;
  if (
    typeof session.id !== 'string'
    || session.id.trim().length === 0
    || session.workspace_id !== expected.workspaceId
    || session.project_id !== expected.scope.projectId
    || session.thread_id !== expected.scope.threadId
    || session.is_active !== true
  ) {
    throw new Error('workspace_voice_meeting_session_invalid');
  }
  return {
    id: session.id,
    workspace_id: expected.workspaceId,
    project_id: expected.scope.projectId,
    thread_id: expected.scope.threadId,
    status: typeof session.status === 'string' ? session.status : 'active',
    is_active: true,
    metadata: session.metadata && typeof session.metadata === 'object'
      && !Array.isArray(session.metadata)
      ? session.metadata as Record<string, unknown>
      : {},
  };
}

async function readJson(response: Response): Promise<unknown> {
  return response.json().catch(() => ({}));
}

export async function ensureWorkspaceVoiceMeetingSession({
  apiUrl,
  workspaceId,
  activeCapabilityCode,
  fetchImpl = fetch,
}: EnsureWorkspaceVoiceMeetingSessionInput): Promise<WorkspaceVoiceMeetingSession> {
  const scope = buildWorkspaceVoiceMeetingScope(activeCapabilityCode);
  const baseUrl = trimTrailingSlash(apiUrl);
  const route = `${baseUrl}/api/v1/workspaces/${encodeURIComponent(workspaceId)}`
    + '/meeting-sessions';
  const query = new URLSearchParams({
    project_id: scope.projectId,
    thread_id: scope.threadId,
  });
  const activeResponse = await fetchImpl(`${route}/active?${query.toString()}`, {
    method: 'GET',
    cache: 'no-store',
    credentials: 'same-origin',
  });
  if (activeResponse.ok) {
    return readSession(await readJson(activeResponse), { workspaceId, scope });
  }
  if (activeResponse.status !== 404) {
    throw new Error(`workspace_voice_meeting_lookup_failed_${activeResponse.status}`);
  }

  const metadata: Record<string, unknown> = {
    source_surface: 'workspace_global_voice',
    voice_bootstrap: true,
  };
  if (scope.capabilityCode) {
    metadata.active_capability_code = scope.capabilityCode;
    metadata.active_pack_code = scope.capabilityCode;
  }
  const startResponse = await fetchImpl(`${route}/start`, {
    method: 'POST',
    cache: 'no-store',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      project_id: scope.projectId,
      thread_id: scope.threadId,
      meeting_type: 'workspace_voice',
      agenda: ['Route workspace voice through the Meeting semantic facade.'],
      success_criteria: [
        'Produce one grounded action, answer, or clarification without a second writer.',
      ],
      max_rounds: 5,
      metadata,
      operation_type: 'generate',
      execution_backend: 'local',
    }),
  });
  if (!startResponse.ok) {
    throw new Error(`workspace_voice_meeting_start_failed_${startResponse.status}`);
  }
  return readSession(await readJson(startResponse), { workspaceId, scope });
}

export function buildWorkspaceVoiceMeetingCommandContext(
  session: WorkspaceVoiceMeetingSession,
  activeCapabilityCode: string | null,
): MeetingVoiceCommandContext {
  const capabilityCode = normalizeCapabilityCode(activeCapabilityCode);
  const metadata: Record<string, unknown> = {
    source_surface: 'workspace_global_voice',
    voice_bootstrap: true,
  };
  if (capabilityCode) {
    metadata.active_capability_code = capabilityCode;
    metadata.active_pack_code = capabilityCode;
  }
  return {
    context_objects: [],
    requested_action: null,
    expected_outputs: [
      'grounded_material',
      'grounded_answer',
      'client_action',
      'clarification',
    ],
    write_mode: 'recommendation_only',
    thread_id: session.thread_id,
    meeting_mentions: [],
    metadata,
  };
}
