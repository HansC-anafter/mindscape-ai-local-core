import { afterEach, vi } from 'vitest';

export const defaultSessionInput = {
  apiBase: 'http://api.test',
  workspaceId: 'ws_device',
  deviceSessionId: 'session_1',
  mediaSessionId: 'session_1',
} as const;

export class MediaStreamMock {
  constructor(private tracks: any[]) {}

  getTracks = () => this.tracks;
  getVideoTracks = () => this.tracks.filter((track) => track.kind === 'video');
  getAudioTracks = () => this.tracks.filter((track) => track.kind === 'audio');
}

export function installMediaStreamMock() {
  vi.stubGlobal('MediaStream', MediaStreamMock);
}

export function installMediaDevices(getUserMedia: ReturnType<typeof vi.fn>) {
  Object.defineProperty(globalThis.navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia },
  });
}

export function installWebSocketMock(initialReadyState = 1) {
  const instances: any[] = [];
  class WebSocketMock {
    static OPEN = 1;
    readyState = initialReadyState;
    onopen: (() => void) | null = null;
    onmessage: ((message: { data: string }) => void) | null = null;
    onerror: (() => void) | null = null;
    onclose: (() => void) | null = null;

    constructor(public url: string) {
      instances.push(this);
    }

    send = vi.fn();
    close = vi.fn();
  }
  vi.stubGlobal('WebSocket', WebSocketMock);
  return { instances, WebSocketMock };
}

export function installLanPeerConnectionMock(statsReport = new Map() as unknown as RTCStatsReport) {
  const configs: RTCConfiguration[] = [];
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
  return { configs, statsReport, RTCPeerConnectionMock };
}

export function installOfferPeerConnectionMock(offers: RTCSessionDescriptionInit[]) {
  const peers: any[] = [];
  class RTCPeerConnectionMock {
    localDescription: RTCSessionDescriptionInit | null = null;
    remoteDescription: RTCSessionDescriptionInit | null = null;
    addTrack = vi.fn();
    createOffer = vi.fn();
    setLocalDescription = vi.fn(async (description: RTCSessionDescriptionInit) => {
      this.localDescription = description;
    });
    setRemoteDescription = vi.fn(async (description: RTCSessionDescriptionInit) => {
      this.remoteDescription = description;
    });
    close = vi.fn();
    getStats = vi.fn(async () => new Map() as unknown as RTCStatsReport);

    constructor() {
      peers.push(this);
      for (const offer of offers) {
        this.createOffer.mockResolvedValueOnce(offer);
      }
    }
  }
  vi.stubGlobal('RTCPeerConnection', RTCPeerConnectionMock);
  return { peers, RTCPeerConnectionMock };
}

export function installTrackPeerConnectionMock(senderTrack: any, replaceTrack = vi.fn()) {
  class RTCPeerConnectionMock {
    connectionState: RTCPeerConnectionState = 'new';
    onicecandidate: ((event: RTCPeerConnectionIceEvent) => void) | null = null;
    ontrack: ((event: RTCTrackEvent) => void) | null = null;
    onconnectionstatechange: (() => void) | null = null;

    addTrack = vi.fn();
    createOffer = vi.fn(async () => ({ sdp: 'offer' }));
    setLocalDescription = vi.fn();
    getSenders = vi.fn(() => [{ track: senderTrack, replaceTrack }]);
    getStats = vi.fn(async () => new Map() as unknown as RTCStatsReport);
    close = vi.fn();
  }
  vi.stubGlobal('RTCPeerConnection', RTCPeerConnectionMock);
  return { replaceTrack, RTCPeerConnectionMock };
}

export function emitSignal(socket: any, event: Record<string, unknown>) {
  socket.onmessage?.({
    data: JSON.stringify({
      workspace_id: defaultSessionInput.workspaceId,
      device_session_id: defaultSessionInput.deviceSessionId,
      media_session_id: defaultSessionInput.mediaSessionId,
      ...event,
    }),
  });
}

export async function flushMicrotasks(count = 1) {
  for (let index = 0; index < count; index += 1) {
    await Promise.resolve();
  }
}

export function sentSignalMessages(socket: any) {
  return socket.send.mock.calls.map(([payload]: [unknown]) => JSON.parse(String(payload)));
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
