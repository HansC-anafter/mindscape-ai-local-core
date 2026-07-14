import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createElement, useEffect } from 'react';

import {
  mocks,
  openProviderSetup,
  resetMotionSourceRailPanelTestState,
  waitForPairingFlow,
} from './motionSourceRailPanelTestHarness';
import { MotionSourceRailPanel } from './MotionSourceRailPanel';
import {
  CaptureSourceBridgeProvider,
  useCaptureSourceBridge,
} from './capture-bridge/CaptureSourceBridgeProvider';
import { CaptureSourceRailFromBridge } from './capture-bridge/CaptureSourceRail';
import {
  openWorkspaceDeviceControlSocket,
  revokeDeviceSession,
} from '@/lib/device-binding/deviceBindingClient';

describe('MotionSourceRailPanel', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      json: async () => ({}),
    })));
  });

  afterEach(() => {
    resetMotionSourceRailPanelTestState();
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
    await waitForPairingFlow();
    expect(openWorkspaceDeviceControlSocket).toHaveBeenCalledTimes(1);
    expect(openWorkspaceDeviceControlSocket).toHaveBeenCalledWith(
      expect.objectContaining({
        apiBase: 'http://api.test',
        workspaceId: 'ws_device',
      }),
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
    expect(screen.getByTestId('capture-provider-tool-phone')).toBeEnabled();
    expect(screen.getByTestId('capture-provider-tool-desktop')).toBeEnabled();
    expect(screen.getByTestId('capture-provider-tool-external')).toBeEnabled();
    expect(screen.queryByRole('link', { name: 'Phone source link' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'Desktop camera source link' })).toBeNull();
    expect(screen.queryByTestId('external-provider-bridge-card')).toBeNull();
    expect(screen.queryByTestId('external-provider-connection-guide')).toBeNull();
    expect(screen.queryByTestId('capture-relay-launcher-card')).toBeNull();

    openProviderSetup('phone');
    expect(screen.getByRole('link', { name: 'Phone source link' })).toHaveAttribute(
      'href',
      'http://localhost:3000/device-link/PAIR1234?workspaceId=ws_device&sourceMode=phone',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Close provider setup' }));

    openProviderSetup('desktop');
    expect(screen.getByRole('link', { name: 'Desktop camera source link' })).toHaveAttribute(
      'href',
      'http://localhost:3000/device-link/PAIR1234?workspaceId=ws_device&sourceMode=camera',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Close provider setup' }));

    const externalWizard = openProviderSetup('external');
    expect(externalWizard.className).toContain('flex-col');
    expect(externalWizard.className).toContain('overflow-hidden');
    expect(screen.getByTestId('capture-provider-wizard-body').className).toContain('min-h-0');
    expect(screen.getByTestId('capture-provider-wizard-body').className).toContain('flex-1');
    expect(screen.getByTestId('capture-provider-wizard-body').className).toContain('overflow-auto');
    expect(screen.getByTestId('external-provider-bridge-card')).toHaveTextContent(
      'External bridge',
    );
    expect(screen.getByTestId('external-provider-pairing-code')).toHaveTextContent('PAIR1234');
    expect(screen.getByTestId('external-provider-bridge-payload')).toHaveTextContent(
      '"transport": "device_binding_control_ws"',
    );
    expect(screen.getByTestId('external-provider-bridge-payload')).toHaveTextContent(
      '"api_base": "http://api.test"',
    );
    expect(screen.getByTestId('external-provider-bridge-payload')).toHaveTextContent(
      '"pairing_code": "PAIR1234"',
    );
    expect(screen.getByTestId('external-provider-bridge-payload')).toHaveTextContent(
      '"control_ws_url": "ws://api.test/api/v1/workspaces/ws_device/device-bindings/PAIR1234/control"',
    );
    expect(screen.getByTestId('external-provider-bridge-payload')).toHaveTextContent(
      '"source_types": [',
    );
    expect(screen.getByTestId('external-provider-bridge-payload')).toHaveTextContent(
      '"external_provider_camera"',
    );
    expect(screen.getByRole('button', { name: 'Copy code' })).toBeEnabled();
    expect(screen.getByTestId('external-provider-connection-guide')).toHaveTextContent(
      'External provider connection guide',
    );
    expect(screen.getByTestId('external-provider-connection-guide')).toHaveTextContent(
      'USB webcam source',
    );
    expect(screen.getByTestId('external-provider-connection-guide')).toHaveTextContent(
      'Session RTMPS publisher',
    );
    expect(screen.getByTestId('external-provider-connection-guide')).toHaveTextContent(
      'Gimbal-mounted camera',
    );
    expect(screen.getByTestId('capture-relay-launcher-card')).toHaveTextContent(
      'Local RTMP to OBS Virtual Camera',
    );
    expect(screen.getByTestId('local-rtmp-relay-fallback')).toHaveTextContent(
      'Local host relay',
    );
    expect(screen.getByRole('link', { name: 'Open OBS Virtual Camera source' })).toHaveAttribute(
      'href',
      'http://localhost:3000/device-link/PAIR1234?workspaceId=ws_device&sourceMode=camera',
    );
    expect(screen.getByTestId('external-provider-advanced-payload')).toHaveTextContent(
      'Advanced bridge payload',
    );
    expect(screen.getByTestId('external-provider-copy-payload')).toBeEnabled();
  });

  it('renders a scannable phone QR only for HTTPS LAN origins', async () => {
    render(
      createElement(MotionSourceRailPanel, {
        apiUrl: 'http://api.test',
        workspaceId: 'ws_device',
      }),
    );

    await waitForPairingFlow();
    openProviderSetup('phone');

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

    await waitForPairingFlow();
    openProviderSetup('phone');
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

    await waitForPairingFlow();
    openProviderSetup('phone');
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

    await waitForPairingFlow();

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
          children: createElement(ReferenceLessonHarness),
        },
      ),
    );

    await waitForPairingFlow();

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

    await waitForPairingFlow();
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
