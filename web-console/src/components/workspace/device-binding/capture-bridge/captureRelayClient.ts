export type CaptureRelayAction = 'status' | 'start' | 'stop' | 'open_obs';

export interface CaptureRelayRequest {
  action: CaptureRelayAction;
  stream_name: string;
  open_obs?: boolean;
  timeout_ms?: number;
}

export interface CaptureRelayResponse {
  schema_version?: string;
  action?: string;
  status?: string;
  reason?: string;
  start_result?: string;
  stop_result?: string;
  relay?: {
    mode?: string;
    managed?: boolean;
    running?: boolean;
    binary_path?: string | null;
    rtmp_listener_open?: boolean;
    rtmp_port?: number;
    rtsp_port?: number;
  };
  obs?: {
    app_present?: boolean;
    websocket_reachable?: boolean;
    websocket_host?: string;
    websocket_port?: number;
  };
  obs_open?: {
    opened?: boolean;
    reason?: string;
  };
  urls?: {
    stream_name?: string;
    publish_url?: string;
    read_url?: string;
  };
  next_steps?: string[];
}

export async function callCaptureRelayControl({
  apiBase,
  request,
}: {
  apiBase: string;
  request: CaptureRelayRequest;
}): Promise<CaptureRelayResponse> {
  const response = await fetch(
    `${apiBase.replace(/\/+$/, '')}/api/v1/host/services/capture-relay`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    },
  );
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body?.detail;
    const reason = detail?.reason || body?.reason || `capture_relay_http_${response.status}`;
    throw new Error(reason);
  }
  return body as CaptureRelayResponse;
}
