import { spawn, type ChildProcess } from "child_process";
import * as fs from "fs";
import * as net from "net";
import * as os from "os";
import * as path from "path";

type CaptureRelayAction = "status" | "start" | "stop" | "open_obs";

interface CaptureRelayArgs {
    action?: string;
    stream_name?: string;
    rtmp_port?: number;
    rtsp_port?: number;
    obs_websocket_host?: string;
    obs_websocket_port?: number;
    open_obs?: boolean;
    timeout_ms?: number;
}

interface ManagedRelayProcess {
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

interface RelayBinaryLookupInput {
    env?: NodeJS.ProcessEnv;
    pathValue?: string;
    commonPaths?: string[];
}

const DEFAULT_RTMP_PORT = 1935;
const DEFAULT_RTSP_PORT = 8554;
const DEFAULT_OBS_WEBSOCKET_PORT = 4455;
const DEFAULT_STREAM_NAME = "external-camera";
const OBS_APP_PATH = "/Applications/OBS.app";
const MEDIAMTX_RELEASES_URL = "https://github.com/bluenviron/mediamtx/releases/latest";
const COMMON_MEDIAMTX_PATHS = [
    "/opt/homebrew/bin/mediamtx",
    "/usr/local/bin/mediamtx",
    "/usr/bin/mediamtx",
];
const COMMON_BREW_PATHS = [
    "/opt/homebrew/bin/brew",
    "/usr/local/bin/brew",
];

let managedRelay: ManagedRelayProcess | null = null;

function isExecutable(filePath: string): boolean {
    try {
        fs.accessSync(filePath, fs.constants.X_OK);
        return true;
    } catch {
        return false;
    }
}

export function resolveRelayBinary(input: RelayBinaryLookupInput = {}): string | null {
    const env = input.env || process.env;
    const configuredPath = String(env.CAPTURE_RELAY_MEDIAMTX_BIN || "").trim();
    if (configuredPath && isExecutable(configuredPath)) {
        return configuredPath;
    }

    const pathValue = input.pathValue ?? env.PATH ?? "";
    const candidates = [
        ...pathValue
            .split(path.delimiter)
            .filter(Boolean)
            .map((directory) => path.join(directory, "mediamtx")),
        ...(input.commonPaths ?? COMMON_MEDIAMTX_PATHS),
    ];
    for (const candidate of candidates) {
        if (isExecutable(candidate)) {
            return candidate;
        }
    }
    return null;
}

function resolveHostCommand(commandName: string, commonPaths: string[]): string | null {
    const candidates = [
        ...(process.env.PATH || "")
            .split(path.delimiter)
            .filter(Boolean)
            .map((directory) => path.join(directory, commandName)),
        ...commonPaths,
    ];
    for (const candidate of candidates) {
        if (isExecutable(candidate)) {
            return candidate;
        }
    }
    return null;
}

function mediamtxAssetPattern(): string {
    const platform = process.platform === "darwin" ? "darwin" : process.platform;
    const arch = process.arch === "x64" ? "amd64" : process.arch;
    return `mediamtx_*_${platform}_${arch}.tar.gz`;
}

function buildInstallGuidance(binaryPath: string | null): Record<string, unknown> {
    const brewPath = resolveHostCommand("brew", COMMON_BREW_PATHS);
    return {
        dependency: "mediamtx",
        status: binaryPath ? "installed" : "missing",
        binary_path: binaryPath,
        official_release_url: MEDIAMTX_RELEASES_URL,
        detected_platform: process.platform,
        detected_arch: process.arch,
        recommended_asset_pattern: mediamtxAssetPattern(),
        host_tools: {
            brew_available: Boolean(brewPath),
            brew_path: brewPath,
        },
        options: [
            {
                id: "homebrew",
                label: "Homebrew",
                available: Boolean(brewPath),
                command: "brew install mediamtx",
                after_install: "Click Check relay again after Homebrew links mediamtx into PATH.",
            },
            {
                id: "official_release",
                label: "Official release archive",
                available: true,
                release_url: MEDIAMTX_RELEASES_URL,
                asset_pattern: mediamtxAssetPattern(),
                install_target: "/opt/homebrew/bin/mediamtx or /usr/local/bin/mediamtx",
                after_install: "Restart Device Node if the binary was added outside the current launchd PATH, then click Check relay.",
            },
        ],
    };
}

export function normalizeStreamName(value: unknown): string {
    const normalized = String(value || "")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9_-]+/g, "-")
        .replace(/^-+|-+$/g, "");
    return normalized || DEFAULT_STREAM_NAME;
}

function normalizePort(value: unknown, fallback: number): number {
    const candidate = Number(value);
    if (!Number.isInteger(candidate) || candidate < 1 || candidate > 65535) {
        return fallback;
    }
    return candidate;
}

