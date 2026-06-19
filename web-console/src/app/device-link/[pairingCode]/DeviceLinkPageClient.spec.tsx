import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  phoneInputs: [] as any[],
  desktopInputs: [] as any[],
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
  buildPhoneVideoConstraints: (facingMode = 'environment') => ({
    facingMode: { ideal: facingMode },
    width: { ideal: 1280 },
    height: { ideal: 720 },
    frameRate: { max: 30 },
  }),
  startPhoneBrowserSourceSession: vi.fn(async (input) => {
    mocks.phoneInputs.push(input);
    const stream = mocks.createStream(`phone_${input.facingMode || 'environment'}`);
    input.onLocalStream?.(stream);
    const handle = {
      stop: vi.fn(() => stream.getTracks().forEach((track: any) => track.stop())),
      replaceVideoTrack: vi.fn(async (video: MediaTrackConstraints) => {
        const facingMode = typeof video.facingMode === 'object'
          && video.facingMode
          && 'ideal' in video.facingMode
          ? String(video.facingMode.ideal)
          : 'environment';
        const nextStream = mocks.createStream(`phone_${facingMode}`);
        input.onLocalStream?.(nextStream);
        return nextStream;
      }),
      setVideoOrientation: vi.fn(async (orientation: 'portrait' | 'landscape') => {
        const nextStream = mocks.createStream(`phone_${input.facingMode || 'environment'}_${orientation}`);
        input.onLocalStream?.(nextStream);
        return nextStream;
      }),
      peerConnection: null,
      localStream: stream,
    };
    mocks.phoneHandles.push(handle);
    return handle;
  }),
  startDesktopBrowserSourceSession: vi.fn(async (input) => {
    mocks.desktopInputs.push(input);
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
    mocks.phoneInputs = [];
    mocks.desktopInputs = [];
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

    expect(screen.getAllByText('HTTPS required').length).toBeGreaterThan(0);
    expect(screen.getByTestId('device-link-connection-status-detail')).toHaveTextContent('HTTPS required');
    expect(openDeviceControlSocket).not.toHaveBeenCalled();
  });

  it('renders the mobile camera controls as a bounded product control panel', () => {
    render(
      createElement(DeviceLinkPageClient, {
        pairingCode: 'PAIR1234',
        workspaceId: 'ws_device',
      }),
    );

    expect(screen.getByTestId('device-link-capture-control-panel')).toBeInTheDocument();
    expect(screen.getByText('Capture controls')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Use front camera' })).toHaveTextContent('Flip');
    expect(screen.getByRole('button', { name: 'Use front camera' })).toHaveTextContent('Rear');
    expect(screen.getByRole('button', { name: 'Use landscape capture' })).toHaveTextContent('Rotate');
    expect(screen.getByRole('button', { name: 'Connect' })).toHaveClass('w-full');
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
            capture_orientation: 'portrait',
            source_mode: 'phone',
            secure_context: false,
          source_origin_scheme: 'http',
          capture_surface: 'device_link',
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
        videoOrientation: 'portrait',
      }),
    );
  });

  it('sends requested phone capture orientation when changed before connect', async () => {
    render(
      createElement(DeviceLinkPageClient, {
        pairingCode: 'PAIR1234',
        workspaceId: 'ws_device',
      }),
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Use landscape capture' }));
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
        metadata: expect.objectContaining({
          capture_orientation: 'landscape',
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
        videoOrientation: 'landscape',
      }),
    );
  });

  it('disables repeat connect and keeps streaming visible across heartbeat acknowledgements', async () => {
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

    expect(screen.getByRole('button', { name: 'Paired' })).toBeDisabled();
    expect(screen.getByTestId('device-link-connection-status-detail')).toHaveTextContent(
      'Connected. Keep this page open while the workspace receiver starts.',
    );

    await act(async () => {
      mocks.phoneInputs[0].onState('connected');
    });

    expect(screen.getByRole('button', { name: 'Streaming' })).toBeDisabled();

    await act(async () => {
      mocks.socketInput.onEvent({
        type: 'heartbeat_ack',
        workspace_id: 'ws_device',
        session_id: 'session_1',
        device_id: 'phone_1',
      });
    });

    expect(screen.getByRole('button', { name: 'Streaming' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Paired' })).toBeNull();
  });

  it('reconnects by opening a fresh control socket after the source session closes', async () => {
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
      mocks.socketInput.onEvent({
        type: 'session_closed',
        workspace_id: 'ws_device',
        session_id: 'session_1',
        device_id: 'phone_1',
        reason: 'socket_closed',
      });
    });

    expect(screen.getByRole('button', { name: 'Reconnect' })).toBeEnabled();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Reconnect' }));
    });
    act(() => {
      mocks.socketInput.onOpen();
    });

    expect(openDeviceControlSocket).toHaveBeenCalledTimes(2);
    expect(mocks.socket.send).toHaveBeenCalledTimes(2);
    expect(mocks.socket.send).toHaveBeenLastCalledWith(
      expect.objectContaining({
        type: 'source_join',
        display_name: 'Phone camera',
        source_types: ['phone_camera', 'microphone'],
      }),
    );
  });

  it('flips phone camera by replacing the video track without closing the media session', async () => {
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
    await waitFor(() => expect(mocks.phoneHandles).toHaveLength(1));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
    await act(async () => {
      mocks.phoneInputs[0].onState('connected');
    });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Streaming' })).toBeDisabled());

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Use front camera' }));
    });

    expect(mocks.phoneHandles[0].stop).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(mocks.phoneHandles[0].replaceVideoTrack).toHaveBeenCalledWith(
        expect.objectContaining({
          facingMode: { ideal: 'user' },
        }),
        expect.objectContaining({
          orientation: 'portrait',
        }),
      ),
    );
    expect(startPhoneBrowserSourceSession).toHaveBeenCalledTimes(1);
  });

  it('keeps the phone source recoverable when camera replacement needs a media restart', async () => {
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
    await waitFor(() => expect(mocks.phoneHandles).toHaveLength(1));
    await act(async () => {
      mocks.phoneInputs[0].onState('connected');
    });
    mocks.phoneHandles[0].replaceVideoTrack.mockImplementationOnce(async () => {
      const error = new Error('replace_track_failed');
      mocks.phoneInputs[0].onError(error);
      throw error;
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Use front camera' }));
    });

    await waitFor(() => expect(startPhoneBrowserSourceSession).toHaveBeenCalledTimes(2));
    expect(mocks.phoneHandles[0].stop).toHaveBeenCalledTimes(1);
    expect(startPhoneBrowserSourceSession).toHaveBeenLastCalledWith(
      expect.objectContaining({
        facingMode: 'user',
        videoOrientation: 'portrait',
      }),
    );
    expect(screen.getByTestId('device-link-connection-status-detail')).toHaveTextContent(
      'Front camera enabled.',
    );
    expect(screen.queryByRole('button', { name: 'Reconnect' })).toBeNull();
  });

  it('switches phone capture orientation without reopening the media session', async () => {
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
    await waitFor(() => expect(mocks.phoneHandles).toHaveLength(1));
    await act(async () => {
      mocks.phoneInputs[0].onState('connected');
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Use landscape capture' }));
    });

    expect(mocks.phoneHandles[0].setVideoOrientation).toHaveBeenCalledWith('landscape');
    expect(startPhoneBrowserSourceSession).toHaveBeenCalledTimes(1);
    expect(openDeviceControlSocket).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('device-link-connection-status-detail')).toHaveTextContent(
      'Landscape capture enabled.',
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
      fireEvent.click(screen.getByRole('button', { name: 'Computer camera' }));
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
          secure_context: false,
          source_origin_scheme: 'http',
          capture_surface: 'device_link',
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

    await waitFor(() => expect(screen.getByTestId('pad-capture-companion')).toBeTruthy());
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
