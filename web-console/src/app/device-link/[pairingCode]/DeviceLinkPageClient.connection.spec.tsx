import { describe, expect, it } from 'vitest';
import { act, screen } from '@testing-library/react';

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
