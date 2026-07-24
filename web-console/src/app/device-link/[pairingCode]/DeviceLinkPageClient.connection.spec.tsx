import { describe, expect, it, vi } from 'vitest';
import { act, screen, waitFor } from '@testing-library/react';

import {
  clickButton,
  connectAndPairPhone,
  markPhoneConnected,
  mocks,
  openControlSocket,
  pairSource,
  renderDeviceLinkPage,
} from './DeviceLinkPageClient.test-support';

describe('DeviceLinkPageClient connection behavior', () => {
  it('hard-fails before source join when secure context is unavailable', async () => {
    mocks.readiness = {
      allowed: false,
      reason: 'secure_context_required',
      message: 'HTTPS required',
    };

    renderDeviceLinkPage();
    await clickButton('Connect');

    expect(screen.getAllByText('HTTPS required').length).toBeGreaterThan(0);
    expect(screen.getByTestId('device-link-connection-status-detail')).toHaveTextContent('HTTPS required');
    expect(mocks.openDeviceControlSocket).not.toHaveBeenCalled();
  });

  it('renders the mobile camera controls as a bounded product control panel', () => {
    renderDeviceLinkPage();

    expect(screen.getByTestId('device-link-capture-control-panel')).toBeInTheDocument();
    expect(screen.getByText('Capture controls')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Use front camera' })).toHaveTextContent('Flip');
    expect(screen.getByRole('button', { name: 'Use front camera' })).toHaveTextContent('Rear');
    expect(screen.getByRole('button', { name: 'Use landscape capture' })).toHaveTextContent('Rotate');
    expect(screen.getByRole('button', { name: 'Connect' })).toHaveClass('w-full');
  });

  it('starts phone media transport after the device binding session pairs', async () => {
    renderDeviceLinkPage();

    await clickButton('Connect');
    openControlSocket();

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

    await pairSource();

    expect(mocks.startPhoneBrowserSourceSession).toHaveBeenCalledWith(
      expect.objectContaining({
        access: expect.objectContaining({
          session: expect.objectContaining({
            workspace_id: 'ws_device',
            device_session_id: 'session_1',
            media_session_id: 'lms_session_1',
          }),
        }),
        facingMode: 'environment',
        videoOrientation: 'portrait',
      }),
    );
  });

  it('turns a remote media-route 404 into a clear recovery message', async () => {
    mocks.createLiveMediaSession.mockRejectedValueOnce(
      new Error('live_media_request_failed_404'),
    );

    renderDeviceLinkPage();
    await clickButton('Connect');
    openControlSocket();
    await pairSource();

    await waitFor(() => {
      expect(screen.getByTestId('device-link-connection-status-detail')).toHaveTextContent(
        'The camera connection service is unavailable on this link. Reload this page, then tap Reconnect.',
      );
    });
    expect(screen.queryByText('live_media_request_failed_404')).toBeNull();
  });

  it('sends requested phone capture orientation when changed before connect', async () => {
    renderDeviceLinkPage();

    await clickButton('Use landscape capture');
    await clickButton('Connect');
    openControlSocket();

    expect(mocks.socket.send).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'source_join',
        metadata: expect.objectContaining({
          capture_orientation: 'landscape',
        }),
      }),
    );

    await pairSource();

    expect(mocks.startPhoneBrowserSourceSession).toHaveBeenCalledWith(
      expect.objectContaining({
        videoOrientation: 'landscape',
      }),
    );
  });

  it('disables repeat connect and keeps streaming visible across heartbeat acknowledgements', async () => {
    await connectAndPairPhone();

    expect(screen.getByRole('button', { name: 'Paired' })).toBeDisabled();
    expect(screen.getByTestId('device-link-connection-status-detail')).toHaveTextContent(
      'Connected. Keep this page open while the workspace receiver starts.',
    );

    await markPhoneConnected();

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

  it('keeps the backend source session alive with periodic heartbeats', async () => {
    vi.useFakeTimers();
    try {
      await connectAndPairPhone();

      await act(async () => {
        vi.advanceTimersByTime(30_000);
      });

      expect(mocks.socket.send).toHaveBeenCalledWith({ type: 'heartbeat' });
    } finally {
      vi.useRealTimers();
    }
  });

  it('restarts source media when signaling closes but the paired control session remains active', async () => {
    vi.useFakeTimers();
    try {
      await connectAndPairPhone();

      await act(async () => {
        mocks.phoneInputs[0].onState('closed');
      });

      expect(mocks.startPhoneBrowserSourceSession).toHaveBeenCalledTimes(1);

      await act(async () => {
        await Promise.resolve();
      });
      await act(async () => {
        vi.advanceTimersByTime(1500);
      });
      await act(async () => {
        await Promise.resolve();
      });

      expect(mocks.startPhoneBrowserSourceSession).toHaveBeenCalledTimes(2);
      expect(mocks.phoneHandles[0].stop).toHaveBeenCalled();
      expect(mocks.phoneInputs[1]).toEqual(expect.objectContaining({
        access: expect.objectContaining({
          session: expect.objectContaining({ media_session_id: 'lms_session_1' }),
        }),
      }));
      expect(screen.getByRole('button', { name: 'Paired' })).toBeDisabled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not start duplicate source media while the first media start is pending', async () => {
    let resolveStart: (handle: any) => void = () => undefined;
    const pendingStart = new Promise<any>((resolve) => {
      resolveStart = resolve;
    });
    mocks.startPhoneBrowserSourceSession.mockImplementationOnce(async (input) => {
      mocks.phoneInputs.push(input);
      return pendingStart;
    });

    renderDeviceLinkPage();
    await clickButton('Connect');
    openControlSocket();
    await pairSource();

    await act(async () => {
      mocks.socketInput.onEvent({
        type: 'heartbeat_ack',
        workspace_id: 'ws_device',
        session_id: 'session_1',
        device_id: 'phone_1',
      });
    });

    expect(mocks.startPhoneBrowserSourceSession).toHaveBeenCalledTimes(1);

    const stream = mocks.createStream('phone_pending');
    await act(async () => {
      resolveStart({
        stop: vi.fn(() => stream.getTracks().forEach((track: any) => track.stop())),
        replaceVideoTrack: vi.fn(),
        setVideoOrientation: vi.fn(),
        peerConnection: null,
        localStream: stream,
      });
      await pendingStart;
    });
  });

  it('stops automatic source media reconnects after the bounded retry budget is exhausted', async () => {
    vi.useFakeTimers();
    try {
      await connectAndPairPhone();

      for (const delayMs of [1500, 5000, 15000]) {
        await act(async () => {
          mocks.phoneInputs[mocks.phoneInputs.length - 1].onState('closed');
        });
        await act(async () => {
          vi.advanceTimersByTime(delayMs);
        });
        await act(async () => {
          await Promise.resolve();
        });
      }

      expect(mocks.startPhoneBrowserSourceSession).toHaveBeenCalledTimes(4);

      await act(async () => {
        mocks.phoneInputs[mocks.phoneInputs.length - 1].onState('closed');
      });
      await act(async () => {
        vi.advanceTimersByTime(60_000);
      });
      await act(async () => {
        await Promise.resolve();
      });

      expect(mocks.startPhoneBrowserSourceSession).toHaveBeenCalledTimes(4);
      expect(screen.getByTestId('device-link-connection-status-detail')).toHaveTextContent(
        'Media signaling closed repeatedly',
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it('republishes the same media session after WHIP connection failure', async () => {
    vi.useFakeTimers();
    try {
      await connectAndPairPhone();

      await act(async () => {
        mocks.phoneInputs[0].onError(new Error('whip_connection_failed'));
      });
      await act(async () => {
        vi.advanceTimersByTime(1500);
        await Promise.resolve();
      });

      expect(mocks.openDeviceControlSocket).toHaveBeenCalledTimes(1);
      expect(mocks.startPhoneBrowserSourceSession).toHaveBeenCalledTimes(2);
      expect(mocks.phoneInputs[1]).toEqual(expect.objectContaining({
        access: expect.objectContaining({
          session: expect.objectContaining({ media_session_id: 'lms_session_1' }),
        }),
      }));
    } finally {
      vi.useRealTimers();
    }
  });

  it('rebuilds source media without reopening the control pairing when media closes while paired', async () => {
    await connectAndPairPhone();

    await act(async () => {
      mocks.phoneInputs[0].onState('closed');
    });

    expect(screen.getByRole('button', { name: 'Reconnect' })).toBeEnabled();
    expect(screen.getByTestId('device-link-connection-status-detail')).toHaveTextContent(
      'Camera media disconnected',
    );

    await clickButton('Reconnect');

    expect(mocks.openDeviceControlSocket).toHaveBeenCalledTimes(1);
    expect(mocks.startPhoneBrowserSourceSession).toHaveBeenCalledTimes(2);
    expect(mocks.phoneHandles[0].stop).toHaveBeenCalled();
    expect(mocks.phoneInputs[1]).toEqual(expect.objectContaining({
      access: expect.objectContaining({
        session: expect.objectContaining({ media_session_id: 'lms_session_1' }),
      }),
    }));
  });

  it('requires a fresh control pairing when media signaling reports an unknown device session', async () => {
    await connectAndPairPhone();

    await act(async () => {
      mocks.phoneInputs[0].onError(new Error('unknown_device_session'));
    });

    expect(screen.getByRole('button', { name: 'Reconnect' })).toBeEnabled();
    expect(screen.getByTestId('device-link-connection-status-detail')).toHaveTextContent(
      'The source control session is no longer active. Reconnect from this page.',
    );

    await clickButton('Reconnect');

    expect(mocks.openDeviceControlSocket).toHaveBeenCalledTimes(2);
    expect(mocks.startPhoneBrowserSourceSession).toHaveBeenCalledTimes(1);
  });

  it('marks a streaming source closed when the control socket closes', async () => {
    await connectAndPairPhone();
    await markPhoneConnected();

    act(() => {
      mocks.socketInput.onClose();
    });

    expect(screen.getByRole('button', { name: 'Reconnect' })).toBeEnabled();
    expect(screen.getByTestId('device-link-connection-status-detail')).toHaveTextContent(
      'The source control connection closed. Reconnect from this page.',
    );
    expect(mocks.phoneHandles[0].stop).toHaveBeenCalled();
  });

  it('reconnects by opening a fresh control socket after the source session closes', async () => {
    await connectAndPairPhone();

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

    await clickButton('Reconnect');
    openControlSocket();

    expect(mocks.openDeviceControlSocket).toHaveBeenCalledTimes(2);
    expect(mocks.socket.send).toHaveBeenCalledTimes(2);
    expect(mocks.socket.send).toHaveBeenLastCalledWith(
      expect.objectContaining({
        type: 'source_join',
        display_name: 'Phone camera',
        source_types: ['phone_camera', 'microphone'],
      }),
    );
  });
});
