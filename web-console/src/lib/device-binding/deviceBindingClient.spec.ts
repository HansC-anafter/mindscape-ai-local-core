import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  buildDeviceControlWebSocketUrl,
  buildDevicePairingCodeUrl,
  buildDeviceRevokeUrl,
  buildDeviceSessionsUrl,
  buildWorkspaceDeviceControlWebSocketUrl,
  createDevicePairingCode,
  listActiveDeviceSessions,
  openDeviceControlSocket,
} from './deviceBindingClient';

describe('deviceBindingClient', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('builds REST and WebSocket URLs under workspace device-bindings', () => {
    expect(
      buildDevicePairingCodeUrl({
        apiBase: 'http://api.test/',
        workspaceId: 'ws 1',
      }),
    ).toBe('http://api.test/api/v1/workspaces/ws%201/device-bindings/pairing-codes');
    expect(
      buildDeviceRevokeUrl({
        apiBase: 'http://api.test',
        workspaceId: 'ws 1',
        sessionId: 'session 1',
      }),
    ).toBe('http://api.test/api/v1/workspaces/ws%201/device-bindings/session%201/revoke');
    expect(
      buildDeviceSessionsUrl({
        apiBase: 'http://api.test',
        workspaceId: 'ws 1',
      }),
    ).toBe('http://api.test/api/v1/workspaces/ws%201/device-bindings/sessions');
    expect(
      buildDeviceControlWebSocketUrl({
        apiBase: 'https://console.test',
        workspaceId: 'ws 1',
        pairingCode: 'ABCD1234',
      }),
    ).toBe('wss://console.test/api/v1/workspaces/ws%201/device-bindings/ABCD1234/control');
    expect(
      buildWorkspaceDeviceControlWebSocketUrl({
        apiBase: 'https://console.test',
        workspaceId: 'ws 1',
      }),
    ).toBe('wss://console.test/api/v1/workspaces/ws%201/device-bindings/control');
  });

  it('uses the backend port directly for local 8300 device binding control', () => {
    vi.spyOn(window, 'location', 'get').mockReturnValue(
      new URL('http://localhost:8300/workspaces/ws_device') as unknown as Location,
    );

    expect(
      buildDeviceSessionsUrl({
        apiBase: '',
        workspaceId: 'ws_device',
      }),
    ).toBe('http://localhost:8200/api/v1/workspaces/ws_device/device-bindings/sessions');
    expect(
      buildWorkspaceDeviceControlWebSocketUrl({
        apiBase: '',
        workspaceId: 'ws_device',
      }),
    ).toBe('ws://localhost:8200/api/v1/workspaces/ws_device/device-bindings/control');
  });

  it('sends JSON control messages only after socket open', () => {
    const instances: WebSocketMock[] = [];
    class WebSocketMock {
      static OPEN = 1;
      readyState = 0;
      sent: string[] = [];
      onopen: (() => void) | null = null;
      onmessage: ((message: { data: string }) => void) | null = null;
      onerror: (() => void) | null = null;
      onclose: (() => void) | null = null;

      constructor(public url: string) {
        instances.push(this);
      }

      send = vi.fn((payload: string) => {
        this.sent.push(payload);
      });
      close = vi.fn();
    }
    vi.stubGlobal('WebSocket', WebSocketMock);

    const socket = openDeviceControlSocket({
      apiBase: 'http://api.test',
      workspaceId: 'ws_test',
      pairingCode: 'PAIR1234',
    });
    socket.send({ type: 'workspace_subscribe' });
    expect(instances[0].send).not.toHaveBeenCalled();

    instances[0].readyState = WebSocketMock.OPEN;
    socket.send({ type: 'workspace_subscribe' });

    expect(instances[0].url).toBe(
      'ws://api.test/api/v1/workspaces/ws_test/device-bindings/PAIR1234/control',
    );
    expect(instances[0].send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'workspace_subscribe' }),
    );
  });

  it('can request a bounded pairing code TTL', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        workspace_id: 'ws_test',
        pairing_code: 'PAIR1234',
        expires_at_epoch: 1000,
        expires_in_seconds: 600,
        device_link_path: '/device-link/PAIR1234',
      }),
    }));
    vi.stubGlobal('fetch', fetchMock);

    await createDevicePairingCode({
      apiBase: 'http://api.test',
      workspaceId: 'ws_test',
      expiresInSeconds: 600,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/api/v1/workspaces/ws_test/device-bindings/pairing-codes',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ expires_in_seconds: 600 }),
      }),
    );
  });

  it('lists active device sessions without caching', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => [
        {
          session_id: 'session_1',
          workspace_id: 'ws_test',
          pairing_code: 'PAIR1234',
          device_id: 'obs_virtual',
          display_name: 'OBS Virtual Camera',
          source_types: ['virtual_camera'],
          state: 'active',
          created_at_epoch: 1,
          updated_at_epoch: 2,
          expires_at_epoch: 62,
        },
      ],
    }));
    vi.stubGlobal('fetch', fetchMock);

    const sessions = await listActiveDeviceSessions({
      apiBase: 'http://api.test',
      workspaceId: 'ws_test',
    });

    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/api/v1/workspaces/ws_test/device-bindings/sessions',
      { cache: 'no-store' },
    );
    expect(sessions[0].display_name).toBe('OBS Virtual Camera');
  });
});
