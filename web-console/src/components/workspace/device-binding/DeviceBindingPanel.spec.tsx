import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { DeviceBindingPanel } from './DeviceBindingPanel';
import {
  createDevicePairingCode,
  openDeviceControlSocket,
  revokeDeviceSession,
} from '@/lib/device-binding/deviceBindingClient';

const mocks = vi.hoisted(() => ({
  socket: {
    send: vi.fn(),
    close: vi.fn(),
    raw: {},
  },
  socketInput: null as any,
}));

vi.mock('@/lib/device-binding/deviceBindingClient', () => ({
  createDevicePairingCode: vi.fn(async () => ({
    workspace_id: 'ws_device',
    pairing_code: 'PAIR1234',
    expires_at_epoch: 1000,
    expires_in_seconds: 120,
    device_link_path: '/device-link/PAIR1234',
  })),
  openDeviceControlSocket: vi.fn((input) => {
    mocks.socketInput = input;
    return mocks.socket;
  }),
  revokeDeviceSession: vi.fn(async () => ({
    type: 'session_revoked',
    workspace_id: 'ws_device',
    active_sessions: [],
  })),
}));

describe('DeviceBindingPanel', () => {
  afterEach(() => {
    vi.clearAllMocks();
    mocks.socketInput = null;
  });

  it('renders without creating an interval polling loop', () => {
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');

    render(
      <DeviceBindingPanel
        apiUrl="http://api.test"
        workspaceId="ws_device"
      />,
    );

    expect(screen.getByRole('button', { name: 'Bind motion source device' })).toBeTruthy();
    expect(setIntervalSpy).not.toHaveBeenCalled();
  });

  it('creates a pairing code and subscribes over one websocket', async () => {
    render(
      <DeviceBindingPanel
        apiUrl="http://api.test"
        workspaceId="ws_device"
      />,
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Bind motion source device' }));
    });

    expect(createDevicePairingCode).toHaveBeenCalledWith({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
    });
    expect(openDeviceControlSocket).toHaveBeenCalledTimes(1);

    act(() => {
      mocks.socketInput.onOpen();
    });

    expect(mocks.socket.send).toHaveBeenCalledWith({ type: 'workspace_subscribe' });
    expect(screen.getByText('PAIR1234')).toBeTruthy();
  });

  it('updates active sessions from websocket events and revokes once', async () => {
    render(
      <DeviceBindingPanel
        apiUrl="http://api.test"
        workspaceId="ws_device"
      />,
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Bind motion source device' }));
    });
    act(() => {
      mocks.socketInput.onEvent({
        type: 'session_paired',
        workspace_id: 'ws_device',
        active_sessions: [
          {
            session_id: 'session_1',
            workspace_id: 'ws_device',
            pairing_code: 'PAIR1234',
            device_id: 'phone_1',
            display_name: 'Phone',
            source_types: ['phone_camera'],
            state: 'paired',
            created_at_epoch: 1,
            updated_at_epoch: 1,
            expires_at_epoch: 61,
          },
        ],
      });
    });

    expect(screen.getByText('Phone')).toBeTruthy();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Revoke Phone' }));
    });

    expect(revokeDeviceSession).toHaveBeenCalledTimes(1);
    expect(revokeDeviceSession).toHaveBeenCalledWith({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      sessionId: 'session_1',
    });
  });
});
