export type CaptureRelayAction = 'status' | 'install_mediamtx' | 'start' | 'stop' | 'open_obs' | 'configure_obs';

export interface CaptureRelayRequest {
  action: CaptureRelayAction;
  stream_name: string;
  scene_name?: string;
  source_name?: string;
  install_method?: 'homebrew';
  open_obs?: boolean;
  start_virtual_camera?: boolean;
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
    recent_output?: string[];
  };
  stream?: {
    stream_name?: string;
    has_publisher?: boolean;
    state?: 'relay_not_running' | 'publishing' | 'waiting_for_publisher';
    reason?: string;
    detail?: string;
  };
  obs?: {
    app_path?: string;
    app_present?: boolean;
    expected_app_paths?: string[];
    websocket_reachable?: boolean;
    websocket_host?: string;
    websocket_port?: number;
  };
  obs_open?: {
    opened?: boolean;
    reason?: string;
    app_path?: string;
    expected_app_paths?: string[];
  };
  install_result?: string;
  install_method?: string;
  install_command?: string;
  install_exit_code?: number | null;
  install_timed_out?: boolean;
  install_stdout?: string;
  install_stderr?: string;
  configure_result?: string;
  obs_setup?: {
    scene_name?: string;
    source_name?: string;
    read_url?: string;
    steps?: string[];
    virtual_camera?: {
      active?: boolean;
      started?: boolean;
      reason?: string;
    } | null;
  };
  install_guidance?: {
    dependency?: string;
    status?: string;
    binary_path?: string | null;
    official_release_url?: string;
    detected_platform?: string;
    detected_arch?: string;
    recommended_asset_pattern?: string;
    host_tools?: {
      brew_available?: boolean;
      brew_path?: string | null;
    };
    options?: Array<{
      id?: string;
      label?: string;
      available?: boolean;
      command?: string;
      release_url?: string;
      asset_pattern?: string;
      install_target?: string;
      after_install?: string;
    }>;
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
