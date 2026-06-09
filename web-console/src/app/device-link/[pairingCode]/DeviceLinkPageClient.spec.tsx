import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createElement } from 'react';

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
  phoneHandles: [] as any[],
  desktopHandles: [] as any[],
  readiness: {
    allowed: true,
  } as any,
  createStream: (label: string) => {
    const tracks = [
      {
        kind: 'video',
        label,
        stop: vi.fn(),
      },
    ];
    return {
      getTracks: () => tracks,
      getVideoTracks: () => tracks,
    } as any;
  },
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
  startPhoneBrowserSourceSession: vi.fn(async (input) => {
    const stream = mocks.createStream(`phone_${input.facingMode || 'environment'}`);
    input.onLocalStream?.(stream);
    const handle = {
      stop: vi.fn(() => stream.getTracks().forEach((track: any) => track.stop())),
      peerConnection: null,
      localStream: stream,
    };
    mocks.phoneHandles.push(handle);
    return handle;
  }),
  startDesktopBrowserSourceSession: vi.fn(async (input) => {
    const stream = mocks.createStream('desktop_camera');
    input.onLocalStream?.(stream);
    const handle = {
      stop: vi.fn(() => stream.getTracks().forEach((track: any) => track.stop())),
      peerConnection: null,
      localStream: stream,
    };
    mocks.desktopHandles.push(handle);
    return handle;
  }),
}));

vi.mock('@/components/workspace/device-binding/DesktopSourcePicker', () => ({
  DesktopSourcePicker: ({ onSelectionChange }: any) =>
    createElement(
      'button',
      {
        type: 'button',
        onClick: () =>
          onSelectionChange({
            deviceId: 'obs_1',
            label: 'OBS Virtual Camera',
            sourceKind: 'virtual_camera',
          }),
      },
      'Select OBS Virtual Camera',
    ),
}));

vi.mock('@/components/workspace/device-binding/DesktopSourcePreview', () => ({
  DesktopSourcePreview: () =>
    createElement('div', {
      'data-testid': 'desktop-source-preview',
    }),
}));

describe('DeviceLinkPageClient', () => {
  afterEach(() => {
    vi.clearAllMocks();
    mocks.socketInput = null;
    mocks.phoneHandles = [];
    mocks.desktopHandles = [];
    mocks.readiness = { allowed: true };
    vi.unstubAllGlobals();
  });

  it('hard-fails before source join when secure context is unavailable', async () => {
    mocks.readiness = {
      allowed: false,
      reason: 'secure_context_required',
      message: 'HTTPS required',
    };

    render(
      createElement(DeviceLinkPageClient, {
        pairingCode: 'PAIR1234',
        workspaceId: 'ws_device',
      }),
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Connect' }));
    });

    expect(screen.getByText('secure_context_required')).toBeTruthy();
    expect(screen.getAllByText('HTTPS required').length).toBeGreaterThan(0);
    expect(openDeviceControlSocket).not.toHaveBeenCalled();
  });

  it('starts phone media transport after the device binding session pairs', async () => {
    render(
      createElement(DeviceLinkPageClient, {
        pairingCode: 'PAIR1234',
        workspaceId: 'ws_device',
      }),
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Connect' }));
    });
    act(() => {
      mocks.socketInput.onOpen();
    });

    expect(mocks.socket.send).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'source_join',
        metadata: expect.objectContaining({
          camera_facing_mode: 'environment',
          source_mode: 'phone',
        }),
      }),
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
        facingMode: 'environment',
      }),
    );
  });

  it('flips phone camera by stopping the current media handle and restarting the same session', async () => {
    render(
      createElement(DeviceLinkPageClient, {
        pairingCode: 'PAIR1234',
        workspaceId: 'ws_device',
      }),
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Connect' }));
    });
    act(() => {
      mocks.socketInput.onOpen();
    });
    await act(async () => {
      mocks.socketInput.onEvent({
        type: 'session_paired',
        workspace_id: 'ws_device',
        session_id: 'session_1',
        device_id: 'phone_1',
      });
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Use front camera' }));
    });

    expect(mocks.phoneHandles[0].stop).toHaveBeenCalled();
    expect(startPhoneBrowserSourceSession).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        deviceSessionId: 'session_1',
        mediaSessionId: 'session_1',
        facingMode: 'user',
      }),
    );
  });

  it('shows fullscreen fallback copy when the browser does not expose fullscreen APIs', async () => {
    render(
      createElement(DeviceLinkPageClient, {
        pairingCode: 'PAIR1234',
        workspaceId: 'ws_device',
      }),
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Enter fullscreen' }));
    });

    expect(screen.getByText('Fullscreen unavailable. The capture layout stays edge-to-edge.')).toBeTruthy();
  });

  it('starts virtual camera media transport without sending device labels to backend', async () => {
    render(
      createElement(DeviceLinkPageClient, {
        pairingCode: 'PAIR1234',
        workspaceId: 'ws_device',
      }),
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Camera' }));
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
      createElement(DeviceLinkPageClient, {
        pairingCode: 'PAIR1234',
        workspaceId: 'ws_device',
        initialSourceMode: 'camera',
      }),
    );

    expect(screen.getByRole('button', { name: 'Select OBS Virtual Camera' })).toBeTruthy();
    expect(screen.getByTestId('desktop-source-preview')).toBeTruthy();
  });

  it('renders the pad companion layout on regular-width screens and accepts reference lesson state', async () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));

    render(
      createElement(DeviceLinkPageClient, {
        pairingCode: 'PAIR1234',
        workspaceId: 'ws_device',
      }),
    );

    expect(screen.getByTestId('pad-capture-companion')).toBeTruthy();
    expect(screen.getByText('Reference lesson')).toBeTruthy();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Connect' }));
    });
    act(() => {
      mocks.socketInput.onEvent({
        type: 'reference_lesson_state',
        workspace_id: 'ws_device',
        reference_lesson_state: {
          chapter_ref: 'chapter_01',
          title: 'Mountain pose alignment',
          timestamp_ms: 65000,
          focus_cue: 'Ground both feet before raising arms.',
        },
      });
    });

    expect(screen.getByText('Mountain pose alignment')).toBeTruthy();
    expect(screen.getByText('1:05')).toBeTruthy();
    expect(screen.getByText('Ground both feet before raising arms.')).toBeTruthy();
  });
});
