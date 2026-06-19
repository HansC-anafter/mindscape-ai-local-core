export type MediaSignalParticipant = 'workspace' | 'source';

export type MediaSourceKind =
  | 'phone_camera'
  | 'desktop_camera'
  | 'usb_camera'
  | 'virtual_camera'
  | 'external_provider_camera';

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
export type CaptureOrientation = 'portrait' | 'landscape';

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
  replaceVideoTrack?: (
    video: MediaTrackConstraints,
    options?: { orientation?: CaptureOrientation },
  ) => Promise<MediaStream>;
  setVideoOrientation?: (orientation: CaptureOrientation) => Promise<MediaStream>;
};

export type PhoneBrowserSourceSessionInput = {
  apiBase: string;
  workspaceId: string;
  deviceSessionId: string;
  mediaSessionId: string;
  audio?: boolean;
  facingMode?: CameraFacingMode;
  videoOrientation?: CaptureOrientation;
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

function getStreamAudioTracks(stream: MediaStream): MediaStreamTrack[] {
  return typeof stream.getAudioTracks === 'function'
    ? stream.getAudioTracks().filter((track) => track.readyState !== 'ended')
    : stream.getTracks().filter((track) => track.kind === 'audio' && track.readyState !== 'ended');
}

function getStreamVideoTracks(stream: MediaStream): MediaStreamTrack[] {
  return typeof stream.getVideoTracks === 'function'
    ? stream.getVideoTracks().filter((track) => track.readyState !== 'ended')
    : stream.getTracks().filter((track) => track.kind === 'video' && track.readyState !== 'ended');
}

function getCanvasOutputSize(orientation: CaptureOrientation): { width: number; height: number } {
  return orientation === 'portrait'
    ? { width: 720, height: 1280 }
    : { width: 1280, height: 720 };
}

async function createPresentationStream({
  rawStream,
  orientation,
}: {
  rawStream: MediaStream;
  orientation?: CaptureOrientation;
}): Promise<{ stream: MediaStream; cleanup: () => void; transformed: boolean }> {
  const [rawVideoTrack] = getStreamVideoTracks(rawStream);
  const fallback = { stream: rawStream, cleanup: () => undefined, transformed: false };
  if (!rawVideoTrack || !orientation || typeof document === 'undefined') {
    return fallback;
  }
  const canvas = document.createElement('canvas');
  if (typeof canvas.captureStream !== 'function') {
    return fallback;
  }
  const video = document.createElement('video');
  const sourceVideoStream = new MediaStream([rawVideoTrack]);
  const { width, height } = getCanvasOutputSize(orientation);
  canvas.width = width;
  canvas.height = height;
  video.muted = true;
  video.playsInline = true;
  video.srcObject = sourceVideoStream;
  try {
    await video.play();
  } catch {
    video.srcObject = null;
    return fallback;
  }
  const context = canvas.getContext('2d');
  if (!context) {
    video.pause();
    video.srcObject = null;
    return fallback;
  }

  let frameId = 0;
  let active = true;
  const draw = () => {
    if (!active) {
      return;
    }
    const sourceWidth = video.videoWidth || width;
    const sourceHeight = video.videoHeight || height;
    const scale = Math.max(width / sourceWidth, height / sourceHeight);
    const drawWidth = sourceWidth * scale;
    const drawHeight = sourceHeight * scale;
    const drawX = (width - drawWidth) / 2;
    const drawY = (height - drawHeight) / 2;
    context.clearRect(0, 0, width, height);
    context.drawImage(video, drawX, drawY, drawWidth, drawHeight);
    frameId = window.requestAnimationFrame(draw);
  };
  draw();

  const transformedVideoStream = canvas.captureStream(30);
  const [transformedVideoTrack] = transformedVideoStream.getVideoTracks();
  if (!transformedVideoTrack) {
    active = false;
    window.cancelAnimationFrame(frameId);
    video.pause();
    video.srcObject = null;
    return fallback;
  }
  const stream = new MediaStream([...getStreamAudioTracks(rawStream), transformedVideoTrack]);
  const cleanup = () => {
    active = false;
    window.cancelAnimationFrame(frameId);
    transformedVideoTrack.stop();
    video.pause();
    video.srcObject = null;
  };
  return { stream, cleanup, transformed: true };
}

function resolveHttpBase(apiBase: string): string {
  return trimTrailingSlash(apiBase || getBrowserOrigin()) || getBrowserOrigin();
}

export function buildPhoneVideoConstraints(facingMode?: CameraFacingMode): MediaTrackConstraints {
  return {
    facingMode: { ideal: facingMode || 'environment' },
    width: { ideal: 1280 },
    height: { ideal: 720 },
    frameRate: { max: 30 },
  };
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
  let videoOrientation = input.videoOrientation;
  let rawStream = await navigator.mediaDevices.getUserMedia({
    video: input.video,
    audio: input.audio ?? true,
  });
  let presentation = await createPresentationStream({
    rawStream,
    orientation: videoOrientation,
  });
  let stream = presentation.stream;
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
    presentation.cleanup();
    for (const track of rawStream.getTracks()) {
      track.stop();
    }
    input.onState?.('closed');
  };

  const replacePeerVideoTrack = async (nextStream: MediaStream) => {
    const [nextVideoTrack] = nextStream.getVideoTracks();
    if (!nextVideoTrack) {
      throw new Error('replacement_video_track_missing');
    }
    if (peerConnection) {
      const videoSender = peerConnection.getSenders().find((sender) => sender.track?.kind === 'video');
      if (videoSender && typeof videoSender.replaceTrack === 'function') {
        await videoSender.replaceTrack(nextVideoTrack);
      } else {
        peerConnection.addTrack(nextVideoTrack, nextStream);
      }
    }
  };

  const setVideoOrientation = async (orientation: CaptureOrientation): Promise<MediaStream> => {
    if (stopped) {
      throw new Error('media_session_stopped');
    }
    videoOrientation = orientation;
    const nextPresentation = await createPresentationStream({
      rawStream,
      orientation,
    });
    await replacePeerVideoTrack(nextPresentation.stream);
    presentation.cleanup();
    presentation = nextPresentation;
    stream = nextPresentation.stream;
    input.onLocalStream?.(stream);
    return stream;
  };

  const replaceVideoTrack = async (
    video: MediaTrackConstraints,
    options?: { orientation?: CaptureOrientation },
  ): Promise<MediaStream> => {
    if (stopped) {
      throw new Error('media_session_stopped');
    }
    const oldRawVideoTracks = getStreamVideoTracks(rawStream);
    let releasedOldCamera = false;
    let nextVideoStream: MediaStream | null = null;
    try {
      try {
        nextVideoStream = await navigator.mediaDevices.getUserMedia({
          video,
          audio: false,
        });
      } catch {
        for (const track of oldRawVideoTracks) {
          track.stop();
        }
        releasedOldCamera = true;
        nextVideoStream = await navigator.mediaDevices.getUserMedia({
          video,
          audio: false,
        });
      }

      const [nextVideoTrack] = nextVideoStream.getVideoTracks();
      if (!nextVideoTrack) {
        throw new Error('replacement_video_track_missing');
      }

      const audioTracks = getStreamAudioTracks(rawStream);
      const nextRawStream = new MediaStream([...audioTracks, nextVideoTrack]);
      videoOrientation = options?.orientation || videoOrientation;
      const nextPresentation = await createPresentationStream({
        rawStream: nextRawStream,
        orientation: videoOrientation,
      });
      await replacePeerVideoTrack(nextPresentation.stream);

      if (!releasedOldCamera) {
        for (const track of oldRawVideoTracks) {
          track.stop();
        }
      }
      presentation.cleanup();
      rawStream = nextRawStream;
      presentation = nextPresentation;
      stream = nextPresentation.stream;
      input.onLocalStream?.(stream);
      return stream;
    } catch (error) {
      if (nextVideoStream) {
        for (const track of nextVideoStream.getTracks()) {
          track.stop();
        }
      }
      input.onError?.(error instanceof Error ? error : new Error('video_track_replace_failed'));
      throw error;
    }
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
      if (event.type === 'participant_joined' && event.sender === 'workspace') {
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
    get localStream() {
      return stream;
    },
    replaceVideoTrack,
    setVideoOrientation,
  };
}

export async function startPhoneBrowserSourceSession(
  input: PhoneBrowserSourceSessionInput,
): Promise<WebRTCSessionHandle> {
  return startBrowserMediaSourceSession({
    ...input,
    sourceKind: 'phone_camera',
    video: buildPhoneVideoConstraints(input.facingMode),
    videoOrientation: input.videoOrientation,
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
