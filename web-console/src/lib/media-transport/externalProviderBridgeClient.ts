import {
  openDeviceControlSocket,
  type DeviceControlEvent,
  type DeviceControlSocket,
} from '@/lib/device-binding/deviceBindingClient';
import {
  createLanPeerConnection,
  openWebRTCSignalSocket,
  type WebRTCSignalSocket,
  type WebRTCSessionState,
} from './webrtcSessionClient';

export type ExternalProviderBridgeSessionState =
  | 'control_open'
  | 'source_paired'
  | WebRTCSessionState
  | 'error';

export interface ExternalProviderBridgeSessionInput {
  apiBase: string;
  workspaceId: string;
  pairingCode: string;
  stream: MediaStream;
  deviceId?: string;
  displayName?: string;
  providerFamily?: string;
  providerBackend?: string;
  metadata?: Record<string, unknown>;
  heartbeatIntervalMs?: number;
  stopTracksOnStop?: boolean;
  onState?: (state: ExternalProviderBridgeSessionState) => void;
  onEvent?: (event: DeviceControlEvent) => void;
  onError?: (error: Error) => void;
}

export interface ExternalProviderBridgeSessionHandle {
  stop: () => void;
  controlSocket: DeviceControlSocket;
  localStream: MediaStream;
  readonly deviceSessionId: string | null;
  readonly mediaSessionId: string | null;
  readonly peerConnection: RTCPeerConnection | null;
}

function liveVideoTracks(stream: MediaStream): MediaStreamTrack[] {
  if (typeof stream.getVideoTracks === 'function') {
    return stream.getVideoTracks().filter((track) => track.readyState !== 'ended');
  }
  return stream.getTracks().filter((track) => track.kind === 'video' && track.readyState !== 'ended');
}

export function startExternalProviderBridgeSession(
  input: ExternalProviderBridgeSessionInput,
): ExternalProviderBridgeSessionHandle {
  if (liveVideoTracks(input.stream).length === 0) {
    throw new Error('external_provider_camera_stream_required');
  }

  let stopped = false;
  let deviceSessionId: string | null = null;
  let mediaSessionId: string | null = null;
  let mediaJoined = false;
  let peerConnection: RTCPeerConnection | null = null;
  let signalSocket: WebRTCSignalSocket | null = null;
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null;

  const stopHeartbeat = () => {
    if (heartbeatTimer !== null) {
      clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
  };

  const startHeartbeat = () => {
    const intervalMs = input.heartbeatIntervalMs ?? 25_000;
    if (intervalMs <= 0 || heartbeatTimer !== null) {
      return;
    }
    heartbeatTimer = setInterval(() => {
      controlSocket.send({ type: 'heartbeat' });
    }, intervalMs);
  };

  const ensurePeerConnection = () => {
    if (peerConnection) {
      return peerConnection;
    }
    if (!signalSocket) {
      throw new Error('external_provider_signal_socket_missing');
    }
    peerConnection = createLanPeerConnection({
      onIceCandidate: (candidate) => signalSocket?.send({ type: 'ice_candidate', candidate }),
      onConnectionStateChange: (state) => {
        if (state === 'connected') {
          input.onState?.('connected');
        }
      },
    });
    for (const track of input.stream.getTracks()) {
      peerConnection.addTrack(track, input.stream);
    }
    return peerConnection;
  };

  const sendOffer = async () => {
    if (!mediaJoined || stopped) {
      return;
    }
    const peer = ensurePeerConnection();
    const offer = await peer.createOffer();
    await peer.setLocalDescription(offer);
    signalSocket?.send({ type: 'offer', sdp: offer.sdp || '' });
    input.onState?.('offer_sent');
  };

  const resendOfferIfNeeded = async () => {
    const hasUnansweredOffer = peerConnection?.localDescription?.type === 'offer'
      && !peerConnection.remoteDescription;
    if (hasUnansweredOffer) {
      return;
    }
    await sendOffer();
  };

  const startMediaSession = (sessionId: string) => {
    if (signalSocket || stopped) {
      return;
    }
    deviceSessionId = sessionId;
    mediaSessionId = sessionId;
    signalSocket = openWebRTCSignalSocket({
      apiBase: input.apiBase,
      workspaceId: input.workspaceId,
      deviceSessionId: sessionId,
      mediaSessionId: sessionId,
      onOpen: () => {
        input.onState?.('signal_open');
        signalSocket?.send({ type: 'source_join' });
      },
      onEvent: async (event) => {
        if (event.type === 'participant_joined' && event.sender === 'source') {
          mediaJoined = true;
          input.onState?.('signal_joined');
          await sendOffer();
          return;
        }
        if (event.type === 'participant_joined' && event.sender === 'workspace') {
          await resendOfferIfNeeded();
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
          handle.stop();
        }
      },
      onError: (error) => {
        input.onState?.('error');
        input.onError?.(error);
      },
      onClose: () => input.onState?.('closed'),
    });
  };

  const handle: ExternalProviderBridgeSessionHandle = {
    stop: () => {
      if (stopped) {
        return;
      }
      stopped = true;
      stopHeartbeat();
      try {
        signalSocket?.send({ type: 'close', reason: 'external_provider_bridge_stopped' });
      } catch {
        // Ignore shutdown races.
      }
      try {
        controlSocket.send({ type: 'session_close' });
      } catch {
        // Ignore shutdown races.
      }
      signalSocket?.close();
      controlSocket.close();
      peerConnection?.close();
      if (input.stopTracksOnStop) {
        for (const track of input.stream.getTracks()) {
          track.stop();
        }
      }
      input.onState?.('closed');
    },
    controlSocket: null as unknown as DeviceControlSocket,
    localStream: input.stream,
    get deviceSessionId() {
      return deviceSessionId;
    },
    get mediaSessionId() {
      return mediaSessionId;
    },
    get peerConnection() {
      return peerConnection;
    },
  };

  const controlSocket = openDeviceControlSocket({
    apiBase: input.apiBase,
    workspaceId: input.workspaceId,
    pairingCode: input.pairingCode,
    onOpen: () => {
      input.onState?.('control_open');
      controlSocket.send({
        type: 'source_join',
        device_id: input.deviceId,
        display_name: input.displayName || 'External provider bridge',
        source_types: ['external_provider_camera'],
        metadata: {
          capture_surface: 'external_provider_bridge',
          provider_family: input.providerFamily,
          provider_backend: input.providerBackend,
          ...input.metadata,
        },
      });
    },
    onEvent: (event) => {
      input.onEvent?.(event);
      if ((event.type === 'session_paired' || event.type === 'heartbeat_ack') && event.session_id) {
        input.onState?.('source_paired');
        startHeartbeat();
        startMediaSession(event.session_id);
      }
      if (event.type === 'session_error' || event.type === 'session_rejected') {
        input.onState?.('error');
        input.onError?.(new Error(event.reason || event.message || 'external_provider_bridge_rejected'));
      }
      if (event.type === 'session_closed' || event.type === 'session_expired' || event.type === 'session_revoked') {
        handle.stop();
      }
    },
    onError: (error) => {
      input.onState?.('error');
      input.onError?.(error);
    },
    onClose: () => input.onState?.('closed'),
  });
  handle.controlSocket = controlSocket;
  return handle;
}
