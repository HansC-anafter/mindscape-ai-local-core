import { describe, expect, it, vi } from 'vitest';

import {
  startDesktopBrowserSourceSession,
  startPhoneBrowserSourceSession,
} from './webrtcSessionClient';
import {
  defaultSessionInput,
  installMediaDevices,
  installWebSocketMock,
} from './webrtcSessionClient.test-support';

describe('webrtcSessionClient capture start constraints', () => {
  it('starts desktop camera sources with device-scoped video constraints and no audio', async () => {
    const tracks = [{ stop: vi.fn() }];
    const getUserMedia = vi.fn(async () => ({
      getTracks: () => tracks,
    }));
    installWebSocketMock();
    installMediaDevices(getUserMedia);

    await startDesktopBrowserSourceSession({
      ...defaultSessionInput,
      sourceKind: 'virtual_camera',
      deviceId: 'obs_1',
    });

    expect(getUserMedia).toHaveBeenCalledWith({
      video: {
        deviceId: { exact: 'obs_1' },
        width: { ideal: 1280 },
        height: { ideal: 720 },
        frameRate: { max: 30 },
      },
      audio: false,
    });
  });

  it('starts phone camera sources with requested facing mode', async () => {
    const getUserMedia = vi.fn(async () => ({
      getTracks: () => [{ stop: vi.fn() }],
    }));
    installWebSocketMock();
    installMediaDevices(getUserMedia);

    await startPhoneBrowserSourceSession({
      ...defaultSessionInput,
      facingMode: 'user',
    });

    expect(getUserMedia).toHaveBeenCalledWith({
      video: {
        facingMode: { ideal: 'user' },
        width: { ideal: 1280 },
        height: { ideal: 720 },
        frameRate: { max: 30 },
      },
      audio: true,
    });
  });
});
