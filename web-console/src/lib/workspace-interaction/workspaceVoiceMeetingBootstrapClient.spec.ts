import { describe, expect, it, vi } from 'vitest';

import {
  buildWorkspaceVoiceMeetingCommandContext,
  buildWorkspaceVoiceMeetingScope,
  ensureWorkspaceVoiceMeetingSession,
} from './workspaceVoiceMeetingBootstrapClient';

function response(
  status: number,
  body: Record<string, unknown>,
): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

const session = {
  id: 'meeting_voice_1',
  workspace_id: 'ws_1',
  project_id: 'workspace_voice',
  thread_id: 'workspace_voice_yogacoach',
  status: 'active',
  is_active: true,
  metadata: {
    source_surface: 'workspace_global_voice',
    active_pack_code: 'yogacoach',
  },
};

describe('workspaceVoiceMeetingBootstrapClient', () => {
  it('builds one stable Workspace/capability Meeting scope', () => {
    expect(buildWorkspaceVoiceMeetingScope(' YogaCoach ')).toEqual({
      projectId: 'workspace_voice',
      threadId: 'workspace_voice_yogacoach',
      capabilityCode: 'YogaCoach',
    });
    expect(buildWorkspaceVoiceMeetingScope(null).threadId).toBe(
      'workspace_voice_workspace',
    );
  });

  it('reuses one active scoped Meeting session without starting another', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(response(200, session));

    const result = await ensureWorkspaceVoiceMeetingSession({
      apiUrl: 'http://api.test/',
      workspaceId: 'ws_1',
      activeCapabilityCode: 'yogacoach',
      fetchImpl,
    });

    expect(result.id).toBe('meeting_voice_1');
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(fetchImpl.mock.calls[0][0]).toBe(
      'http://api.test/api/v1/workspaces/ws_1/meeting-sessions/active'
      + '?project_id=workspace_voice&thread_id=workspace_voice_yogacoach',
    );
  });

  it('starts exactly once after a scoped 404 and freezes capability metadata', async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(response(404, { detail: 'not found' }))
      .mockResolvedValueOnce(response(200, session));

    const result = await ensureWorkspaceVoiceMeetingSession({
      apiUrl: 'http://api.test',
      workspaceId: 'ws_1',
      activeCapabilityCode: 'yogacoach',
      fetchImpl,
    });

    expect(result.id).toBe('meeting_voice_1');
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    const [startUrl, startInit] = fetchImpl.mock.calls[1];
    expect(startUrl).toBe(
      'http://api.test/api/v1/workspaces/ws_1/meeting-sessions/start',
    );
    expect(startInit.method).toBe('POST');
    expect(JSON.parse(startInit.body)).toMatchObject({
      project_id: 'workspace_voice',
      thread_id: 'workspace_voice_yogacoach',
      meeting_type: 'workspace_voice',
      metadata: {
        source_surface: 'workspace_global_voice',
        voice_bootstrap: true,
        active_capability_code: 'yogacoach',
        active_pack_code: 'yogacoach',
      },
    });
  });

  it('fails closed on non-404 lookup errors and invalid identities', async () => {
    await expect(ensureWorkspaceVoiceMeetingSession({
      apiUrl: 'http://api.test',
      workspaceId: 'ws_1',
      activeCapabilityCode: 'yogacoach',
      fetchImpl: vi.fn().mockResolvedValue(response(503, {})),
    })).rejects.toThrow('workspace_voice_meeting_lookup_failed_503');

    await expect(ensureWorkspaceVoiceMeetingSession({
      apiUrl: 'http://api.test',
      workspaceId: 'ws_1',
      activeCapabilityCode: 'yogacoach',
      fetchImpl: vi.fn().mockResolvedValue(response(200, {
        ...session,
        thread_id: 'another_thread',
      })),
    })).rejects.toThrow('workspace_voice_meeting_session_invalid');
  });

  it('builds the one semantic command context consumed by bounded and realtime paths', () => {
    expect(buildWorkspaceVoiceMeetingCommandContext(
      session,
      'yogacoach',
    )).toEqual({
      context_objects: [],
      requested_action: null,
      expected_outputs: [
        'grounded_material',
        'grounded_answer',
        'client_action',
        'clarification',
      ],
      write_mode: 'recommendation_only',
      thread_id: 'workspace_voice_yogacoach',
      meeting_mentions: [],
      metadata: {
        source_surface: 'workspace_global_voice',
        voice_bootstrap: true,
        active_capability_code: 'yogacoach',
        active_pack_code: 'yogacoach',
      },
    });
  });
});
