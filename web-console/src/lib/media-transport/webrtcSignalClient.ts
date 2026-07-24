import type {
  MediaSignalEvent,
  OpenWebRTCSignalSocketInput,
  WebRTCSignalSocket,
} from './webrtcSessionTypes';

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

function getBrowserOrigin(): string {
  if (typeof window === 'undefined') {
    return 'http://localhost:8300';
  }
  return window.location.origin;
}

function resolveLocalBackendBase(origin: string): string | null {
  try {
    const url = new URL(origin);
    if (
      (url.hostname === 'localhost' || url.hostname === '127.0.0.1')
      && url.port === '8300'
    ) {
      url.port = '8200';
      return trimTrailingSlash(url.toString());
    }
  } catch {
    return null;
  }
  return null;
}

function resolveHttpBase(apiBase: string): string {
  const trimmedApiBase = apiBase.trim();
  if (trimmedApiBase) {
    return trimTrailingSlash(trimmedApiBase);
  }
  const browserOrigin = getBrowserOrigin();
  return resolveLocalBackendBase(browserOrigin) || trimTrailingSlash(browserOrigin) || browserOrigin;
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
  socket.onclose = (event) => input.onClose?.({
    code: event.code,
    reason: event.reason,
    wasClean: event.wasClean,
  });
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
