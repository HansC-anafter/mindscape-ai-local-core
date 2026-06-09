import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createElement } from 'react';

import { MotionSourceRailPanel } from './MotionSourceRailPanel';
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

vi.mock('./PhoneSourcePreview', () => ({
  PhoneSourcePreview: (props: { session: { session_id: string }; liveMotionSessionId?: string }) => {
    const { session, liveMotionSessionId } = props;
    return createElement('div', {
      'data-testid': `mock-phone-source-preview-${session.session_id}`,
      'data-live-motion-session-id': liveMotionSessionId || '',
    });
  },
}));

describe('MotionSourceRailPanel', () => {
  afterEach(() => {
    vi.clearAllMocks();
    mocks.socketInput = null;
    vi.unstubAllGlobals();
  });

  it('starts one pairing flow on mount without interval polling', async () => {
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');

    render(
      createElement(MotionSourceRailPanel, {
        apiUrl: 'http://api.test',
        workspaceId: 'ws_device',
      }),
    );

    expect(setIntervalSpy).not.toHaveBeenCalled();
    await screen.findByText('PAIR1234');
    expect(createDevicePairingCode).toHaveBeenCalledWith({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
    });
    expect(openDeviceControlSocket).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('link', { name: 'Phone source link' })).toHaveAttribute(
      'href',
      'http://localhost:3000/device-link/PAIR1234?workspaceId=ws_device&sourceMode=phone',
    );
    expect(screen.getByRole('link', { name: 'Desktop camera source link' })).toHaveAttribute(
      'href',
      'http://localhost:3000/device-link/PAIR1234?workspaceId=ws_device&sourceMode=camera',
    );
  });

  it('renders a scannable phone QR only for HTTPS LAN origins', async () => {
    render(
      createElement(MotionSourceRailPanel, {
        apiUrl: 'http://api.test',
        workspaceId: 'ws_device',
      }),
    );

    await screen.findByText('PAIR1234');

    expect(screen.queryByTestId('phone-qr-code')).toBeNull();

    fireEvent.change(screen.getByTestId('phone-public-origin-input'), {
      target: { value: 'https://192.168.1.20:8343' },
    });

    expect(screen.getByTestId('phone-qr-readiness')).toHaveTextContent('QR-ready link');
    expect(screen.getByRole('link', { name: 'Phone source link' })).toHaveAttribute(
      'href',
      'https://192.168.1.20:8343/device-link/PAIR1234?workspaceId=ws_device&sourceMode=phone',
    );
    expect(screen.getByTestId('phone-qr-code').querySelector('svg')).toHaveAttribute(
      'aria-label',
      'Phone pairing QR code',
    );
  });

  it('subscribes over websocket and revokes active sessions', async () => {
    render(
      createElement(MotionSourceRailPanel, {
        apiUrl: 'http://api.test',
        workspaceId: 'ws_device',
      }),
    );

    await screen.findByText('PAIR1234');

    act(() => {
      mocks.socketInput.onOpen();
    });

    expect(mocks.socket.send).toHaveBeenCalledWith({ type: 'workspace_subscribe' });

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

    expect(screen.getByText('phone_camera')).toBeTruthy();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Revoke Phone' }));
    });

    expect(revokeDeviceSession).toHaveBeenCalledWith({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      sessionId: 'session_1',
    });
  });

  it('keeps yoga and dance practice controls out of the generic source rail', async () => {
    render(
      createElement(MotionSourceRailPanel, {
        apiUrl: 'http://api.test',
        workspaceId: 'ws_device',
      }),
    );

    await screen.findByText('PAIR1234');
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
            state: 'active',
            created_at_epoch: 1,
            updated_at_epoch: 1,
            expires_at_epoch: 61,
          },
        ],
      });
    });

    expect(screen.queryByText('AI Yoga')).toBeNull();
    expect(screen.queryByText('Dance')).toBeNull();
    expect(screen.queryByTestId('motion-practice-mode-select')).toBeNull();
    expect(screen.queryByTestId('motion-practice-start-button')).toBeNull();
    expect(screen.getByTestId('mock-phone-source-preview-session_1')).toHaveAttribute(
      'data-live-motion-session-id',
      '',
    );
  });
});
