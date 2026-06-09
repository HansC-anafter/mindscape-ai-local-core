export type MediaSignalParticipant = 'workspace' | 'source';

export type MediaSourceKind =
  | 'phone_camera'
  | 'desktop_camera'
  | 'usb_camera'
  | 'virtual_camera';

export type MediaSignalMessage =
  | { type: 'workspace_join' }
  | { type: 'source_join' }
  | { type: 'ready' }
  | { type: 'offer'; sdp: string }
  | { type: 'answer'; sdp: string }
  | { type: 'ice_candidate'; candidate: RTCIceCandidateInit }
  | { type: 'close'; reason?: string };

export type MediaSignalEvent = {
  type:
    | 'participant_joined'
    | 'participant_left'
    | 'ready'
    | 'offer'
    | 'answer'
    | 'ice_candidate'
    | 'close'
    | 'session_error';
  workspace_id: string;
  device_session_id: string;
  media_session_id: string;
  sender?: MediaSignalParticipant;
  sdp?: string;
  candidate?: RTCIceCandidateInit;
  reason?: string;
  message?: string;
  recoverable?: boolean;
  ice_servers?: RTCIceServer[];
  created_at_epoch: number;
};

export type MediaStreamRef = {
  workspace_id: string;
  device_session_id: string;
  media_session_id: string;
  source_kind: MediaSourceKind;
  stream_id: string;
  track_kinds: string[];
  started_at_epoch: number;
};

export type CameraFacingMode = 'user' | 'environment';

export type WebRTCSignalSocket = {
  raw: WebSocket;
  send: (message: MediaSignalMessage) => void;
  close: () => void;
};

export type OpenWebRTCSignalSocketInput = {
  apiBase: string;
  workspaceId: string;
  deviceSessionId: string;
  mediaSessionId: string;
  onOpen?: () => void;
  onEvent?: (event: MediaSignalEvent) => void | Promise<void>;
  onError?: (error: Error) => void;
  onClose?: () => void;
};

export type WebRTCSessionState =
  | 'local_stream_ready'
  | 'signal_open'
  | 'signal_joined'
  | 'offer_sent'
  | 'answer_sent'
  | 'answer_received'
  | 'connected'
  | 'closed';

export type WebRTCSessionHandle = {
  stop: () => void;
  peerConnection: RTCPeerConnection | null;
  localStream?: MediaStream;
};

export type PhoneBrowserSourceSessionInput = {
  apiBase: string;
  workspaceId: string;
  deviceSessionId: string;
  mediaSessionId: string;
  audio?: boolean;
  facingMode?: CameraFacingMode;
  onLocalStream?: (stream: MediaStream) => void;
  onState?: (state: WebRTCSessionState) => void;
  onError?: (error: Error) => void;
};

export type BrowserMediaSourceSessionInput = PhoneBrowserSourceSessionInput & {
  sourceKind: MediaSourceKind;
  video: MediaTrackConstraints;
};

export type DesktopBrowserSourceSessionInput = {
  apiBase: string;
  workspaceId: string;
  deviceSessionId: string;
  mediaSessionId: string;
  sourceKind: Extract<MediaSourceKind, 'desktop_camera' | 'usb_camera' | 'virtual_camera'>;
  deviceId?: string;
  onLocalStream?: (stream: MediaStream) => void;
  onState?: (state: WebRTCSessionState) => void;
  onError?: (error: Error) => void;
};

export type WorkspaceReceiverSessionInput = {
  apiBase: string;
  workspaceId: string;
  deviceSessionId: string;
  mediaSessionId: string;
  onRemoteStream?: (stream: MediaStream) => void;
  onState?: (state: WebRTCSessionState) => void;
  onError?: (error: Error) => void;
};

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

function getBrowserOrigin(): string {
  if (typeof window === 'undefined') {
    return 'http://localhost:8300';
  }
  return window.location.origin;
}

function resolveHttpBase(apiBase: string): string {
  return trimTrailingSlash(apiBase || getBrowserOrigin()) || getBrowserOrigin();
}

export function buildWebRTCSignalWebSocketUrl({
  apiBase,
  workspaceId,
  deviceSessionId,
  mediaSessionId,
}: {
  apiBase: string;
  workspaceId: string;
  deviceSessionId: string;
  mediaSessionId: string;
}): string {
  const base = resolveHttpBase(apiBase);
  const url = new URL(base, getBrowserOrigin());
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.pathname = `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/device-bindings/${encodeURIComponent(deviceSessionId)}/media-sessions/${encodeURIComponent(mediaSessionId)}/signal`;
  url.search = '';
  return url.toString();
}