function isManagedRelayRunning(): boolean {
    return Boolean(managedRelay && managedRelay.child.exitCode === null && !managedRelay.child.killed);
}

function activeManagedRelay(): ManagedRelayProcess | null {
    if (!isManagedRelayRunning()) {
        managedRelay = null;
        return null;
    }
    return managedRelay;
}

function chooseLanHost(): string {
    const interfaces = os.networkInterfaces();
    const candidates: string[] = [];
    for (const entries of Object.values(interfaces)) {
        for (const entry of entries || []) {
            if (entry.family !== "IPv4" || entry.internal) {
                continue;
            }
            candidates.push(entry.address);
        }
    }
    const privateCandidate = candidates.find((address) => (
        address.startsWith("192.168.")
        || address.startsWith("10.")
        || /^172\.(1[6-9]|2\d|3[0-1])\./.test(address)
    ));
    return privateCandidate || candidates[0] || "127.0.0.1";
}

export function buildRelayUrls(
    streamName: string,
    rtmpPort = DEFAULT_RTMP_PORT,
    rtspPort = DEFAULT_RTSP_PORT,
    lanHost = chooseLanHost(),
): RelayUrls {
    const portSegment = rtmpPort === DEFAULT_RTMP_PORT ? "" : `:${rtmpPort}`;
    return {
        stream_name: streamName,
        publish_url: `rtmp://${lanHost}${portSegment}/${streamName}`,
        read_url: `rtsp://127.0.0.1:${rtspPort}/${streamName}`,
    };
}

async function isTcpPortOpen(host: string, port: number, timeoutMs = 500): Promise<boolean> {
    return new Promise((resolve) => {
        const socket = net.createConnection({ host, port });
        let resolved = false;
        const finish = (value: boolean) => {
            if (resolved) {
                return;
            }
            resolved = true;
            socket.destroy();
            resolve(value);
        };
        socket.setTimeout(timeoutMs);
        socket.once("connect", () => finish(true));
        socket.once("timeout", () => finish(false));
        socket.once("error", () => finish(false));
    });
}

async function waitForTcpPort(host: string, port: number, timeoutMs: number): Promise<boolean> {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
        if (await isTcpPortOpen(host, port, 250)) {
            return true;
        }
        await new Promise((resolve) => setTimeout(resolve, 250));
    }
    return false;
}

function appendOutputLine(relay: ManagedRelayProcess, chunk: Buffer): void {
    const lines = chunk.toString("utf-8").split(/\r?\n/).filter(Boolean);
    relay.outputLines.push(...lines.slice(-20));
    relay.outputLines = relay.outputLines.slice(-20);
}

async function openObsApp(): Promise<{ opened: boolean; reason?: string }> {
    if (!fs.existsSync(OBS_APP_PATH)) {
        return { opened: false, reason: "obs_app_missing" };
    }
    return new Promise((resolve) => {
        const child = spawn("open", ["-a", "OBS"], { shell: false });
        let stderr = "";
        child.stderr.on("data", (chunk) => {
            stderr += chunk.toString("utf-8");
        });
        child.on("close", (code) => {
            if (code === 0) {
                resolve({ opened: true });
                return;
            }
            resolve({ opened: false, reason: stderr.trim() || `open_obs_exit_${code}` });
        });
        child.on("error", (error) => {
            resolve({ opened: false, reason: error.message });
        });
    });
}

