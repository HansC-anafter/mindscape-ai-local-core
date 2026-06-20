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
