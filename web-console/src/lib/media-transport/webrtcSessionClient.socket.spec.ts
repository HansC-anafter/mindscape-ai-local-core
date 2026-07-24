import { describe, expect, it, vi } from 'vitest';

import {
  buildWebRTCSignalWebSocketUrl,
  createLanPeerConnection,
  openWebRTCSignalSocket,
  startPhoneBrowserSourceSession,
  startWorkspaceReceiverSession,
} from './webrtcSessionClient';
import {
  defaultSessionInput,
  emitSignal,
  flushMicrotasks,
  installMediaDevices,
  installLanPeerConnectionMock,
  installWebSocketMock,
  sentSignalMessages,
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

  it('routes localhost web-console media signaling directly to the execution backend', () => {
    vi.stubGlobal('window', {
      location: {
        origin: 'http://localhost:8300',
      },
    });

    expect(
      buildWebRTCSignalWebSocketUrl({
        apiBase: '',
        workspaceId: 'ws_device',
        deviceSessionId: 'session_1',
        mediaSessionId: 'session_1',
      }),
    ).toBe(
      'ws://localhost:8200/api/v1/workspaces/ws_device/device-bindings/session_1/media-sessions/session_1/signal',
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

  it('closes a workspace receiver socket without stopping the source media session', () => {
    const { instances } = installWebSocketMock();

    const receiver = startWorkspaceReceiverSession(defaultSessionInput);
    instances[0].onopen?.();
    receiver.stop();

    expect(instances[0].send).toHaveBeenCalledWith(JSON.stringify({ type: 'workspace_join' }));
    expect(instances[0].send).not.toHaveBeenCalledWith(
      JSON.stringify({ type: 'close', reason: 'workspace_stopped' }),
    );
    expect(instances[0].close).toHaveBeenCalled();
  });

  it('closes a replaced source locally without notifying the workspace receiver', async () => {
    const sourceTrack = { kind: 'video', readyState: 'live', stop: vi.fn() };
    installMediaDevices(vi.fn(async () => ({
      getTracks: () => [sourceTrack],
    })));
    const { instances } = installWebSocketMock();
    const onState = vi.fn();
    const onError = vi.fn();

    await startPhoneBrowserSourceSession({
      ...defaultSessionInput,
      facingMode: 'environment',
      onState,
      onError,
    });
    instances[0].onopen?.();

    emitSignal(instances[0], {
      type: 'session_error',
      reason: 'participant_replaced',
      recoverable: true,
      created_at_epoch: 1,
    });
    await flushMicrotasks();

    expect(sentSignalMessages(instances[0])).toEqual([{ type: 'source_join' }]);
    expect(instances[0].close).toHaveBeenCalled();
    expect(sourceTrack.stop).toHaveBeenCalled();
    expect(onState).toHaveBeenCalledWith('closed');
    expect(onError).not.toHaveBeenCalled();
  });

  it('reports non-recoverable source signaling errors after local cleanup', async () => {
    const sourceTrack = { kind: 'video', readyState: 'live', stop: vi.fn() };
    installMediaDevices(vi.fn(async () => ({
      getTracks: () => [sourceTrack],
    })));
    const { instances } = installWebSocketMock();
    const onError = vi.fn();

    await startPhoneBrowserSourceSession({
      ...defaultSessionInput,
      facingMode: 'environment',
      onError,
    });
    instances[0].onopen?.();

    emitSignal(instances[0], {
      type: 'session_error',
      reason: 'unknown_device_session',
      recoverable: false,
      created_at_epoch: 1,
    });
    await flushMicrotasks();

    expect(sentSignalMessages(instances[0])).toEqual([{ type: 'source_join' }]);
    expect(instances[0].close).toHaveBeenCalled();
    expect(sourceTrack.stop).toHaveBeenCalled();
    expect(onError).toHaveBeenCalledWith(expect.objectContaining({
      message: 'unknown_device_session',
    }));
  });

  it('notifies the workspace receiver when the source is stopped directly', async () => {
    const sourceTrack = { kind: 'video', readyState: 'live', stop: vi.fn() };
    installMediaDevices(vi.fn(async () => ({
      getTracks: () => [sourceTrack],
    })));
    const { instances } = installWebSocketMock();

    const source = await startPhoneBrowserSourceSession({
      ...defaultSessionInput,
      facingMode: 'environment',
    });
    instances[0].onopen?.();

    source.stop();

    expect(sentSignalMessages(instances[0])).toContainEqual({
      type: 'close',
      reason: 'source_stopped',
    });
    expect(instances[0].close).toHaveBeenCalled();
    expect(sourceTrack.stop).toHaveBeenCalled();
  });
});
