import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { DesktopSourcePicker } from './DesktopSourcePicker';

describe('DesktopSourcePicker', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('loads camera sources on user action and marks OBS as virtual camera', async () => {
    Object.defineProperty(globalThis.navigator, 'mediaDevices', {
      configurable: true,
      value: {
        enumerateDevices: vi.fn(async () => [
          {
            kind: 'videoinput',
            deviceId: 'obs_1',
            groupId: 'group_1',
            label: 'OBS Virtual Camera',
          },
        ]),
      },
    });
    const onSelectionChange = vi.fn();

    render(
      <DesktopSourcePicker
        onSelectionChange={onSelectionChange}
      />,
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Refresh camera sources' }));
    });

    expect(screen.getByText('OBS Virtual Camera')).toBeTruthy();
    expect(screen.getByText('Virtual camera')).toBeTruthy();
    expect(screen.queryByText(/RTSP|NDI|OBS websocket/i)).toBeNull();
    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.objectContaining({
        deviceId: 'obs_1',
        sourceKind: 'virtual_camera',
      }),
    );
  });

  it('does not create an interval polling loop', () => {
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');

    render(
      <DesktopSourcePicker
        onSelectionChange={vi.fn()}
      />,
    );

    expect(setIntervalSpy).not.toHaveBeenCalled();
  });
});
