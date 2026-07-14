import { afterEach, describe, expect, it, vi } from 'vitest';

import { startLiveMediaReceiver } from './liveMediaReceiverClient';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('startLiveMediaReceiver', () => {
  it('starts the server-owned receiver without sending credentials', async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => ({
      ok: true,
      json: async () => ({
        schema_version: 'live_media_receiver_control.v1',
        status: 'active',
        state: 'starting',
        media_session_id: 'media/one',
      }),
      requestInit: init,
    }));
    vi.stubGlobal('fetch', fetchMock);

    await startLiveMediaReceiver({
      apiBase: 'http://api.test/',
      workspaceId: 'workspace one',
      deviceSessionId: 'device one',
      mediaSessionId: 'media/one',
      liveMotionSessionId: 'motion one',
      meetingSessionId: 'meeting one',
      practiceSessionId: 'practice one',
      coachPack: 'yogacoach',
      practiceMode: 'live_guidance',
      referenceUrl: 'https://example.test/reference',
    });

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      'http://api.test/api/v1/workspaces/workspace%20one/device-bindings/'
        + 'device%20one/media-sessions/media%2Fone/receiver/start',
    );
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(request.credentials).toBe('same-origin');
    const payload = JSON.parse(String(request.body));
    expect(payload).toMatchObject({
      live_motion_session_id: 'motion one',
      meeting_session_id: 'meeting one',
      practice_session_id: 'practice one',
      coach_pack: 'yogacoach',
    });
    expect(JSON.stringify(payload)).not.toMatch(/token|append_owner|receiver_identity/);
  });

  it('fails unless the host confirms the requested media session is active', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema_version: 'live_media_receiver_control.v1',
        status: 'failed',
        media_session_id: 'media-one',
      }),
    })));

    await expect(startLiveMediaReceiver({
      apiBase: '',
      workspaceId: 'workspace-one',
      deviceSessionId: 'device-one',
      mediaSessionId: 'media-one',
      liveMotionSessionId: 'motion-one',
      meetingSessionId: 'meeting-one',
      practiceSessionId: 'practice-one',
      coachPack: 'yogacoach',
      practiceMode: 'live_guidance',
    })).rejects.toThrow('live_media_receiver_not_active:failed');
  });
});
