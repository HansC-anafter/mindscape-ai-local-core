import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createElement, useEffect } from 'react';

import { MotionSourceRailPanel } from './MotionSourceRailPanel';
import {
  CaptureSourceBridgeProvider,
  useCaptureSourceBridge,
} from './capture-bridge/CaptureSourceBridgeProvider';
import { CaptureSourceRailFromBridge } from './capture-bridge/CaptureSourceRail';
import {
  createDevicePairingCode,
  openWorkspaceDeviceControlSocket,
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
  buildDeviceLinkHttpsHealthUrl: vi.fn(({ apiBase }: { apiBase: string }) => (
    `${apiBase.replace(/\/+$/, '')}/api/v1/host/services/device-link-https/health`
  )),
  createDevicePairingCode: vi.fn(async () => ({
    workspace_id: 'ws_device',
    pairing_code: 'PAIR1234',
    expires_at_epoch: 1000,
    expires_in_seconds: 120,
    device_link_path: '/device-link/PAIR1234',
  })),
  openWorkspaceDeviceControlSocket: vi.fn((input) => {
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
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      json: async () => ({}),
    })));
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
    mocks.socketInput = null;
    vi.unstubAllGlobals();
    window.history.replaceState({}, '', 'http://localhost:3000/');
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
      expiresInSeconds: 600,
    });
    expect(openWorkspaceDeviceControlSocket).toHaveBeenCalledTimes(1);
    expect(openWorkspaceDeviceControlSocket).toHaveBeenCalledWith(
      expect.objectContaining({
        apiBase: 'http://api.test',
        workspaceId: 'ws_device',
      }),
    );
    expect(screen.getByRole('link', { name: 'Phone source link' })).toHaveAttribute(
      'href',
      'http://localhost:3000/device-link/PAIR1234?workspaceId=ws_device&sourceMode=phone',
    );
    expect(screen.getByRole('link', { name: 'Desktop camera source link' })).toHaveAttribute(
      'href',
      'http://localhost:3000/device-link/PAIR1234?workspaceId=ws_device&sourceMode=camera',
    );
    expect(screen.getByText('Local-core device link')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open Device Link settings' })).toHaveAttribute(
      'href',
      '/settings?tab=runtime&section=device-link-readiness&workspace_id=ws_device',
    );
    expect(screen.getByText('Provider backends')).toBeInTheDocument();
    expect(screen.getByTestId('capture-provider-source-slot-count')).toHaveTextContent('0 / 3 active');
    expect(screen.getByText('Phone owned camera')).toBeInTheDocument();
    expect(screen.getByText('Computer / OBS camera')).toBeInTheDocument();
    expect(screen.getByText('External device provider')).toBeInTheDocument();
    expect(screen.getByText('Bridge required')).toBeInTheDocument();
    expect(screen.getByTestId('external-provider-connection-guide')).toHaveTextContent(
      'External provider connection guide',
    );
    expect(screen.getByTestId('external-provider-connection-guide')).toHaveTextContent(
      'run a neutral host/mobile bridge for DJI Ronin, RS, Osmo',
    );
    expect(screen.getByTestId('external-provider-connection-guide')).toHaveTextContent(
      'Do not use the Phone owned camera link for DJI provider control',
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

    expect(screen.getByTestId('phone-qr-readiness')).toHaveTextContent('QR-ready');
    expect(screen.getByRole('link', { name: 'Phone source link' })).toHaveAttribute(
      'href',
      'https://192.168.1.20:8343/device-link/PAIR1234?workspaceId=ws_device&sourceMode=phone',
    );
    expect(screen.getByRole('link', { name: 'Open phone camera' })).toHaveAttribute(
      'href',
      'https://192.168.1.20:8343/device-link/PAIR1234?workspaceId=ws_device&sourceMode=phone',
    );
    expect(screen.getByTestId('phone-qr-code').querySelector('svg')).toHaveAttribute(
      'aria-label',
      'Phone pairing QR code',
    );
  });

  it('auto-populates the phone HTTPS origin from local-core device-link readiness', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        public_origin: 'https://192.168.0.104:8343',
      }),
    })));

    render(
      createElement(MotionSourceRailPanel, {
        apiUrl: 'http://api.test',
        workspaceId: 'ws_device',
      }),
    );

    await screen.findByText('PAIR1234');
    expect(await screen.findByTestId('phone-qr-code')).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      'http://api.test/api/v1/host/services/device-link-https/health',
      expect.objectContaining({ cache: 'no-store' }),
    );
    expect(screen.getByTestId('phone-public-origin-input')).toHaveValue('https://192.168.0.104:8343');
    expect(screen.getByRole('link', { name: 'Phone source link' })).toHaveAttribute(
      'href',
      'https://192.168.0.104:8343/device-link/PAIR1234?workspaceId=ws_device&sourceMode=phone',
    );
    expect(screen.getByRole('link', { name: 'Open phone camera' })).toHaveAttribute(
      'href',
      'https://192.168.0.104:8343/device-link/PAIR1234?workspaceId=ws_device&sourceMode=phone',
    );
  });

  it('uses the remote workbench HTTPS origin for phone capture links', async () => {
    vi.spyOn(window, 'location', 'get').mockReturnValue(
      new URL('https://remote-workbench.mindscapeai.app/workspaces/ws_device') as unknown as Location,
    );
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        public_origin: 'https://192.168.0.104:8343',
      }),
    })));

    render(
      createElement(MotionSourceRailPanel, {
        apiUrl: 'http://api.test',
        workspaceId: 'ws_device',
      }),
    );

    await screen.findByText('PAIR1234');
    expect(screen.getByTestId('phone-public-origin-input')).toHaveValue('');
    expect(screen.getByTestId('phone-lan-readiness')).toHaveTextContent(
      'Ready for remote phone capture over HTTPS.',
    );
    expect(screen.getByRole('link', { name: 'Phone source link' })).toHaveAttribute(
      'href',
      'https://remote-workbench.mindscapeai.app/device-link/PAIR1234?workspaceId=ws_device&sourceMode=phone',
    );
    expect(screen.getByRole('link', { name: 'Open phone camera' })).toHaveAttribute(
      'href',
      'https://remote-workbench.mindscapeai.app/device-link/PAIR1234?workspaceId=ws_device&sourceMode=phone',
    );
    expect(screen.queryByTestId('phone-source-link-blocked')).toBeNull();
    expect(screen.getByTestId('phone-qr-code')).toBeInTheDocument();
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
    expect(screen.getByTestId('capture-provider-source-slot-count')).toHaveTextContent('1 / 3 active');

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Revoke Phone' }));
    });

    expect(revokeDeviceSession).toHaveBeenCalledWith({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      sessionId: 'session_1',
    });
  });

  it('replays the selected reference lesson when the source companion joins later', async () => {
    function ReferenceLessonHarness() {
      const bridge = useCaptureSourceBridge();

      useEffect(() => {
        bridge.publishReferenceLessonState({
          chapter_ref: 'chapter_alignment',
          title: 'Alignment practice',
          timestamp_ms: 12000,
          poster_ref: 'https://example.test/thumb.jpg',
          focus_cue: 'Keep the body centered.',
        });
      }, [bridge.publishReferenceLessonState]);

      return createElement(CaptureSourceRailFromBridge, {
        bridge,
        showPreview: false,
      });
    }

    render(
      createElement(
        CaptureSourceBridgeProvider,
        {
          apiUrl: 'http://api.test',
          workspaceId: 'ws_device',
        },
        createElement(ReferenceLessonHarness),
      ),
    );

    await screen.findByText('PAIR1234');

    act(() => {
      mocks.socketInput.onOpen();
    });

    expect(mocks.socket.send).toHaveBeenCalledWith({ type: 'workspace_subscribe' });
    expect(mocks.socket.send).toHaveBeenCalledWith({
      type: 'reference_lesson_state',
      reference_lesson_state: expect.objectContaining({
        chapter_ref: 'chapter_alignment',
        title: 'Alignment practice',
      }),
    });

    act(() => {
      mocks.socketInput.onEvent({
        type: 'session_active',
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

    expect(mocks.socket.send).toHaveBeenLastCalledWith({
      type: 'reference_lesson_state',
      reference_lesson_state: expect.objectContaining({
        chapter_ref: 'chapter_alignment',
        focus_cue: 'Keep the body centered.',
      }),
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