async function buildStatus(
    action: CaptureRelayAction,
    args: CaptureRelayArgs,
    extra: Record<string, unknown> = {},
): Promise<Record<string, unknown>> {
    const streamName = normalizeStreamName(args.stream_name);
    const rtmpPort = normalizePort(args.rtmp_port, DEFAULT_RTMP_PORT);
    const rtspPort = normalizePort(args.rtsp_port, DEFAULT_RTSP_PORT);
    const obsWebsocketHost = String(args.obs_websocket_host || "127.0.0.1");
    const obsWebsocketPort = normalizePort(
        args.obs_websocket_port,
        DEFAULT_OBS_WEBSOCKET_PORT,
    );
    const binaryPath = resolveRelayBinary();
    const activeRelay = activeManagedRelay();
    const rtmpOpen = await isTcpPortOpen("127.0.0.1", rtmpPort);
    const obsWebsocketReachable = await isTcpPortOpen(obsWebsocketHost, obsWebsocketPort);
    const urls = buildRelayUrls(streamName, rtmpPort, rtspPort);
    const relayRunning = Boolean(activeRelay || rtmpOpen);
    const blocked = !relayRunning && !binaryPath;
    const status = relayRunning ? "running" : blocked ? "blocked" : "ready_to_start";
    const reason = blocked ? "relay_binary_missing" : undefined;

    return {
        schema_version: "capture_relay_control.v1",
        action,
        status,
        reason,
        relay: {
            engine: "mediamtx",
            mode: activeRelay ? "managed" : rtmpOpen ? "external" : "not_running",
            managed: Boolean(activeRelay),
            running: relayRunning,
            pid: activeRelay?.child.pid || null,
            started_at: activeRelay?.startedAt || null,
            binary_path: binaryPath,
            rtmp_port: rtmpPort,
            rtsp_port: rtspPort,
            rtmp_listener_open: rtmpOpen,
            recent_output: activeRelay?.outputLines.slice(-5) || [],
        },
        obs: {
            app_path: OBS_APP_PATH,
            app_present: fs.existsSync(OBS_APP_PATH),
            websocket_host: obsWebsocketHost,
            websocket_port: obsWebsocketPort,
            websocket_reachable: obsWebsocketReachable,
        },
        urls,
        install_guidance: buildInstallGuidance(binaryPath),
        next_steps: [
            "Start the RTMP relay.",
            "Set the external camera app RTMP destination to the publish_url.",
            "Add an OBS Media Source that reads the read_url.",
            "Start OBS Virtual Camera and select it from the browser device-link camera source.",
        ],
        ...extra,
    };
}

async function startRelay(args: CaptureRelayArgs): Promise<Record<string, unknown>> {
    const streamName = normalizeStreamName(args.stream_name);
    const rtmpPort = normalizePort(args.rtmp_port, DEFAULT_RTMP_PORT);
    const rtspPort = normalizePort(args.rtsp_port, DEFAULT_RTSP_PORT);
    const activeRelay = activeManagedRelay();
    if (activeRelay) {
        return buildStatus("start", args, { start_result: "already_managed" });
    }
    if (await isTcpPortOpen("127.0.0.1", rtmpPort)) {
        return buildStatus("start", args, { start_result: "external_listener_detected" });
    }

    const binaryPath = resolveRelayBinary();
    if (!binaryPath) {
        return buildStatus("start", args, { start_result: "blocked" });
    }

    const relay: ManagedRelayProcess = {
        child: spawn(binaryPath, [], {
            shell: false,
            stdio: ["ignore", "pipe", "pipe"],
        }),
        binaryPath,
        streamName,
        startedAt: new Date().toISOString(),
        rtmpPort,
        rtspPort,
        outputLines: [],
    };
    managedRelay = relay;
    relay.child.stdout?.on("data", (chunk) => appendOutputLine(relay, chunk));
    relay.child.stderr?.on("data", (chunk) => appendOutputLine(relay, chunk));
    relay.child.on("close", () => {
        if (managedRelay?.child === relay.child) {
            managedRelay = null;
        }
    });

    const timeoutMs = Math.min(Math.max(Number(args.timeout_ms || 5000), 1000), 15000);
    const ready = await waitForTcpPort("127.0.0.1", rtmpPort, timeoutMs);
    if (!ready) {
        return buildStatus("start", args, { start_result: "relay_start_timeout" });
    }
    return buildStatus("start", args, { start_result: "started", stream_name: streamName });
}

async function stopRelay(args: CaptureRelayArgs): Promise<Record<string, unknown>> {
    const activeRelay = activeManagedRelay();
    if (!activeRelay) {
        return buildStatus("stop", args, { stop_result: "no_managed_relay" });
    }
    activeRelay.child.kill("SIGTERM");
    await new Promise((resolve) => setTimeout(resolve, 500));
    if (activeRelay.child.exitCode === null && !activeRelay.child.killed) {
        activeRelay.child.kill("SIGKILL");
    }
    managedRelay = null;
    return buildStatus("stop", args, { stop_result: "stopped" });
}

export async function captureRelayControl(
    rawArgs: Record<string, unknown>,
): Promise<Record<string, unknown>> {
    const args = rawArgs as CaptureRelayArgs;
    const action = (String(args.action || "status").trim() || "status") as CaptureRelayAction;
    if (!["status", "start", "stop", "open_obs"].includes(action)) {
        return {
            schema_version: "capture_relay_control.v1",
            action,
            status: "rejected",
            reason: "unsupported_action",
        };
    }
    if (action === "start") {
        const result = await startRelay(args);
        if (args.open_obs) {
            return { ...result, obs_open: await openObsApp() };
        }
        return result;
    }
    if (action === "stop") {
        return stopRelay(args);
    }
    if (action === "open_obs") {
        return buildStatus("open_obs", args, { obs_open: await openObsApp() });
    }
    return buildStatus("status", args);
}

export default captureRelayControl;
