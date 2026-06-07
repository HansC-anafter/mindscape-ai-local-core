import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  buildLocalVideoCaptureSessionId,
  buildLocalVideoLiveSessionRequest,
  buildLocalVideoMotionResourcePolicy,
  buildLocalVideoSourceRef,
  readLocalVideoLiveSessionId,
  registerLocalVideoLiveSession,
} from './localVideoMotionSmokeSession';

const file = {
  name: 'teacher demo.mov',
  size: 123456,
  type: 'video/quicktime',
  lastModified: 1710000000000,
};

function expectNoRawPayload(payload: unknown) {
  const forbiddenKeys = new Set([
    'raw_frame',
    'raw_video',
    'video_base64',
    'frame_base64',
    'file_data',
    'video_bytes',
  ]);
  const visit = (value: unknown) => {
    if (!value || typeof value !== 'object') {
      return;
    }
    for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
      expect(forbiddenKeys.has(key)).toBe(false);
      visit(nested);
    }
  };
  visit(payload);
}

describe('localVideoMotionSmokeSession', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('builds deterministic local-video refs without raw media payloads', () => {
    expect(buildLocalVideoCaptureSessionId(file)).toBe(
      'local_video:teacher-demo.mov:123456:1710000000000',
    );
    expect(buildLocalVideoSourceRef(file)).toBe(
      'mindscape://local-video/local_video%3Ateacher-demo.mov%3A123456%3A1710000000000',
    );

    const request = buildLocalVideoLiveSessionRequest({
      workspaceId: 'ws_motion',
      file,
    });

    expect(request).toMatchObject({
      workspace_id: 'ws_motion',
      capture_session_id: 'local_video:teacher-demo.mov:123456:1710000000000',
      metadata: {
        source_surface: 'workspace_local_video_motion_smoke',
        source_kind: 'local_video_file',
        resource_policy: buildLocalVideoMotionResourcePolicy(),
      },
    });
    expectNoRawPayload(request);
  });

  it('registers one motion_runtime live session without polling or retries', async () => {
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');
    const fetchMock = vi.fn(async () => Response.json({
      live_session: {
        live_session_id: 'lms_local_video',
      },
    }));
    vi.stubGlobal('fetch', fetchMock);

    const response = await registerLocalVideoLiveSession({
      apiUrl: 'http://api.test/',
      workspaceId: 'ws_motion',
      file,
    });

    expect(readLocalVideoLiveSessionId(response)).toBe('lms_local_video');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/api/v1/capabilities/motion_runtime/analysis/live-sessions',
      expect.objectContaining({
        method: 'POST',
        credentials: 'same-origin',
      }),
    );
    expectNoRawPayload(JSON.parse(String(fetchMock.mock.calls[0][1]?.body)));
    expect(setIntervalSpy).not.toHaveBeenCalled();
  });
});
