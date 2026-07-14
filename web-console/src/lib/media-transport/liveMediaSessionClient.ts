import type { MediaSourceKind } from './webrtcSessionTypes';

export type LiveMediaSessionState =
  | 'waiting_for_publisher'
  | 'publishing'
  | 'ready'
  | 'degraded'
  | 'stopped'
  | 'expired';

export type LiveMediaSessionDescriptor = {
  workspace_id: string;
  device_session_id: string;
  media_session_id: string;
  stream_path: string;
  source_kind: MediaSourceKind;
  relay_profile: 'public';
  capabilities: Array<'video' | 'audio'>;
  analysis_reserved: boolean;
  state: LiveMediaSessionState;
  endpoints: {
    whip_publish_url: string;
    whep_preview_url: string;
    rtmps_publish_url: string;
    rtsps_receiver_url: string;
  };
  receiver_descriptor_ref: string;
  created_at_epoch: number;
  updated_at_epoch: number;
  expires_at_epoch: number;
  terminal_reason?: string | null;
};

export type LiveMediaSessionAccess = {
  session: LiveMediaSessionDescriptor;
  tokens: {
    publish: string;
    preview: string;
  };
};

type SessionIdentity = {
  apiBase: string;
  workspaceId: string;
  deviceSessionId: string;
};

function browserOrigin(): string {
  return typeof window === 'undefined' ? 'http://localhost:8300' : window.location.origin;
}

function httpBase(apiBase: string): string {
  const requested = apiBase.trim();
  if (requested) {
    return requested.replace(/\/+$/, '');
  }
  const origin = new URL(browserOrigin());
  if ((origin.hostname === 'localhost' || origin.hostname === '127.0.0.1') && origin.port === '8300') {
    origin.port = '8200';
  }
  return origin.toString().replace(/\/+$/, '');
}

function collectionUrl(input: SessionIdentity): string {
  return `${httpBase(input.apiBase)}/api/v1/workspaces/${encodeURIComponent(input.workspaceId)}/device-bindings/${encodeURIComponent(input.deviceSessionId)}/media-sessions`;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.ok) {
    return response.json() as Promise<T>;
  }
  let reason = `live_media_request_failed_${response.status}`;
  try {
    const payload = await response.json() as { detail?: string };
    reason = payload.detail || reason;
  } catch {
    // Keep the stable status-derived reason.
  }
  throw new Error(reason);
}

export async function createLiveMediaSession(
  input: SessionIdentity & {
    sourceKind: MediaSourceKind;
    capabilities: Array<'video' | 'audio'>;
    analysisReserved?: boolean;
  },
): Promise<LiveMediaSessionAccess> {
  const response = await fetch(collectionUrl(input), {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      source_kind: input.sourceKind,
      relay_profile: 'public',
      capabilities: input.capabilities,
      analysis_reserved: input.analysisReserved ?? true,
    }),
  });
  return parseResponse<LiveMediaSessionAccess>(response);
}

export async function getLiveMediaSession(
  input: SessionIdentity,
): Promise<LiveMediaSessionDescriptor> {
  const response = await fetch(collectionUrl(input), { cache: 'no-store' });
  return parseResponse<LiveMediaSessionDescriptor>(response);
}

export async function refreshLiveMediaSessionAccess(
  input: SessionIdentity & { mediaSessionId: string },
): Promise<LiveMediaSessionAccess> {
  const response = await fetch(
    `${collectionUrl(input)}/${encodeURIComponent(input.mediaSessionId)}/refresh`,
    { method: 'POST' },
  );
  return parseResponse<LiveMediaSessionAccess>(response);
}

export async function stopLiveMediaSession(
  input: SessionIdentity & { mediaSessionId: string; keepalive?: boolean },
): Promise<LiveMediaSessionDescriptor> {
  const response = await fetch(
    `${collectionUrl(input)}/${encodeURIComponent(input.mediaSessionId)}/stop`,
    { method: 'POST', keepalive: input.keepalive },
  );
  return parseResponse<LiveMediaSessionDescriptor>(response);
}
