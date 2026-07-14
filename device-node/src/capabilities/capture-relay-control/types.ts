import type { ChildProcess } from "child_process";

export type CaptureRelayAction =
    | "status"
    | "install_mediamtx"
    | "start"
    | "stop"
    | "open_obs"
    | "configure_obs"
    | "receiver_start"
    | "receiver_status"
    | "receiver_stop";

export interface CaptureRelayArgs {
    action?: string;
    stream_name?: string;
    scene_name?: string;
    source_name?: string;
    rtmp_port?: number;
    rtsp_port?: number;
    obs_websocket_host?: string;
    obs_websocket_port?: number;
    open_obs?: boolean;
    start_virtual_camera?: boolean;
    install_method?: string;
    timeout_ms?: number;
    receiver_descriptor?: unknown;
    media_session_id?: string;
    receiver_identity?: string;
}

export interface ManagedRelayProcess {
    child: ChildProcess;
    binaryPath: string;
    streamName: string;
    startedAt: string;
    rtmpPort: number;
    rtspPort: number;
    outputLines: string[];
}

export interface RelayUrls {
    stream_name: string;
    publish_url: string;
    read_url: string;
}

export interface RelayPublisherState {
    stream_name: string;
    has_publisher: boolean;
    state: "relay_not_running" | "publishing" | "waiting_for_publisher";
    reason?: string;
    detail: string;
}

export interface RelayBinaryLookupInput {
    env?: NodeJS.ProcessEnv;
    pathValue?: string;
    commonPaths?: string[];
}

export interface ObsAppLookupInput {
    env?: NodeJS.ProcessEnv;
    commonPaths?: string[];
}

export interface ObsWebSocketMessage {
    op?: number;
    d?: Record<string, unknown>;
}

export interface ObsRpcClient {
    request(requestType: string, requestData?: Record<string, unknown>): Promise<Record<string, unknown>>;
    close(): void;
}

export interface ObsOpenResult {
    opened: boolean;
    reason?: string;
    app_path?: string;
    expected_app_paths?: string[];
}

export interface HostCommandResult {
    exitCode: number | null;
    stdout: string;
    stderr: string;
    timedOut: boolean;
}
