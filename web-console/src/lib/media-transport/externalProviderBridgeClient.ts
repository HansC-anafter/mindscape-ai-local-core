import {
  openDeviceControlSocket,
  type DeviceControlEvent,
  type DeviceControlSocket,
} from '@/lib/device-binding/deviceBindingClient';
import {
  createLiveMediaSession,
  stopLiveMediaSession,
  type LiveMediaSessionAccess,
} from './liveMediaSessionClient';
import { startWhipPublisher, type WhipPublisherHandle } from './whipPublisherClient';
import type { WebRTCSessionState } from './webrtcSessionTypes';

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
  return stream.getTracks().filter((track) => (
    track.kind === 'video' && track.readyState !== 'ended'
  ));
}

export function startExternalProviderBridgeSession(
  input: ExternalProviderBridgeSessionInput,
): ExternalProviderBridgeSessionHandle {
  if (liveVideoTracks(input.stream).length === 0) {
    throw new Error('external_provider_camera_stream_required');
  }

  let stopped = false;
  let deviceSessionId: string | null = null;
  let mediaAccess: LiveMediaSessionAccess | null = null;
  let publisher: WhipPublisherHandle | null = null;
  let mediaStartPromise: Promise<void> | null = null;
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

  const startMediaSession = (sessionId: string) => {
    if (stopped || publisher || mediaStartPromise) {
      return;
    }
    deviceSessionId = sessionId;
    mediaStartPromise = (async () => {
      try {
        const audioTracks = typeof input.stream.getAudioTracks === 'function'
          ? input.stream.getAudioTracks()
          : input.stream.getTracks().filter((track) => track.kind === 'audio');
        const capabilities: Array<'video' | 'audio'> = audioTracks.length
          ? ['video', 'audio']
          : ['video'];
        const access = await createLiveMediaSession({
          apiBase: input.apiBase,
          workspaceId: input.workspaceId,
          deviceSessionId: sessionId,
          sourceKind: 'external_provider_camera',
          capabilities,
          analysisReserved: true,
        });
        mediaAccess = access;
        if (stopped) {
          await stopLiveMediaSession({
            apiBase: input.apiBase,
            workspaceId: access.session.workspace_id,
            deviceSessionId: access.session.device_session_id,
            mediaSessionId: access.session.media_session_id,
            keepalive: true,
          }).catch(() => undefined);
          return;
        }
        publisher = await startWhipPublisher({
          endpoint: access.session.endpoints.whip_publish_url,
          token: access.tokens.publish,
          stream: input.stream,
          onState: input.onState,
          onError: input.onError,
        });
      } catch (error) {
        const normalized = error instanceof Error
          ? error
          : new Error('external_provider_media_start_failed');
        input.onState?.('error');
        input.onError?.(normalized);
      } finally {
        mediaStartPromise = null;
      }
    })();
  };

  const handle: ExternalProviderBridgeSessionHandle = {
    stop: () => {
      if (stopped) {
        return;
      }
      stopped = true;
      stopHeartbeat();
      publisher?.stop();
      if (mediaAccess) {
        void stopLiveMediaSession({
          apiBase: input.apiBase,
          workspaceId: mediaAccess.session.workspace_id,
          deviceSessionId: mediaAccess.session.device_session_id,
          mediaSessionId: mediaAccess.session.media_session_id,
          keepalive: true,
        }).catch(() => undefined);
      }
      try {
        controlSocket.send({ type: 'session_close' });
      } catch {
        // Ignore shutdown races.
      }
      controlSocket.close();
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
      return mediaAccess?.session.media_session_id || null;
    },
    get peerConnection() {
      return publisher?.peerConnection || null;
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
        input.onError?.(new Error(
          event.reason || event.message || 'external_provider_bridge_rejected',
        ));
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
