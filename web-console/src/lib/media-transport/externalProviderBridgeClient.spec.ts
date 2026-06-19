import { afterEach, describe, expect, it, vi } from 'vitest';

import { startExternalProviderBridgeSession } from './externalProviderBridgeClient';

type WebSocketMessageHandler = ((message: { data: string }) => void) | null;

function createStreamMock() {
  const videoTrack = {
    kind: 'video',
    readyState: 'live',
    stop: vi.fn(),
  };
  const stream = {
    getTracks: () => [videoTrack],
    getVideoTracks: () => [videoTrack],
  } as unknown as MediaStream;
  return { stream, videoTrack };
}

function installSocketAndPeerMocks() {
  const sockets: WebSocketMock[] = [];
  const peers: RTCPeerConnectionMock[] = [];

  class WebSocketMock {
    static OPEN = 1;
    readyState = WebSocketMock.OPEN;
    sent: string[] = [];
    onopen: (() => void) | null = null;
    onmessage: WebSocketMessageHandler = null;
    onerror: (() => void) | null = null;
    onclose: (() => void) | null = null;

    constructor(public url: string) {
      sockets.push(this);
    }

    send = vi.fn((payload: string) => {
      this.sent.push(payload);
    });
    close = vi.fn();
  }

  class RTCPeerConnectionMock {
    connectionState: RTCPeerConnectionState = 'new';
    localDescription: RTCSessionDescriptionInit | null = null;
    remoteDescription: RTCSessionDescriptionInit | null = null;
    onicecandidate: ((event: RTCPeerConnectionIceEvent) => void) | null = null;
    ontrack: ((event: RTCTrackEvent) => void) | null = null;
    onconnectionstatechange: (() => void) | null = null;
    addTrack = vi.fn();
    addIceCandidate = vi.fn();
    close = vi.fn();
    createOffer = vi.fn(async () => ({ type: 'offer', sdp: 'offer_sdp' } as RTCSessionDescriptionInit));
    setLocalDescription = vi.fn(async (description: RTCSessionDescriptionInit) => {
      this.localDescription = description;
    });
    setRemoteDescription = vi.fn(async (description: RTCSessionDescriptionInit) => {
      this.remoteDescription = description;
    });
    getStats = vi.fn(async () => new Map() as unknown as RTCStatsReport);

    constructor(public config: RTCConfiguration) {
      peers.push(this);
    }
  }

  vi.stubGlobal('WebSocket', WebSocketMock);
  vi.stubGlobal('RTCPeerConnection', RTCPeerConnectionMock);
  return { sockets, peers };
}

function emitSocketEvent(socket: { onmessage: WebSocketMessageHandler }, event: Record<string, unknown>) {
  socket.onmessage?.({ data: JSON.stringify(event) });
}

