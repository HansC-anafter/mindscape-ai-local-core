import { describe, expect, it, vi } from 'vitest';

import {
  buildDeviceControlWebSocketUrl,
  buildDevicePairingCodeUrl,
  buildDeviceRevokeUrl,
  openDeviceControlSocket,
} from './deviceBindingClient';

describe('deviceBindingClient', () => {
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
      buildDeviceControlWebSocketUrl({
        apiBase: 'https://console.test',
        workspaceId: 'ws 1',
        pairingCode: 'ABCD1234',
      }),
    ).toBe('wss://console.test/api/v1/workspaces/ws%201/device-bindings/ABCD1234/control');
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
});
