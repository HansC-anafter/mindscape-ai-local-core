import type {
  CameraFacingMode,
  WebRTCSessionState,
} from '@/lib/media-transport/webrtcSessionTypes';
import type { LinkState } from './useDeviceLinkCaptureSessionTypes';

export function buildDeviceId(): string {
  const storageKey = 'mindscape_device_binding_id';
  if (typeof window === 'undefined') {
    return 'device_browser';
  }
  const existing = window.localStorage.getItem(storageKey);
  if (existing) {
    return existing;
  }
  const next = `browser_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  window.localStorage.setItem(storageKey, next);
  return next;
}

export function stopStreamTracks(stream: MediaStream | null) {
  if (!stream) {
    return;
  }
  for (const track of stream.getTracks()) {
    track.stop();
  }
}

export function phoneFacingModeMessage(mode: CameraFacingMode): string {
  return mode === 'environment' ? 'Rear camera enabled.' : 'Front camera enabled.';
}

export function deviceLinkConnectionErrorMessage(reason: string): string {
  if (reason === 'live_media_request_failed_404') {
    return 'The camera connection service is unavailable on this link. Reload this page, then tap Reconnect.';
  }
  if (/^live_media_request_failed_5\d\d$/.test(reason)) {
    return 'The camera connection service did not respond. Wait a moment, then tap Reconnect.';
  }
  if (/^[a-z0-9_:-]+$/.test(reason)) {
    return 'Could not connect the camera. Check the network, then tap Reconnect.';
  }
  return reason;
}

export function isActiveLinkState(state: LinkState): boolean {
  return state === 'connecting' || state === 'paired' || state === 'streaming';
}

export function canReconnectMediaTransport(
  state: LinkState,
  mediaState: WebRTCSessionState | 'idle' | 'error',
  deviceSessionId: string | null,
): boolean {
  return Boolean(deviceSessionId)
    && (state === 'paired' || state === 'streaming')
    && (mediaState === 'closed' || mediaState === 'error');
}

export function connectionStatusLabel(state: LinkState, mediaState: WebRTCSessionState | 'idle' | 'error'): string {
  if (state === 'connecting') {
    return 'Connecting';
  }
  if (state === 'paired') {
    if (mediaState === 'closed' || mediaState === 'error') {
      return 'Media offline';
    }
    return mediaState === 'connected' ? 'Connected' : 'Paired';
  }
  if (state === 'streaming') {
    if (mediaState === 'closed' || mediaState === 'error') {
      return 'Media offline';
    }
    return mediaState === 'connected' ? 'Streaming' : 'Camera active';
  }
  if (state === 'secure_context_required') {
    return 'HTTPS required';
  }
  if (state === 'error') {
    return 'Connection error';
  }
  if (state === 'closed') {
    return 'Connection closed';
  }
  return 'Ready';
}

export function connectionStatusDetail(state: LinkState, mediaState: WebRTCSessionState | 'idle' | 'error'): string {
  if (state === 'connecting') {
    return 'Pairing with the workspace. Do not tap Connect again.';
  }
  if (state === 'paired') {
    if (mediaState === 'closed' || mediaState === 'error') {
      return 'Camera media disconnected. Reconnect source media without changing the pairing code.';
    }
    return mediaState === 'connected'
      ? 'Workspace receiver connected. Keep this page open.'
      : 'Device paired. Keep this page open while the workspace starts the receiver.';
  }
  if (state === 'streaming') {
    if (mediaState === 'closed' || mediaState === 'error') {
      return 'Camera media disconnected. Reconnect source media without changing the pairing code.';
    }
    return mediaState === 'connected'
      ? 'Live video is streaming to the workspace.'
      : 'Camera is active. Keep your full body in frame while the receiver connects.';
  }
  if (state === 'secure_context_required') {
    return 'Open this link from the LAN HTTPS origin before capture.';
  }
  if (state === 'error') {
    return 'Reconnect only after fixing camera permission, network, or pairing state.';
  }
  if (state === 'closed') {
    return 'The source session closed. Reconnect if you want to start a new session.';
  }
  return 'Aim the phone at your full body, then tap Connect once. Keep this page open.';
}

export function connectButtonLabel(state: LinkState, mediaState: WebRTCSessionState | 'idle' | 'error'): string {
  if (state === 'connecting') {
    return 'Connecting';
  }
  if (state === 'paired') {
    if (mediaState === 'closed' || mediaState === 'error') {
      return 'Reconnect';
    }
    return mediaState === 'connected' ? 'Connected' : 'Paired';
  }
  if (state === 'streaming') {
    if (mediaState === 'closed' || mediaState === 'error') {
      return 'Reconnect';
    }
    return 'Streaming';
  }
  if (state === 'closed' || state === 'error') {
    return 'Reconnect';
  }
  return 'Connect';
}