describe('externalProviderBridgeClient', () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('joins device binding as an external provider camera and publishes its stream over the existing media lane', async () => {
    const { sockets, peers } = installSocketAndPeerMocks();
    const { stream, videoTrack } = createStreamMock();
    const onState = vi.fn();

    startExternalProviderBridgeSession({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      pairingCode: 'PAIR1234',
      stream,
      deviceId: 'provider_bridge_1',
      displayName: 'DJI bridge',
      providerFamily: 'dji_ground_imaging',
      providerBackend: 'dji_mobile_companion',
      heartbeatIntervalMs: 0,
      metadata: {
        device_model: 'DJI Osmo',
      },
      onState,
    });

    expect(sockets[0].url).toBe(
      'ws://api.test/api/v1/workspaces/ws_device/device-bindings/PAIR1234/control',
    );
    sockets[0].onopen?.();
    expect(JSON.parse(sockets[0].sent[0])).toMatchObject({
      type: 'source_join',
      device_id: 'provider_bridge_1',
      display_name: 'DJI bridge',
      source_types: ['external_provider_camera'],
      metadata: {
        capture_surface: 'external_provider_bridge',
        provider_family: 'dji_ground_imaging',
        provider_backend: 'dji_mobile_companion',
        device_model: 'DJI Osmo',
      },
    });

    emitSocketEvent(sockets[0], {
      type: 'session_paired',
      workspace_id: 'ws_device',
      session_id: 'session_provider',
      active_sessions: [],
    });
    expect(sockets[1].url).toBe(
      'ws://api.test/api/v1/workspaces/ws_device/device-bindings/session_provider/media-sessions/session_provider/signal',
    );
    sockets[1].onopen?.();
    expect(JSON.parse(sockets[1].sent[0])).toEqual({ type: 'source_join' });

    emitSocketEvent(sockets[1], {
      type: 'participant_joined',
      workspace_id: 'ws_device',
      device_session_id: 'session_provider',
      media_session_id: 'session_provider',
      sender: 'source',
      created_at_epoch: 1,
    });
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    expect(peers[0].config).toEqual({ iceServers: [] });
    expect(peers[0].addTrack).toHaveBeenCalledWith(videoTrack, stream);
    expect(peers[0].setLocalDescription).toHaveBeenCalledWith({
      type: 'offer',
      sdp: 'offer_sdp',
    });
    expect(JSON.parse(sockets[1].sent[1])).toEqual({
      type: 'offer',
      sdp: 'offer_sdp',
    });
    expect(onState).toHaveBeenCalledWith('source_paired');
    expect(onState).toHaveBeenCalledWith('offer_sent');
  });

  it('does not duplicate the provider offer while the first offer is still unanswered', async () => {
    const { sockets } = installSocketAndPeerMocks();
    const { stream } = createStreamMock();

    startExternalProviderBridgeSession({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      pairingCode: 'PAIR1234',
      stream,
      heartbeatIntervalMs: 0,
    });

    sockets[0].onopen?.();
    emitSocketEvent(sockets[0], {
      type: 'session_paired',
      workspace_id: 'ws_device',
      session_id: 'session_provider',
      active_sessions: [],
    });
    sockets[1].onopen?.();
    emitSocketEvent(sockets[1], {
      type: 'participant_joined',
      workspace_id: 'ws_device',
      device_session_id: 'session_provider',
      media_session_id: 'session_provider',
      sender: 'source',
      created_at_epoch: 1,
    });
    await Promise.resolve();
    await Promise.resolve();
    emitSocketEvent(sockets[1], {
      type: 'participant_joined',
      workspace_id: 'ws_device',
      device_session_id: 'session_provider',
      media_session_id: 'session_provider',
      sender: 'workspace',
      created_at_epoch: 2,
    });
    await Promise.resolve();
    await Promise.resolve();

    const offers = sockets[1].sent
      .map((payload) => JSON.parse(payload))
      .filter((message) => message.type === 'offer');
    expect(offers).toHaveLength(1);
  });

  it('resends the provider offer when a workspace receiver rejoins after an answered offer', async () => {
    const { sockets } = installSocketAndPeerMocks();
    const { stream } = createStreamMock();

    startExternalProviderBridgeSession({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      pairingCode: 'PAIR1234',
      stream,
      heartbeatIntervalMs: 0,
    });

    sockets[0].onopen?.();
    emitSocketEvent(sockets[0], {
      type: 'session_paired',
      workspace_id: 'ws_device',
      session_id: 'session_provider',
      active_sessions: [],
    });
    sockets[1].onopen?.();
    emitSocketEvent(sockets[1], {
      type: 'participant_joined',
      workspace_id: 'ws_device',
      device_session_id: 'session_provider',
      media_session_id: 'session_provider',
      sender: 'source',
      created_at_epoch: 1,
    });
    await Promise.resolve();
    await Promise.resolve();
    emitSocketEvent(sockets[1], {
      type: 'answer',
      workspace_id: 'ws_device',
      device_session_id: 'session_provider',
      media_session_id: 'session_provider',
      sender: 'workspace',
      sdp: 'answer_sdp',
      created_at_epoch: 2,
    });
    await Promise.resolve();
    emitSocketEvent(sockets[1], {
      type: 'participant_joined',
      workspace_id: 'ws_device',
      device_session_id: 'session_provider',
      media_session_id: 'session_provider',
      sender: 'workspace',
      created_at_epoch: 3,
    });
    await Promise.resolve();
    await Promise.resolve();

    const offers = sockets[1].sent
      .map((payload) => JSON.parse(payload))
      .filter((message) => message.type === 'offer');
    expect(offers).toHaveLength(2);
  });

  it('sends bounded heartbeats and leaves bridge-owned stream tracks alive by default on stop', () => {
    vi.useFakeTimers();
    const { sockets, peers } = installSocketAndPeerMocks();
    const { stream, videoTrack } = createStreamMock();
    const handle = startExternalProviderBridgeSession({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      pairingCode: 'PAIR1234',
      stream,
      heartbeatIntervalMs: 1000,
    });
    sockets[0].onopen?.();
    emitSocketEvent(sockets[0], {
      type: 'session_paired',
      workspace_id: 'ws_device',
      session_id: 'session_provider',
      active_sessions: [],
    });

    vi.advanceTimersByTime(1000);
    expect(sockets[0].sent.map((payload) => JSON.parse(payload).type)).toContain('heartbeat');

    handle.stop();

    expect(videoTrack.stop).not.toHaveBeenCalled();
    expect(sockets[0].close).toHaveBeenCalled();
    expect(sockets[1].close).toHaveBeenCalled();
    expect(peers).toHaveLength(0);
  });

  it('rejects bridge sessions that do not provide a live video stream', () => {
    const stream = {
      getTracks: () => [],
      getVideoTracks: () => [],
    } as unknown as MediaStream;

    expect(() => startExternalProviderBridgeSession({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      pairingCode: 'PAIR1234',
      stream,
    })).toThrow('external_provider_camera_stream_required');
  });
});
