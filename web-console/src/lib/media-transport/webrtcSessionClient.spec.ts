import { describe, expect, it, vi } from 'vitest';

import {
  buildWebRTCSignalWebSocketUrl,
  createLanPeerConnection,
  openWebRTCSignalSocket,
  startDesktopBrowserSourceSession,
} from './webrtcSessionClient';

describe('webrtcSessionClient', () => {
  it('builds workspace device media signaling WebSocket URLs', () => {
    expect(
      buildWebRTCSignalWebSocketUrl({
        apiBase: 'https://console.test/',
        workspaceId: 'ws 1',
        deviceSessionId: 'device session',
        mediaSessionId: 'media session',
      }),
    ).toBe(
      'wss://console.test/api/v1/workspaces/ws%201/device-bindings/device%20session/media-sessions/media%20session/signal',
    );
  });

  it('sends JSON media signaling messages only after the socket is open', () => {
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

    const socket = openWebRTCSignalSocket({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      deviceSessionId: 'session_1',
      mediaSessionId: 'session_1',
    });
    socket.send({ type: 'source_join' });
    expect(instances[0].send).not.toHaveBeenCalled();

    instances[0].readyState = WebSocketMock.OPEN;
    socket.send({ type: 'source_join' });

    expect(instances[0].url).toBe(
      'ws://api.test/api/v1/workspaces/ws_device/device-bindings/session_1/media-sessions/session_1/signal',
    );
    expect(instances[0].send).toHaveBeenCalledWith(JSON.stringify({ type: 'source_join' }));
  });

  it('creates LAN-only peer connections and emits ICE candidates through callbacks', () => {
    const configs: RTCConfiguration[] = [];
    const statsReport = new Map() as unknown as RTCStatsReport;
    class RTCPeerConnectionMock {
      connectionState: RTCPeerConnectionState = 'new';
      onicecandidate: ((event: RTCPeerConnectionIceEvent) => void) | null = null;
      ontrack: ((event: RTCTrackEvent) => void) | null = null;
      onconnectionstatechange: (() => void) | null = null;

      constructor(config: RTCConfiguration) {
        configs.push(config);
      }

      getStats = vi.fn(async () => statsReport);
    }
    vi.stubGlobal('RTCPeerConnection', RTCPeerConnectionMock);
    const onIceCandidate = vi.fn();
    const onStats = vi.fn();

    const peer = createLanPeerConnection({ onIceCandidate, onStats });
    peer.onicecandidate?.({
      candidate: {
        toJSON: () => ({ candidate: 'candidate:1' }),
      },
    } as RTCPeerConnectionIceEvent);
    (peer as unknown as RTCPeerConnectionMock).connectionState = 'connected';
    peer.onconnectionstatechange?.({} as Event);

    expect(configs).toEqual([{ iceServers: [] }]);
    expect(onIceCandidate).toHaveBeenCalledWith({ candidate: 'candidate:1' });
    return Promise.resolve().then(() => {
      expect(onStats).toHaveBeenCalledWith('connected', statsReport);
    });
  });

  it('starts desktop camera sources with device-scoped video constraints and no audio', async () => {
    const tracks = [{ stop: vi.fn() }];
    const getUserMedia = vi.fn(async () => ({
      getTracks: () => tracks,
    }));
    class WebSocketMock {
      static OPEN = 1;
      readyState = WebSocketMock.OPEN;
      onopen: (() => void) | null = null;
      onmessage: ((message: { data: string }) => void) | null = null;
      onerror: (() => void) | null = null;
      onclose: (() => void) | null = null;

      constructor(public url: string) {}

      send = vi.fn();
      close = vi.fn();
    }
    vi.stubGlobal('WebSocket', WebSocketMock);
    Object.defineProperty(globalThis.navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia },
    });

    await startDesktopBrowserSourceSession({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      deviceSessionId: 'session_1',
      mediaSessionId: 'session_1',
      sourceKind: 'virtual_camera',
      deviceId: 'obs_1',
    });

    expect(getUserMedia).toHaveBeenCalledWith({
      video: {
        deviceId: { exact: 'obs_1' },
        width: { ideal: 1280 },
        height: { ideal: 720 },
        frameRate: { max: 30 },
      },
      audio: false,
    });
  });
});
