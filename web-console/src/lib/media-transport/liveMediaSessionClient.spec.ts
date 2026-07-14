import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  createLiveMediaSession,
  getLiveMediaSession,
  refreshLiveMediaSessionAccess,
  stopLiveMediaSession,
} from './liveMediaSessionClient';

const identity = {
  apiBase: 'https://core.test/',
  workspaceId: 'workspace one',
  deviceSessionId: 'device one',
};

function response(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('liveMediaSessionClient', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('creates one session under the existing device-binding namespace', async () => {
    const fetchMock = vi.fn(async () => response({ session: {}, tokens: {} }));
    vi.stubGlobal('fetch', fetchMock);

    await createLiveMediaSession({
      ...identity,
      sourceKind: 'phone_camera',
      capabilities: ['video', 'audio'],
      analysisReserved: true,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      'https://core.test/api/v1/workspaces/workspace%20one/device-bindings/device%20one/media-sessions',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          source_kind: 'phone_camera',
          relay_profile: 'public',
          capabilities: ['video', 'audio'],
          analysis_reserved: true,
        }),
      }),
    );
  });

  it('keeps descriptor reads credential-free and refresh explicit', async () => {
    const fetchMock = vi.fn(async () => response({}));
    vi.stubGlobal('fetch', fetchMock);

    await getLiveMediaSession(identity);
    await refreshLiveMediaSessionAccess({ ...identity, mediaSessionId: 'media one' });

    expect(fetchMock.mock.calls[0]).toEqual([
      'https://core.test/api/v1/workspaces/workspace%20one/device-bindings/device%20one/media-sessions',
      { cache: 'no-store' },
    ]);
    expect(fetchMock.mock.calls[1]).toEqual([
      'https://core.test/api/v1/workspaces/workspace%20one/device-bindings/device%20one/media-sessions/media%20one/refresh',
      { method: 'POST' },
    ]);
  });

  it('uses keepalive only for explicit terminal cleanup', async () => {
    const fetchMock = vi.fn(async () => response({ state: 'stopped' }));
    vi.stubGlobal('fetch', fetchMock);

    await stopLiveMediaSession({
      ...identity,
      mediaSessionId: 'media one',
      keepalive: true,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      'https://core.test/api/v1/workspaces/workspace%20one/device-bindings/device%20one/media-sessions/media%20one/stop',
      { method: 'POST', keepalive: true },
    );
  });

  it('surfaces the backend stable reason without logging response credentials', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({
      detail: 'workspace_analysis_session_already_reserved',
    }, 409)));

    await expect(createLiveMediaSession({
      ...identity,
      sourceKind: 'phone_camera',
      capabilities: ['video'],
    })).rejects.toThrow('workspace_analysis_session_already_reserved');
  });
});