export function openWebRTCSignalSocket(
  input: OpenWebRTCSignalSocketInput,
): WebRTCSignalSocket {
  const socket = new WebSocket(buildWebRTCSignalWebSocketUrl(input));
  socket.onopen = () => input.onOpen?.();
  socket.onmessage = (message) => {
    try {
      void input.onEvent?.(JSON.parse(String(message.data)) as MediaSignalEvent);
    } catch (error) {
      input.onError?.(error instanceof Error ? error : new Error('invalid_media_signal_event'));
    }
  };
  socket.onerror = () => input.onError?.(new Error('media_signal_socket_error'));
  socket.onclose = () => input.onClose?.();
  return {
    raw: socket,
    send: (message) => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(message));
      }
    },
    close: () => socket.close(),
  };
}

export function createLanPeerConnection({
  onIceCandidate,
  onRemoteStream,
  onConnectionStateChange,
  onStats,
}: {
  onIceCandidate?: (candidate: RTCIceCandidateInit) => void;
  onRemoteStream?: (stream: MediaStream) => void;
  onConnectionStateChange?: (state: RTCPeerConnectionState) => void;
  onStats?: (state: RTCPeerConnectionState, report: RTCStatsReport) => void;
} = {}): RTCPeerConnection {
  const peerConnection = new RTCPeerConnection({ iceServers: [] });
  peerConnection.onicecandidate = (event) => {
    if (event.candidate) {
      onIceCandidate?.(event.candidate.toJSON());
    }
  };
  peerConnection.ontrack = (event) => {
    const [stream] = event.streams;
    if (stream) {
      onRemoteStream?.(stream);
    }
  };
  peerConnection.onconnectionstatechange = () => {
    const state = peerConnection.connectionState;
    onConnectionStateChange?.(state);
    if (state === 'connected' || state === 'failed' || state === 'disconnected' || state === 'closed') {
      void peerConnection.getStats()
        .then((report) => onStats?.(state, report))
        .catch(() => undefined);
    }
  };
  return peerConnection;
}

export async function startBrowserMediaSourceSession(
  input: BrowserMediaSourceSessionInput,
): Promise<WebRTCSessionHandle> {
  const stream = await navigator.mediaDevices.getUserMedia({
    video: input.video,
    audio: input.audio ?? true,
  });
  input.onLocalStream?.(stream);
  input.onState?.('local_stream_ready');

  let stopped = false;
  let joined = false;
  let peerConnection: RTCPeerConnection | null = null;
  let signalSocket: WebRTCSignalSocket;

  const ensurePeerConnection = () => {
    if (peerConnection) {
      return peerConnection;
    }
    peerConnection = createLanPeerConnection({
      onIceCandidate: (candidate) => signalSocket.send({ type: 'ice_candidate', candidate }),
      onConnectionStateChange: (state) => {
        if (state === 'connected') {
          input.onState?.('connected');
        }
      },
    });
    for (const track of stream.getTracks()) {
      peerConnection.addTrack(track, stream);
    }
    return peerConnection;
  };

  const sendOffer = async () => {
    if (!joined || stopped) {
      return;
    }
    const peer = ensurePeerConnection();
    const offer = await peer.createOffer();
    await peer.setLocalDescription(offer);
    signalSocket.send({ type: 'offer', sdp: offer.sdp || '' });
    input.onState?.('offer_sent');
  };

  const stop = () => {
    if (stopped) {
      return;
    }
    stopped = true;
    try {
      signalSocket.send({ type: 'close', reason: 'source_stopped' });
    } catch {
      // Ignore shutdown races.
    }
    signalSocket.close();
    peerConnection?.close();
    for (const track of stream.getTracks()) {
      track.stop();
    }
    input.onState?.('closed');
  };

  signalSocket = openWebRTCSignalSocket({
    apiBase: input.apiBase,
    workspaceId: input.workspaceId,
    deviceSessionId: input.deviceSessionId,
    mediaSessionId: input.mediaSessionId,
    onOpen: () => {
      input.onState?.('signal_open');
      signalSocket.send({ type: 'source_join' });
    },
    onEvent: async (event) => {
      if (event.type === 'participant_joined' && event.sender === 'source') {
        joined = true;
        input.onState?.('signal_joined');
        await sendOffer();
        return;
      }
      if (event.type === 'answer' && event.sdp) {
        const peer = ensurePeerConnection();
        await peer.setRemoteDescription({ type: 'answer', sdp: event.sdp });
        input.onState?.('answer_received');
        return;
      }
      if (event.type === 'ice_candidate' && event.candidate) {
        await ensurePeerConnection().addIceCandidate(event.candidate);
        return;
      }
      if (event.type === 'close' || event.type === 'session_error') {
        stop();
      }
    },
    onError: input.onError,
    onClose: () => input.onState?.('closed'),
  });

  return {
    stop,
    get peerConnection() {
      return peerConnection;
    },
    localStream: stream,
  };
}

