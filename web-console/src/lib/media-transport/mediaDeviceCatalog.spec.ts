import { describe, expect, it, vi } from 'vitest';

import {
  attachDeviceChangeRefresh,
  classifyVideoInputSource,
  loadVideoInputCatalog,
} from './mediaDeviceCatalog';

describe('mediaDeviceCatalog', () => {
  it('classifies browser video inputs without OBS control protocols', () => {
    expect(classifyVideoInputSource('OBS Virtual Camera')).toBe('virtual_camera');
    expect(classifyVideoInputSource('USB Capture HDMI')).toBe('usb_camera');
    expect(classifyVideoInputSource('FaceTime HD Camera')).toBe('desktop_camera');
  });

  it('loads only video inputs through explicit enumerateDevices calls', async () => {
    const enumerateDevices = vi.fn(async () => [
      {
        kind: 'audioinput',
        deviceId: 'mic_1',
        groupId: 'group_1',
        label: 'Microphone',
      },
      {
        kind: 'videoinput',
        deviceId: 'camera_1',
        groupId: 'group_2',
        label: 'OBS Virtual Camera',
      },
    ] as MediaDeviceInfo[]);

    await expect(loadVideoInputCatalog({ enumerateDevices })).resolves.toEqual([
      {
        deviceId: 'camera_1',
        groupId: 'group_2',
        label: 'OBS Virtual Camera',
        sourceKind: 'virtual_camera',
      },
    ]);
    expect(enumerateDevices).toHaveBeenCalledTimes(1);
  });

  it('unlocks browser camera labels when the first enumerate call returns no video inputs', async () => {
    const stop = vi.fn();
    const enumerateDevices = vi.fn()
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          kind: 'videoinput',
          deviceId: 'obs_camera',
          groupId: 'group_obs',
          label: 'OBS Virtual Camera',
        },
      ] as MediaDeviceInfo[]);
    const getUserMedia = vi.fn(async () => ({
      getTracks: () => [{ stop }],
    } as unknown as MediaStream));

    await expect(loadVideoInputCatalog({ enumerateDevices, getUserMedia })).resolves.toEqual([
      {
        deviceId: 'obs_camera',
        groupId: 'group_obs',
        label: 'OBS Virtual Camera',
        sourceKind: 'virtual_camera',
      },
    ]);
    expect(getUserMedia).toHaveBeenCalledWith({ video: true, audio: false });
    expect(stop).toHaveBeenCalledTimes(1);
  });

  it('uses devicechange events without creating an interval loop', () => {
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');
    const addEventListener = vi.fn();
    const removeEventListener = vi.fn();
    const onChange = vi.fn();

    const detach = attachDeviceChangeRefresh(
      {
        enumerateDevices: vi.fn(async () => []),
        addEventListener,
        removeEventListener,
      },
      onChange,
    );
    detach();

    expect(addEventListener).toHaveBeenCalledWith('devicechange', onChange);
    expect(removeEventListener).toHaveBeenCalledWith('devicechange', onChange);
    expect(setIntervalSpy).not.toHaveBeenCalled();
  });
});
