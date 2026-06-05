import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { DeviceLinkPageClient } from './DeviceLinkPageClient';
import { openDeviceControlSocket } from '@/lib/device-binding/deviceBindingClient';
import {
  startDesktopBrowserSourceSession,
  startPhoneBrowserSourceSession,
} from '@/lib/media-transport/webrtcSessionClient';

const mocks = vi.hoisted(() => ({
  socket: {
    send: vi.fn(),
    close: vi.fn(),
    raw: {},
  },
  socketInput: null as any,
  readiness: {
    allowed: true,
  } as any,
}));

vi.mock('@/lib/api-url', () => ({
  getApiBaseUrl: () => 'http://api.test',
}));

vi.mock('@/lib/media-transport/secureContextGuard', () => ({
  assessBrowserMediaCaptureReadiness: vi.fn(() => mocks.readiness),
}));

vi.mock('@/lib/device-binding/deviceBindingClient', () => ({
  openDeviceControlSocket: vi.fn((input) => {
    mocks.socketInput = input;
    return mocks.socket;
  }),
}));

vi.mock('@/lib/media-transport/webrtcSessionClient', () => ({
  startPhoneBrowserSourceSession: vi.fn(async () => ({
    stop: vi.fn(),
    peerConnection: null,
  })),
  startDesktopBrowserSourceSession: vi.fn(async () => ({
    stop: vi.fn(),
    peerConnection: null,
  })),
}));

vi.mock('@/components/workspace/device-binding/DesktopSourcePicker', () => ({
  DesktopSourcePicker: ({ onSelectionChange }: any) => (
    <button
      type="button"
      onClick={() => onSelectionChange({
        deviceId: 'obs_1',
        label: 'OBS Virtual Camera',
        sourceKind: 'virtual_camera',
      })}
    >
      Select OBS Virtual Camera
    </button>
  ),
}));

vi.mock('@/components/workspace/device-binding/DesktopSourcePreview', () => ({
  DesktopSourcePreview: () => <div data-testid="desktop-source-preview" />,
}));

describe('DeviceLinkPageClient', () => {
  afterEach(() => {
    vi.clearAllMocks();
    mocks.socketInput = null;
    mocks.readiness = { allowed: true };
  });

  it('hard-fails before source join when secure context is unavailable', async () => {
    mocks.readiness = {
      allowed: false,
      reason: 'secure_context_required',
      message: 'HTTPS required',
    };

    render(<DeviceLinkPageClient pairingCode="PAIR1234" workspaceId="ws_device" />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Connect' }));
    });

    expect(screen.getByText('secure_context_required')).toBeTruthy();
    expect(screen.getByText('HTTPS required')).toBeTruthy();
    expect(openDeviceControlSocket).not.toHaveBeenCalled();
  });

  it('starts phone media transport after the device binding session pairs', async () => {
    render(<DeviceLinkPageClient pairingCode="PAIR1234" workspaceId="ws_device" />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Connect' }));
    });
    act(() => {
      mocks.socketInput.onOpen();
    });

    expect(mocks.socket.send).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'source_join' }),
    );

    await act(async () => {
      mocks.socketInput.onEvent({
        type: 'session_paired',
        workspace_id: 'ws_device',
        session_id: 'session_1',
        device_id: 'phone_1',
      });
    });

    expect(startPhoneBrowserSourceSession).toHaveBeenCalledWith(
      expect.objectContaining({
        apiBase: 'http://api.test',
        workspaceId: 'ws_device',
        deviceSessionId: 'session_1',
        mediaSessionId: 'session_1',
      }),
    );
  });

  it('starts virtual camera media transport without sending device labels to backend', async () => {
    render(<DeviceLinkPageClient pairingCode="PAIR1234" workspaceId="ws_device" />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Camera source' }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Select OBS Virtual Camera' }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Connect' }));
    });
    act(() => {
      mocks.socketInput.onOpen();
    });

    expect(mocks.socket.send).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'source_join',
        display_name: 'Virtual camera',
        source_types: ['virtual_camera'],
        metadata: expect.objectContaining({
          source_mode: 'camera',
        }),
      }),
    );
    expect(JSON.stringify(mocks.socket.send.mock.calls)).not.toContain('OBS Virtual Camera');

    await act(async () => {
      mocks.socketInput.onEvent({
        type: 'session_paired',
        workspace_id: 'ws_device',
        session_id: 'session_1',
        device_id: 'desktop_1',
      });
    });

    expect(startDesktopBrowserSourceSession).toHaveBeenCalledWith(
      expect.objectContaining({
        apiBase: 'http://api.test',
        workspaceId: 'ws_device',
        deviceSessionId: 'session_1',
        mediaSessionId: 'session_1',
        sourceKind: 'virtual_camera',
        deviceId: 'obs_1',
      }),
    );
    expect(startPhoneBrowserSourceSession).not.toHaveBeenCalled();
  });

  it('can open directly in camera source mode from a rail deep link', () => {
    render(
      <DeviceLinkPageClient
        pairingCode="PAIR1234"
        workspaceId="ws_device"
        initialSourceMode="camera"
      />,
    );

    expect(screen.getByRole('button', { name: 'Select OBS Virtual Camera' })).toBeTruthy();
    expect(screen.getByTestId('desktop-source-preview')).toBeTruthy();
  });
});