export async function startPhoneBrowserSourceSession(
  input: PhoneBrowserSourceSessionInput,
): Promise<WebRTCSessionHandle> {
  return startBrowserMediaSourceSession({
    ...input,
    sourceKind: 'phone_camera',
    video: {
      facingMode: { ideal: input.facingMode || 'environment' },
      width: { ideal: 1280 },
      height: { ideal: 720 },
      frameRate: { max: 30 },
    },
  });
}

export async function startDesktopBrowserSourceSession(
  input: DesktopBrowserSourceSessionInput,
): Promise<WebRTCSessionHandle> {
  return startBrowserMediaSourceSession({
    apiBase: input.apiBase,
    workspaceId: input.workspaceId,
    deviceSessionId: input.deviceSessionId,
    mediaSessionId: input.mediaSessionId,
    sourceKind: input.sourceKind,
    audio: false,
    video: {
      ...(input.deviceId ? { deviceId: { exact: input.deviceId } } : {}),
      width: { ideal: 1280 },
      height: { ideal: 720 },
      frameRate: { max: 30 },
    },
    onLocalStream: input.onLocalStream,
    onState: input.onState,
    onError: input.onError,
  });
}

export function startWorkspaceReceiverSession(
  input: WorkspaceReceiverSessionInput,
): WebRTCSessionHandle {
  let stopped = false;
  let peerConnection: RTCPeerConnection | null = null;
  let remoteDescriptionReady = false;
  const pendingCandidates: RTCIceCandidateInit[] = [];
  let signalSocket: WebRTCSignalSocket;

  const ensurePeerConnection = () => {
    if (peerConnection) {
      return peerConnection;
    }
    peerConnection = createLanPeerConnection({
      onIceCandidate: (candidate) => signalSocket.send({ type: 'ice_candidate', candidate }),
      onRemoteStream: input.onRemoteStream,
      onConnectionStateChange: (state) => {
        if (state === 'connected') {
          input.onState?.('connected');
        }
      },
    });
    return peerConnection;
  };

  const flushCandidates = async () => {
    const peer = ensurePeerConnection();
    while (pendingCandidates.length) {
      const candidate = pendingCandidates.shift();
      if (candidate) {
        await peer.addIceCandidate(candidate);
      }
    }
  };

  const stop = () => {
    if (stopped) {
      return;
    }
    stopped = true;
    try {
      signalSocket.send({ type: 'close', reason: 'workspace_stopped' });
    } catch {
      // Ignore shutdown races.
    }
    signalSocket.close();
    peerConnection?.close();
    input.onState?.('closed');
  };

  signalSocket = openWebRTCSignalSocket({
    apiBase: input.apiBase,
    workspaceId: input.workspaceId,
    deviceSessionId: input.deviceSessionId,
    mediaSessionId: input.mediaSessionId,
    onOpen: () => {
      input.onState?.('signal_open');
      signalSocket.send({ type: 'workspace_join' });
    },
    onEvent: async (event) => {
      if (event.type === 'participant_joined' && event.sender === 'workspace') {
        input.onState?.('signal_joined');
        return;
      }
      if (event.type === 'offer' && event.sdp) {
        const peer = ensurePeerConnection();
        await peer.setRemoteDescription({ type: 'offer', sdp: event.sdp });
        remoteDescriptionReady = true;
        await flushCandidates();
        const answer = await peer.createAnswer();
        await peer.setLocalDescription(answer);
        signalSocket.send({ type: 'answer', sdp: answer.sdp || '' });
        input.onState?.('answer_sent');
        return;
      }
      if (event.type === 'ice_candidate' && event.candidate) {
        if (!remoteDescriptionReady) {
          pendingCandidates.push(event.candidate);
          return;
        }
        await ensurePeerConnection().addIceCandidate(event.candidate);
        return;
      }
      if (event.type === 'close' || event.type === 'session_error') {
        stop();
      }
    },
    onError: input.onError,
    onClose: () => input.onState?.('closed'),
  });

  return {
    stop,
    get peerConnection() {
      return peerConnection;
    },
  };
}
