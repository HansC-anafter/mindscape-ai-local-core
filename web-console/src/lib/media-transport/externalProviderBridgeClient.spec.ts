import { act } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { startExternalProviderBridgeSession } from './externalProviderBridgeClient';

const mocks = vi.hoisted(() => ({
  controlInput: null as any,
  controlSocket: {
    send: vi.fn(),
    close: vi.fn(),
    raw: {},
  },
  createLiveMediaSession: vi.fn(async (input) => ({
    session: {
      workspace_id: input.workspaceId,
      device_session_id: input.deviceSessionId,
      media_session_id: 'media_provider',
      stream_path: 'live/provider',
      source_kind: 'external_provider_camera',
      relay_profile: 'public',
      capabilities: input.capabilities,
      analysis_reserved: true,
      state: 'waiting_for_publisher',
      endpoints: {
        whip_publish_url: 'https://media.test/live/provider/whip',
        whep_preview_url: 'https://media.test/live/provider/whep',
        rtmps_publish_url: 'rtmps://media.test:1936/live/provider',
        rtsps_receiver_url: 'rtsps://media.test:8322/live/provider',
      },
      receiver_descriptor_ref: 'live-media-receiver:media_provider',
      created_at_epoch: 1,
      updated_at_epoch: 1,
      expires_at_epoch: 3601,
    },
    tokens: {
      publish: 'publish_token',
      preview: 'preview_token',
      receiver: 'receiver_token',
    },
  })),
  stopLiveMediaSession: vi.fn(async () => ({ state: 'stopped' })),
  publisherHandle: {
    stop: vi.fn(),
    peerConnection: { connectionState: 'connected' },
  },
  publisherInput: null as any,
}));

vi.mock('@/lib/device-binding/deviceBindingClient', () => ({
  openDeviceControlSocket: vi.fn((input) => {
    mocks.controlInput = input;
    return mocks.controlSocket;
  }),
}));

vi.mock('./liveMediaSessionClient', () => ({
  createLiveMediaSession: mocks.createLiveMediaSession,
  stopLiveMediaSession: mocks.stopLiveMediaSession,
}));

vi.mock('./whipPublisherClient', () => ({
  startWhipPublisher: vi.fn(async (input) => {
    mocks.publisherInput = input;
    return mocks.publisherHandle;
  }),
}));

function createStreamMock({ audio = false } = {}) {
  const videoTrack = { kind: 'video', readyState: 'live', stop: vi.fn() };
  const audioTrack = { kind: 'audio', readyState: 'live', stop: vi.fn() };
  const tracks = audio ? [videoTrack, audioTrack] : [videoTrack];
  return {
    stream: {
      getTracks: () => tracks,
      getVideoTracks: () => [videoTrack],
      getAudioTracks: () => (audio ? [audioTrack] : []),
    } as unknown as MediaStream,
    videoTrack,
  };
}

