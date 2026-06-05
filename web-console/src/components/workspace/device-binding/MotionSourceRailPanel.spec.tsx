import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { MotionSourceRailPanel } from './MotionSourceRailPanel';
import {
  createDevicePairingCode,
  openDeviceControlSocket,
  revokeDeviceSession,
} from '@/lib/device-binding/deviceBindingClient';
import { submitMeetingCommandEnvelope } from '@/components/capabilities/meeting-workbench/meetingCommandLedger';

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
  PhoneSourcePreview: ({ session }: any) => (
    <div data-testid={`mock-phone-source-preview-${session.session_id}`} />
  ),
}));

vi.mock('@/components/capabilities/meeting-workbench/meetingCommandLedger', () => ({
  submitMeetingCommandEnvelope: vi.fn(async () => ({
    commandId: 'cmd_motion_practice',
    status: 'accepted',
    dispatchResult: null,
  })),
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
      <MotionSourceRailPanel
        apiUrl="http://api.test"
        workspaceId="ws_device"
      />,
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

  it('subscribes over websocket and revokes active sessions', async () => {
    render(
      <MotionSourceRailPanel
        apiUrl="http://api.test"
        workspaceId="ws_device"
      />,
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

  it('launches yoga practice through motion runtime and the meeting command ledger', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes('/meeting-sessions/active')) {
        return new Response(JSON.stringify({ detail: 'No active session found' }), { status: 404 });
      }
      if (url.includes('/meeting-sessions/start')) {
        return Response.json({
          id: 'mtg_motion_practice',
          workspace_id: 'ws_device',
          thread_id: null,
          metadata: {},
        });
      }
      if (url.includes('/api/v1/capabilities/motion_runtime/analysis/live-sessions')) {
        const body = JSON.parse(String(init?.body || '{}'));
        return Response.json({
          live_session: {
            live_session_id: 'lms_motion_practice',
            workspace_id: body.workspace_id,
            capture_session_id: body.capture_session_id,
          },
        });
      }
      return new Response('{}', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <MotionSourceRailPanel
        apiUrl="http://api.test"
        workspaceId="ws_device"
      />,
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

    await act(async () => {
      fireEvent.click(screen.getByTestId('motion-practice-start-button'));
    });

    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/api/v1/workspaces/ws_device/meeting-sessions/active',
      { credentials: 'same-origin' },
    );
    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/api/v1/capabilities/motion_runtime/analysis/live-sessions',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"capture_session_id":"session_1"'),
      }),
    );
    expect(submitMeetingCommandEnvelope).toHaveBeenCalledWith(
      expect.objectContaining({
        workspaceId: 'ws_device',
        meetingId: 'mtg_motion_practice',
        originSurface: 'workspace_motion_source_practice_launcher',
        requestedAction: expect.objectContaining({
          pack_code: 'yogacoach',
          playbook_code: 'yogacoach_student_practice_summary',
        }),
      }),
    );
    expect(screen.getByText('Submitted: accepted')).toBeInTheDocument();
    expect(screen.getByText('motion lms_motion_practice')).toBeInTheDocument();
  });

  it('shows non-ready practice routes without dispatching a command', async () => {
    render(
      <MotionSourceRailPanel
        apiUrl="http://api.test"
        workspaceId="ws_device"
      />,
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

    fireEvent.click(screen.getByRole('button', { name: 'Dance' }));

    expect(screen.getByTestId('motion-practice-readiness')).toHaveTextContent(
      'Dance pack contract exists',
    );
    expect(screen.getByTestId('motion-practice-start-button')).toBeDisabled();
    expect(submitMeetingCommandEnvelope).not.toHaveBeenCalled();
  });
});
