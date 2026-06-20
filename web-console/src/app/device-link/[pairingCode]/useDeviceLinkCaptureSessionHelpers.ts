import type { WebRTCSessionState } from '@/lib/media-transport/webrtcSessionClient';
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

export function isActiveLinkState(state: LinkState): boolean {
  return state === 'connecting' || state === 'paired' || state === 'streaming';
}

export function connectionStatusLabel(state: LinkState, mediaState: WebRTCSessionState | 'idle' | 'error'): string {
  if (state === 'connecting') {
    return 'Connecting';
  }
  if (state === 'paired') {
    return mediaState === 'connected' ? 'Connected' : 'Paired';
  }
  if (state === 'streaming') {
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
    return mediaState === 'connected'
      ? 'Workspace receiver connected. Keep this page open.'
      : 'Device paired. Keep this page open while the workspace starts the receiver.';
  }
  if (state === 'streaming') {
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
  return 'Tap Connect once, then keep this page open.';
}

export function connectButtonLabel(state: LinkState, mediaState: WebRTCSessionState | 'idle' | 'error'): string {
  if (state === 'connecting') {
    return 'Connecting';
  }
  if (state === 'paired') {
    return mediaState === 'connected' ? 'Connected' : 'Paired';
  }
  if (state === 'streaming') {
    return 'Streaming';
  }
  if (state === 'closed' || state === 'error') {
    return 'Reconnect';
  }
  return 'Connect';
}