async function pairSource(sessionId = 'session_provider') {
  await act(async () => {
    mocks.controlInput.onEvent({
      type: 'session_paired',
      workspace_id: 'ws_device',
      session_id: sessionId,
      active_sessions: [],
    });
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe('externalProviderBridgeClient', () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
    mocks.controlInput = null;
    mocks.publisherInput = null;
  });

  it('pairs as an external provider and publishes the same live media path through WHIP', async () => {
    const { stream } = createStreamMock({ audio: true });
    const onState = vi.fn();
    const handle = startExternalProviderBridgeSession({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      pairingCode: 'PAIR1234',
      stream,
      deviceId: 'provider_bridge_1',
      providerFamily: 'dji_ground_imaging',
      heartbeatIntervalMs: 0,
      onState,
    });

    mocks.controlInput.onOpen();
    expect(mocks.controlSocket.send).toHaveBeenCalledWith(expect.objectContaining({
      type: 'source_join',
      device_id: 'provider_bridge_1',
      source_types: ['external_provider_camera'],
      metadata: expect.objectContaining({ provider_family: 'dji_ground_imaging' }),
    }));
    await pairSource();

    expect(mocks.createLiveMediaSession).toHaveBeenCalledWith({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      deviceSessionId: 'session_provider',
      sourceKind: 'external_provider_camera',
      capabilities: ['video', 'audio'],
      analysisReserved: true,
    });
    expect(mocks.publisherInput).toEqual(expect.objectContaining({
      endpoint: 'https://media.test/live/provider/whip',
      token: 'publish_token',
      stream,
    }));
    expect(handle.deviceSessionId).toBe('session_provider');
    expect(handle.mediaSessionId).toBe('media_provider');
    expect(handle.peerConnection).toBe(mocks.publisherHandle.peerConnection);
    expect(onState).toHaveBeenCalledWith('source_paired');
  });

  it('does not create a second publisher on heartbeat acknowledgements', async () => {
    const { stream } = createStreamMock();
    startExternalProviderBridgeSession({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      pairingCode: 'PAIR1234',
      stream,
      heartbeatIntervalMs: 0,
    });
    await pairSource();

    await act(async () => {
      mocks.controlInput.onEvent({
        type: 'heartbeat_ack',
        workspace_id: 'ws_device',
        session_id: 'session_provider',
      });
      await Promise.resolve();
    });

    expect(mocks.createLiveMediaSession).toHaveBeenCalledTimes(1);
  });

  it('keeps bounded control heartbeats and performs explicit media cleanup on stop', async () => {
    vi.useFakeTimers();
    const { stream, videoTrack } = createStreamMock();
    const handle = startExternalProviderBridgeSession({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      pairingCode: 'PAIR1234',
      stream,
      heartbeatIntervalMs: 1000,
    });
    await pairSource();

    vi.advanceTimersByTime(1000);
    expect(mocks.controlSocket.send).toHaveBeenCalledWith({ type: 'heartbeat' });

    handle.stop();
    await Promise.resolve();

    expect(mocks.publisherHandle.stop).toHaveBeenCalledTimes(1);
    expect(mocks.stopLiveMediaSession).toHaveBeenCalledWith({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      deviceSessionId: 'session_provider',
      mediaSessionId: 'media_provider',
      keepalive: true,
    });
    expect(mocks.controlSocket.send).toHaveBeenCalledWith({ type: 'session_close' });
    expect(mocks.controlSocket.close).toHaveBeenCalled();
    expect(videoTrack.stop).not.toHaveBeenCalled();
  });

  it('stops bridge-owned tracks only when requested', () => {
    const { stream, videoTrack } = createStreamMock();
    const handle = startExternalProviderBridgeSession({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      pairingCode: 'PAIR1234',
      stream,
      stopTracksOnStop: true,
    });

    handle.stop();

    expect(videoTrack.stop).toHaveBeenCalledTimes(1);
  });

  it('reports media admission failures without opening a legacy P2P fallback', async () => {
    mocks.createLiveMediaSession.mockRejectedValueOnce(new Error('codec_unsupported'));
    const onError = vi.fn();
    const onState = vi.fn();
    const { stream } = createStreamMock();
    startExternalProviderBridgeSession({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      pairingCode: 'PAIR1234',
      stream,
      heartbeatIntervalMs: 0,
      onError,
      onState,
    });

    await pairSource();

    expect(onError).toHaveBeenCalledWith(expect.objectContaining({
      message: 'codec_unsupported',
    }));
    expect(onState).toHaveBeenCalledWith('error');
    expect(mocks.publisherInput).toBeNull();
  });

  it('rejects bridge sessions without a live video stream', () => {
    const stream = {
      getTracks: () => [],
      getVideoTracks: () => [],
      getAudioTracks: () => [],
    } as unknown as MediaStream;

    expect(() => startExternalProviderBridgeSession({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      pairingCode: 'PAIR1234',
      stream,
    })).toThrow('external_provider_camera_stream_required');
  });
});
