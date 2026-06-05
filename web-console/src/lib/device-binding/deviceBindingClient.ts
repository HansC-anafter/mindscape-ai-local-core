export type DeviceSourceType =
  | 'phone_camera'
  | 'desktop_camera'
  | 'usb_camera'
  | 'virtual_camera'
  | 'microphone';

export type DeviceBindingSessionState =
  | 'pairing'
  | 'paired'
  | 'active'
  | 'revoked'
  | 'expired'
  | 'closed'
  | 'rejected';

export type DevicePairingCode = {
  workspace_id: string;
  pairing_code: string;
  expires_at_epoch: number;
  expires_in_seconds: number;
  device_link_path: string;
};

export type DeviceSessionEntry = {
  session_id: string;
  workspace_id: string;
  pairing_code: string;
  device_id: string;
  display_name?: string | null;
  source_types: DeviceSourceType[];
  state: DeviceBindingSessionState;
  created_at_epoch: number;
  updated_at_epoch: number;
  expires_at_epoch: number;
  terminal_reason?: string | null;
};

export type DeviceControlEvent = {
  type:
    | 'pairing_ready'
    | 'session_paired'
    | 'session_active'
    | 'session_revoked'
    | 'session_expired'
    | 'session_closed'
    | 'session_rejected'
    | 'heartbeat_ack'
    | 'session_error';
  workspace_id: string;
  pairing_code?: string;
  session_id?: string;
  device_id?: string;
  display_name?: string | null;
  source_types?: DeviceSourceType[];
  state?: DeviceBindingSessionState;
  expires_at_epoch?: number;
  active_sessions?: DeviceSessionEntry[];
  reason?: string;
  message?: string;
  recoverable?: boolean;
};

export type DeviceControlMessage =
  | { type: 'workspace_subscribe' }
  | {
      type: 'source_join';
      device_id?: string;
      display_name?: string;
      source_types?: DeviceSourceType[];
      metadata?: Record<string, unknown>;
    }
  | { type: 'heartbeat' }
  | { type: 'session_close' }
  | { type: 'ack' };

export type DeviceControlSocket = {
  send: (message: DeviceControlMessage) => void;
  close: () => void;
  raw: WebSocket;
};

export type OpenDeviceControlSocketInput = {
  apiBase: string;
  workspaceId: string;
  pairingCode: string;
  onOpen?: () => void;
  onEvent?: (event: DeviceControlEvent) => void;
  onError?: (error: Error) => void;
  onClose?: () => void;
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

export function buildDevicePairingCodeUrl({
  apiBase,
  workspaceId,
}: {
  apiBase: string;
  workspaceId: string;
}): string {
  return `${resolveHttpBase(apiBase)}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/device-bindings/pairing-codes`;
}

export function buildDeviceRevokeUrl({
  apiBase,
  workspaceId,
  sessionId,
}: {
  apiBase: string;
  workspaceId: string;
  sessionId: string;
}): string {
  return `${resolveHttpBase(apiBase)}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/device-bindings/${encodeURIComponent(sessionId)}/revoke`;
}

export function buildDeviceControlWebSocketUrl({
  apiBase,
  workspaceId,
  pairingCode,
}: {
  apiBase: string;
  workspaceId: string;
  pairingCode: string;
}): string {
  const base = resolveHttpBase(apiBase);
  const url = new URL(base, getBrowserOrigin());
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.pathname = `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/device-bindings/${encodeURIComponent(pairingCode)}/control`;
  url.search = '';
  return url.toString();
}

export async function createDevicePairingCode({
  apiBase,
  workspaceId,
}: {
  apiBase: string;
  workspaceId: string;
}): Promise<DevicePairingCode> {
  const response = await fetch(buildDevicePairingCodeUrl({ apiBase, workspaceId }), {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({}),
  });
  if (!response.ok) {
    throw new Error('device_pairing_code_create_failed');
  }
  return response.json() as Promise<DevicePairingCode>;
}

export async function revokeDeviceSession({
  apiBase,
  workspaceId,
  sessionId,
}: {
  apiBase: string;
  workspaceId: string;
  sessionId: string;
}): Promise<DeviceControlEvent> {
  const response = await fetch(buildDeviceRevokeUrl({ apiBase, workspaceId, sessionId }), {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error('device_session_revoke_failed');
  }
  return response.json() as Promise<DeviceControlEvent>;
}

export function openDeviceControlSocket(
  input: OpenDeviceControlSocketInput,
): DeviceControlSocket {
  const socket = new WebSocket(buildDeviceControlWebSocketUrl(input));
  socket.onopen = () => input.onOpen?.();
  socket.onmessage = (message) => {
    try {
      input.onEvent?.(JSON.parse(String(message.data)) as DeviceControlEvent);
    } catch (error) {
      input.onError?.(
        error instanceof Error ? error : new Error('invalid_device_control_event'),
      );
    }
  };
  socket.onerror = () => input.onError?.(new Error('device_control_socket_error'));
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
