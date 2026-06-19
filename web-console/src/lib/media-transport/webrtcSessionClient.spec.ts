import { describe, expect, it, vi } from 'vitest';

import {
  buildWebRTCSignalWebSocketUrl,
  createLanPeerConnection,
  openWebRTCSignalSocket,
  startDesktopBrowserSourceSession,
  startPhoneBrowserSourceSession,
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

  it('starts phone camera sources with requested facing mode', async () => {
    const getUserMedia = vi.fn(async () => ({
      getTracks: () => [{ stop: vi.fn() }],
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

    await startPhoneBrowserSourceSession({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      deviceSessionId: 'session_1',
      mediaSessionId: 'session_1',
      facingMode: 'user',
    });

    expect(getUserMedia).toHaveBeenCalledWith({
      video: {
        facingMode: { ideal: 'user' },
        width: { ideal: 1280 },
        height: { ideal: 720 },
        frameRate: { max: 30 },
      },
      audio: true,
    });
  });

  it('does not duplicate the source offer while the first offer is still unanswered', async () => {
    const getUserMedia = vi.fn(async () => ({
      getTracks: () => [{ kind: 'video', readyState: 'live', stop: vi.fn() }],
    }));
    const sockets: WebSocketMock[] = [];
    class WebSocketMock {
      static OPEN = 1;
      readyState = WebSocketMock.OPEN;
      onopen: (() => void) | null = null;
      onmessage: ((message: { data: string }) => void) | null = null;
      onerror: (() => void) | null = null;
      onclose: (() => void) | null = null;

      constructor(public url: string) {
        sockets.push(this);
      }

      send = vi.fn();
      close = vi.fn();
    }
    class RTCPeerConnectionMock {
      localDescription: RTCSessionDescriptionInit | null = null;
      remoteDescription: RTCSessionDescriptionInit | null = null;
      addTrack = vi.fn();
      createOffer = vi.fn()
        .mockResolvedValueOnce({ type: 'offer', sdp: 'offer_before_workspace' })
        .mockResolvedValueOnce({ type: 'offer', sdp: 'offer_after_workspace' });
      setLocalDescription = vi.fn(async (description: RTCSessionDescriptionInit) => {
        this.localDescription = description;
      });
      setRemoteDescription = vi.fn(async (description: RTCSessionDescriptionInit) => {
        this.remoteDescription = description;
      });
      close = vi.fn();
      getStats = vi.fn(async () => new Map() as unknown as RTCStatsReport);
    }
    vi.stubGlobal('WebSocket', WebSocketMock);
    vi.stubGlobal('RTCPeerConnection', RTCPeerConnectionMock);
    Object.defineProperty(globalThis.navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia },
    });

    await startPhoneBrowserSourceSession({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      deviceSessionId: 'session_1',
      mediaSessionId: 'session_1',
      facingMode: 'environment',
    });

    sockets[0].onmessage?.({
      data: JSON.stringify({
        type: 'participant_joined',
        sender: 'source',
        workspace_id: 'ws_device',
        device_session_id: 'session_1',
        media_session_id: 'session_1',
        created_at_epoch: 1,
      }),
    });
    await Promise.resolve();
    await Promise.resolve();

    sockets[0].onmessage?.({
      data: JSON.stringify({
        type: 'participant_joined',
        sender: 'workspace',
        workspace_id: 'ws_device',
        device_session_id: 'session_1',
        media_session_id: 'session_1',
        created_at_epoch: 2,
      }),
    });
    await Promise.resolve();
    await Promise.resolve();

    const sentMessages = sockets[0].send.mock.calls.map(([payload]) => JSON.parse(String(payload)));
    expect(sentMessages).toContainEqual({ type: 'offer', sdp: 'offer_before_workspace' });
    expect(sentMessages).not.toContainEqual({ type: 'offer', sdp: 'offer_after_workspace' });
  });

  it('resends the source offer when a workspace receiver rejoins after an answered offer', async () => {
    const getUserMedia = vi.fn(async () => ({
      getTracks: () => [{ kind: 'video', readyState: 'live', stop: vi.fn() }],
    }));
    const sockets: WebSocketMock[] = [];
    class WebSocketMock {
      static OPEN = 1;
      readyState = WebSocketMock.OPEN;
      onopen: (() => void) | null = null;
      onmessage: ((message: { data: string }) => void) | null = null;
      onerror: (() => void) | null = null;
      onclose: (() => void) | null = null;

      constructor(public url: string) {
        sockets.push(this);
      }

      send = vi.fn();
      close = vi.fn();
    }
    class RTCPeerConnectionMock {
      localDescription: RTCSessionDescriptionInit | null = null;
      remoteDescription: RTCSessionDescriptionInit | null = null;
      addTrack = vi.fn();
      createOffer = vi.fn()
        .mockResolvedValueOnce({ type: 'offer', sdp: 'offer_before_answer' })
        .mockResolvedValueOnce({ type: 'offer', sdp: 'offer_after_rejoin' });
      setLocalDescription = vi.fn(async (description: RTCSessionDescriptionInit) => {
        this.localDescription = description;
      });
      setRemoteDescription = vi.fn(async (description: RTCSessionDescriptionInit) => {
        this.remoteDescription = description;
      });
      close = vi.fn();
      getStats = vi.fn(async () => new Map() as unknown as RTCStatsReport);
    }
    vi.stubGlobal('WebSocket', WebSocketMock);
    vi.stubGlobal('RTCPeerConnection', RTCPeerConnectionMock);
    Object.defineProperty(globalThis.navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia },
    });

    await startPhoneBrowserSourceSession({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      deviceSessionId: 'session_1',
      mediaSessionId: 'session_1',
      facingMode: 'environment',
    });

    sockets[0].onmessage?.({
      data: JSON.stringify({
        type: 'participant_joined',
        sender: 'source',
        workspace_id: 'ws_device',
        device_session_id: 'session_1',
        media_session_id: 'session_1',
        created_at_epoch: 1,
      }),
    });
    await Promise.resolve();
    await Promise.resolve();

    sockets[0].onmessage?.({
      data: JSON.stringify({
        type: 'answer',
        sender: 'workspace',
        workspace_id: 'ws_device',
        device_session_id: 'session_1',
        media_session_id: 'session_1',
        sdp: 'answer_before_rejoin',
        created_at_epoch: 2,
      }),
    });
    await Promise.resolve();

    sockets[0].onmessage?.({
      data: JSON.stringify({
        type: 'participant_joined',
        sender: 'workspace',
        workspace_id: 'ws_device',
        device_session_id: 'session_1',
        media_session_id: 'session_1',
        created_at_epoch: 3,
      }),
    });
    await Promise.resolve();
    await Promise.resolve();

    const sentMessages = sockets[0].send.mock.calls.map(([payload]) => JSON.parse(String(payload)));
    expect(sentMessages).toContainEqual({ type: 'offer', sdp: 'offer_before_answer' });
    expect(sentMessages).toContainEqual({ type: 'offer', sdp: 'offer_after_rejoin' });
  });

  it('replaces phone camera video track without closing the media session', async () => {
    const oldVideoTrack = { kind: 'video', readyState: 'live', stop: vi.fn() };
    const audioTrack = { kind: 'audio', readyState: 'live', stop: vi.fn() };
    const newVideoTrack = { kind: 'video', readyState: 'live', stop: vi.fn() };
    class MediaStreamMock {
      constructor(private tracks: any[]) {}

      getTracks = () => this.tracks;
      getVideoTracks = () => this.tracks.filter((track) => track.kind === 'video');
      getAudioTracks = () => this.tracks.filter((track) => track.kind === 'audio');
    }
    const initialStream = new MediaStreamMock([oldVideoTrack, audioTrack]);
    const replacementStream = new MediaStreamMock([newVideoTrack]);
    const getUserMedia = vi.fn()
      .mockResolvedValueOnce(initialStream)
      .mockResolvedValueOnce(replacementStream);
    const replaceTrack = vi.fn();
    const sockets: WebSocketMock[] = [];
    class WebSocketMock {
      static OPEN = 1;
      readyState = WebSocketMock.OPEN;
      onopen: (() => void) | null = null;
      onmessage: ((message: { data: string }) => void) | null = null;
      onerror: (() => void) | null = null;
      onclose: (() => void) | null = null;

      constructor(public url: string) {
        sockets.push(this);
      }

      send = vi.fn();
      close = vi.fn();
    }
    class RTCPeerConnectionMock {
      connectionState: RTCPeerConnectionState = 'new';
      onicecandidate: ((event: RTCPeerConnectionIceEvent) => void) | null = null;
      ontrack: ((event: RTCTrackEvent) => void) | null = null;
      onconnectionstatechange: (() => void) | null = null;

      addTrack = vi.fn();
      createOffer = vi.fn(async () => ({ sdp: 'offer' }));
      setLocalDescription = vi.fn();
      getSenders = vi.fn(() => [{ track: oldVideoTrack, replaceTrack }]);
      getStats = vi.fn(async () => new Map() as unknown as RTCStatsReport);
      close = vi.fn();
    }
    vi.stubGlobal('MediaStream', MediaStreamMock);
    vi.stubGlobal('WebSocket', WebSocketMock);
    vi.stubGlobal('RTCPeerConnection', RTCPeerConnectionMock);
    Object.defineProperty(globalThis.navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia },
    });

    const handle = await startPhoneBrowserSourceSession({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      deviceSessionId: 'session_1',
      mediaSessionId: 'session_1',
      facingMode: 'environment',
    });
    sockets[0].onmessage?.({
      data: JSON.stringify({
        type: 'participant_joined',
        sender: 'source',
        workspace_id: 'ws_device',
        device_session_id: 'session_1',
        media_session_id: 'session_1',
        created_at_epoch: 1,
      }),
    });
    await Promise.resolve();

    const nextStream = await handle.replaceVideoTrack?.({
      facingMode: { ideal: 'user' },
      width: { ideal: 1280 },
      height: { ideal: 720 },
      frameRate: { max: 30 },
    });

    expect(getUserMedia).toHaveBeenNthCalledWith(2, {
      video: {
        facingMode: { ideal: 'user' },
        width: { ideal: 1280 },
        height: { ideal: 720 },
        frameRate: { max: 30 },
      },
      audio: false,
    });
    expect(replaceTrack).toHaveBeenCalledWith(newVideoTrack);
    expect(oldVideoTrack.stop).toHaveBeenCalled();
    expect(sockets[0].close).not.toHaveBeenCalled();
    expect(nextStream?.getVideoTracks()).toEqual([newVideoTrack]);
  });

  it('switches phone capture orientation by replacing the outgoing presentation track', async () => {
    const rawVideoTrack = { kind: 'video', readyState: 'live', stop: vi.fn() };
    const audioTrack = { kind: 'audio', readyState: 'live', stop: vi.fn() };
    const landscapeVideoTrack = { kind: 'video', readyState: 'live', stop: vi.fn() };
    class MediaStreamMock {
      constructor(private tracks: any[]) {}

      getTracks = () => this.tracks;
      getVideoTracks = () => this.tracks.filter((track) => track.kind === 'video');
      getAudioTracks = () => this.tracks.filter((track) => track.kind === 'audio');
    }
    const initialStream = new MediaStreamMock([rawVideoTrack, audioTrack]);
    const getUserMedia = vi.fn().mockResolvedValue(initialStream);
    const canvasInstances: any[] = [];
    const transformedTracks = [landscapeVideoTrack];
    const createElement = vi.spyOn(document, 'createElement').mockImplementation((tagName: string) => {
      if (tagName === 'canvas') {
        const canvas = {
          width: 0,
          height: 0,
          getContext: vi.fn(() => ({
            clearRect: vi.fn(),
            drawImage: vi.fn(),
          })),
          captureStream: vi.fn(() => new MediaStreamMock([transformedTracks.shift()])),
        };
        canvasInstances.push(canvas);
        return canvas as unknown as HTMLElement;
      }
      if (tagName === 'video') {
        return {
          muted: false,
          playsInline: false,
          srcObject: null,
          videoWidth: 640,
          videoHeight: 480,
          play: vi.fn(async () => undefined),
          pause: vi.fn(),
        } as unknown as HTMLElement;
      }
      return document.createElement(tagName);
    });
    const requestAnimationFrame = vi.spyOn(window, 'requestAnimationFrame').mockImplementation(() => 1);
    const cancelAnimationFrame = vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => undefined);
    const replaceTrack = vi.fn();
    const sockets: WebSocketMock[] = [];
    class WebSocketMock {
      static OPEN = 1;
      readyState = WebSocketMock.OPEN;
      onopen: (() => void) | null = null;
      onmessage: ((message: { data: string }) => void) | null = null;
      onerror: (() => void) | null = null;
      onclose: (() => void) | null = null;

      constructor(public url: string) {
        sockets.push(this);
      }

      send = vi.fn();
      close = vi.fn();
    }
    class RTCPeerConnectionMock {
      connectionState: RTCPeerConnectionState = 'new';
      onicecandidate: ((event: RTCPeerConnectionIceEvent) => void) | null = null;
      ontrack: ((event: RTCTrackEvent) => void) | null = null;
      onconnectionstatechange: (() => void) | null = null;

      addTrack = vi.fn();
      createOffer = vi.fn(async () => ({ sdp: 'offer' }));
      setLocalDescription = vi.fn();
      getSenders = vi.fn(() => [{ track: rawVideoTrack, replaceTrack }]);
      getStats = vi.fn(async () => new Map() as unknown as RTCStatsReport);
      close = vi.fn();
    }
    vi.stubGlobal('MediaStream', MediaStreamMock);
    vi.stubGlobal('WebSocket', WebSocketMock);
    vi.stubGlobal('RTCPeerConnection', RTCPeerConnectionMock);
    Object.defineProperty(globalThis.navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia },
    });

    const handle = await startPhoneBrowserSourceSession({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      deviceSessionId: 'session_1',
      mediaSessionId: 'session_1',
      facingMode: 'environment',
      videoOrientation: 'portrait',
    });
    sockets[0].onmessage?.({
      data: JSON.stringify({
        type: 'participant_joined',
        sender: 'source',
        workspace_id: 'ws_device',
        device_session_id: 'session_1',
        media_session_id: 'session_1',
        created_at_epoch: 1,
      }),
    });
    await Promise.resolve();

    const nextStream = await handle.setVideoOrientation?.('landscape');

    expect(canvasInstances).toHaveLength(1);
    expect(canvasInstances[0]).toMatchObject({ width: 1280, height: 720 });
    expect(replaceTrack).toHaveBeenCalledWith(landscapeVideoTrack);
    expect(nextStream?.getVideoTracks()).toEqual([landscapeVideoTrack]);
    expect(sockets[0].close).not.toHaveBeenCalled();

    createElement.mockRestore();
    requestAnimationFrame.mockRestore();
    cancelAnimationFrame.mockRestore();
  });
});
