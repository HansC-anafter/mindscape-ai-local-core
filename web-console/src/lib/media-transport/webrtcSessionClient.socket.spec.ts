import { describe, expect, it, vi } from 'vitest';

import {
  buildWebRTCSignalWebSocketUrl,
  createLanPeerConnection,
  openWebRTCSignalSocket,
} from './webrtcSessionClient';
import {
  defaultSessionInput,
  installLanPeerConnectionMock,
  installWebSocketMock,
} from './webrtcSessionClient.test-support';

describe('webrtcSessionClient signal socket and peer connection', () => {
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
    const { instances, WebSocketMock } = installWebSocketMock(0);

    const socket = openWebRTCSignalSocket(defaultSessionInput);
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
    const { configs, statsReport } = installLanPeerConnectionMock();
    const onIceCandidate = vi.fn();
    const onStats = vi.fn();

    const peer = createLanPeerConnection({ onIceCandidate, onStats });
    peer.onicecandidate?.({
      candidate: {
        toJSON: () => ({ candidate: 'candidate:1' }),
      },
    } as RTCPeerConnectionIceEvent);
    (peer as unknown as { connectionState: RTCPeerConnectionState }).connectionState = 'connected';
    peer.onconnectionstatechange?.({} as Event);

    expect(configs).toEqual([{ iceServers: [] }]);
    expect(onIceCandidate).toHaveBeenCalledWith({ candidate: 'candidate:1' });
    return Promise.resolve().then(() => {
      expect(onStats).toHaveBeenCalledWith('connected', statsReport);
    });
  });
});
